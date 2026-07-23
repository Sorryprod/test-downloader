from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class ExternalApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class RateLimitedError(ExternalApiError):
    def __init__(self, message: str, retry_after: float, status_code: int) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after


@dataclass
class MarkDownloadedResult:
    marked_now: int
    already_marked: int


def _parse_retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return 5.0
    try:
        return max(float(raw), 0.1)
    except ValueError:
        return 5.0


class ExternalFilesClient:
    """Клиент внешнего API с уважением к Retry-After / 429 / 403."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.external_api_base_url.rstrip("/"),
            timeout=httpx.Timeout(60.0, connect=15.0),
        )
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0
        # Текущий интервал может временно вырасти после 429
        self._current_interval = settings.external_api_min_interval_seconds
        self._consecutive_rate_limits = 0

    @property
    def candidate_headers(self) -> dict[str, str]:
        return {"X-Candidate-Id": self._settings.x_candidate_id}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _throttle(self) -> None:
        now = asyncio.get_running_loop().time()
        wait_for = self._last_request_at + self._current_interval - now
        if wait_for > 0:
            logger.debug("Throttle sleep %.2fs (interval=%.2fs)", wait_for, self._current_interval)
            await asyncio.sleep(wait_for)

    def _on_success(self) -> None:
        self._consecutive_rate_limits = 0
        base = self._settings.external_api_min_interval_seconds
        # Плавно возвращаемся к базовому интервалу
        self._current_interval = max(base, self._current_interval * 0.85)
        if self._current_interval - base < 0.05:
            self._current_interval = base

    def _on_rate_limit(self, retry_after: float, status_code: int) -> float:
        """Вернуть сколько секунд спать; увеличить текущий интервал."""
        self._consecutive_rate_limits += 1
        base = self._settings.external_api_min_interval_seconds
        buffer = self._settings.external_api_retry_buffer_seconds

        if status_code == 403:
            # Бан: ждём ровно Retry-After (+ небольшой запас), интервал после бана — повышенный
            sleep_for = retry_after + buffer
            self._current_interval = max(base * 2, 3.0)
            return sleep_for

        # 429: Retry-After + буфер, плюс экспонента по числу подряд идущих лимитов
        multiplier = min(2 ** (self._consecutive_rate_limits - 1), 8)
        sleep_for = max(retry_after + buffer, base) * multiplier
        self._current_interval = max(
            self._current_interval,
            base * (1.0 + 0.5 * self._consecutive_rate_limits),
            retry_after + buffer,
        )
        logger.info(
            "Rate-limit backoff: sleep=%.2fs, next_interval=%.2fs, streak=%s",
            sleep_for,
            self._current_interval,
            self._consecutive_rate_limits,
        )
        return sleep_for

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        expect_zip: bool = False,
        on_waiting: Any | None = None,
    ) -> httpx.Response:
        retries = self._settings.external_api_max_retries

        for attempt in range(retries + 1):
            async with self._lock:
                await self._throttle()
                response = await self._client.request(
                    method,
                    path,
                    headers=self.candidate_headers,
                    json=json_body,
                )
                self._last_request_at = asyncio.get_running_loop().time()

            if response.status_code in (429, 403):
                retry_after = _parse_retry_after(response)
                detail = ""
                try:
                    detail = response.json().get("detail", "")
                except Exception:
                    detail = response.text[:300]

                sleep_for = self._on_rate_limit(retry_after, response.status_code)
                message = (
                    f"Внешний API вернул {response.status_code}. "
                    f"Ожидание {sleep_for:.1f}с (Retry-After={retry_after:.1f}). {detail}"
                ).strip()
                logger.warning(message)

                if on_waiting is not None:
                    await on_waiting(message, sleep_for, response.status_code)

                if attempt >= retries:
                    raise RateLimitedError(message, sleep_for, response.status_code)

                await asyncio.sleep(sleep_for)
                # После паузы сбрасываем таймер throttle, чтобы не ждать ещё раз сразу
                self._last_request_at = asyncio.get_running_loop().time()
                continue

            if response.status_code >= 400:
                detail = response.text[:500]
                try:
                    detail = response.json().get("detail", detail)
                except Exception:
                    pass
                raise ExternalApiError(
                    f"Ошибка внешнего API {response.status_code}: {detail}",
                    status_code=response.status_code,
                )

            if expect_zip:
                content_type = response.headers.get("content-type", "")
                if "zip" not in content_type and not response.content.startswith(b"PK"):
                    raise ExternalApiError(
                        "Ожидался ZIP-архив, получен другой тип ответа",
                        status_code=response.status_code,
                    )

            self._on_success()
            return response

        raise ExternalApiError("Исчерпаны попытки запроса к внешнему API")

    async def get_file_names(self, *, on_waiting: Any | None = None) -> list[str]:
        response = await self._request("GET", "/api/files/names", on_waiting=on_waiting)
        payload = response.json()
        if "file_names" not in payload:
            raise ExternalApiError(
                f"Некорректный ответ /names: нет поля file_names ({payload!r})",
                status_code=response.status_code,
            )
        raw = payload["file_names"]
        if raw is None:
            raise ExternalApiError(
                "Некорректный ответ /names: file_names=null",
                status_code=response.status_code,
            )
        if not isinstance(raw, list):
            raise ExternalApiError(
                f"Некорректный ответ /names: file_names не список ({type(raw)!r})",
                status_code=response.status_code,
            )
        return [str(name) for name in raw]

    async def download_files(
        self,
        file_names: list[str],
        *,
        on_waiting: Any | None = None,
    ) -> bytes:
        if not file_names:
            raise ValueError("file_names пуст")
        if len(file_names) > 3:
            raise ValueError("Нельзя скачать больше 3 файлов за запрос")

        response = await self._request(
            "POST",
            "/api/files/download",
            json_body={"file_names": file_names},
            expect_zip=True,
            on_waiting=on_waiting,
        )
        return response.content

    async def mark_downloaded(
        self,
        file_names: list[str],
        *,
        on_waiting: Any | None = None,
    ) -> MarkDownloadedResult:
        if not file_names:
            raise ValueError("file_names пуст")

        response = await self._request(
            "POST",
            "/api/files/downloaded",
            json_body={"file_names": file_names},
            on_waiting=on_waiting,
        )
        payload = response.json()
        return MarkDownloadedResult(
            marked_now=int(payload.get("marked_now", 0)),
            already_marked=int(payload.get("already_marked", 0)),
        )
