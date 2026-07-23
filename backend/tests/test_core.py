from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest
import respx

from app.core.config import Settings
from app.services.downloader import extract_text_files_from_zip
from app.services.external_client import ExternalFilesClient, RateLimitedError
from app.services.stats import count_digits, merge_digit_counts


def test_count_digits_basic() -> None:
    content = "01234567890123"
    counts = count_digits(content)
    assert counts["0"] == 2
    assert counts["1"] == 2
    assert counts["9"] == 1
    assert counts["8"] == 1


def test_count_digits_rejects_non_digits() -> None:
    with pytest.raises(ValueError, match="только из цифр"):
        count_digits("12a34")


def test_merge_digit_counts() -> None:
    overall = merge_digit_counts(
        [
            count_digits("111"),
            count_digits("2221"),
        ]
    )
    assert overall["1"] == 4
    assert overall["2"] == 3
    assert overall["0"] == 0


def test_extract_text_files_from_zip() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("a.txt", "123")
        archive.writestr("nested/b.txt", "456")
    extracted = extract_text_files_from_zip(buffer.getvalue())
    assert extracted["a.txt"] == "123"
    assert extracted["b.txt"] == "456"


@pytest.mark.asyncio
@respx.mock
async def test_get_file_names_retries_after_429() -> None:
    settings = Settings(
        external_api_base_url="http://example.test",
        x_candidate_id="wasireal",
        external_api_min_interval_seconds=0,
        external_api_max_retries=3,
    )

    route = respx.get("http://example.test/api/files/names")
    route.side_effect = [
        httpx.Response(
            429,
            json={"detail": "slow down"},
            headers={"Retry-After": "0.01"},
        ),
        httpx.Response(200, json={"file_names": ["a.txt", "b.txt"]}),
    ]

    client = ExternalFilesClient(settings)
    try:
        names = await client.get_file_names()
        assert names == ["a.txt", "b.txt"]
        assert route.call_count == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_exhausted() -> None:
    settings = Settings(
        external_api_base_url="http://example.test",
        x_candidate_id="wasireal",
        external_api_min_interval_seconds=0,
        external_api_max_retries=1,
    )

    respx.get("http://example.test/api/files/names").mock(
        return_value=httpx.Response(
            403,
            json={"detail": "banned"},
            headers={"Retry-After": "0.01"},
        )
    )

    client = ExternalFilesClient(settings)
    try:
        with pytest.raises(RateLimitedError):
            await client.get_file_names()
    finally:
        await client.aclose()
