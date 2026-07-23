"""
Smoke-тест внешнего API: пара запросов без mark (прогресс кандидата не трогаем).

Запуск из корня репозитория:
  backend\\.venv\\Scripts\\python scripts\\smoke_external_api.py

Опции:
  --mark   после download вызвать POST /downloaded (меняет прогресс!)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

BASE_URL = os.getenv("EXTERNAL_API_BASE_URL", "http://91.199.149.128:18001").rstrip("/")
CANDIDATE_ID = os.getenv("X_CANDIDATE_ID", "wasireal")
HEADERS = {"X-Candidate-Id": CANDIDATE_ID}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-тест внешнего Files API")
    parser.add_argument(
        "--mark",
        action="store_true",
        help="После скачивания отметить файлы через /downloaded",
    )
    args = parser.parse_args()

    print(f"BASE_URL     = {BASE_URL}")
    print(f"Candidate-Id = {CANDIDATE_ID}")
    print("-" * 50)

    with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=60.0) as client:
        # 1) Имена файлов
        print("\n[1] GET /api/files/names")
        names_resp = client.get("/api/files/names")
        _print_response(names_resp)

        if names_resp.status_code in (429, 403):
            print("\nRate-limit/ban. Смотри Retry-After и повтори позже.")
            return 1

        if names_resp.status_code != 200:
            return 1

        file_names: list[str] = names_resp.json().get("file_names", [])
        if not file_names:
            print("Список имён пуст — для этого candidate-id каталог уже отмечен скачанным.")
            return 0

        batch = file_names[:3]
        print(f"\nВозьмём для download до 3 имён: {batch}")

        # 2) Скачивание ZIP
        print("\n[2] POST /api/files/download")
        download_resp = client.post("/api/files/download", json={"file_names": batch})
        _print_response(download_resp, preview_body=False)

        if download_resp.status_code != 200:
            return 1

        zip_path = ROOT / "scripts" / "_last_download.zip"
        zip_path.write_bytes(download_resp.content)
        print(f"ZIP сохранён: {zip_path} ({len(download_resp.content)} bytes)")

        if not args.mark:
            print(
                "\nГотово. Mark не вызывали — прогресс кандидата не изменён.\n"
                "Чтобы отметить файлы: добавь флаг --mark"
            )
            return 0

        # 3) Отметка (опционально)
        print("\n[3] POST /api/files/downloaded")
        mark_resp = client.post("/api/files/downloaded", json={"file_names": batch})
        _print_response(mark_resp)
        return 0 if mark_resp.status_code == 200 else 1


def _print_response(response: httpx.Response, *, preview_body: bool = True) -> None:
    print(f"status = {response.status_code}")
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        print(f"Retry-After = {retry_after}")

    content_type = response.headers.get("content-type", "")
    print(f"content-type = {content_type}")

    if not preview_body:
        return

    if "application/json" in content_type:
        print(f"body = {response.json()}")
    else:
        text = response.text[:300]
        print(f"body = {text!r}")


if __name__ == "__main__":
    sys.exit(main())
