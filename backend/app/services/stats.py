from __future__ import annotations

from collections import Counter


DIGIT_KEYS = tuple(str(digit) for digit in range(10))


def empty_digit_counts() -> dict[str, int]:
    return {key: 0 for key in DIGIT_KEYS}


def count_digits(content: str) -> dict[str, int]:
    """Подсчёт частоты цифр 0–9 в содержимом файла."""
    normalized = content.strip()
    if not normalized:
        raise ValueError("Файл пустой")

    if not normalized.isdigit():
        raise ValueError("Содержимое файла должно состоять только из цифр 0–9")

    counter = Counter(normalized)
    result = empty_digit_counts()
    for digit, count in counter.items():
        result[digit] = count
    return result


def merge_digit_counts(items: list[dict[str, int]]) -> dict[str, int]:
    overall = empty_digit_counts()
    for item in items:
        for key in DIGIT_KEYS:
            overall[key] += int(item.get(key, 0))
    return overall
