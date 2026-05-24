from __future__ import annotations

import hashlib
import html
import re


def html_escape(value: str) -> str:
    return html.escape(value, quote=True)


def normalize_spaces(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    return value.strip()


def normalize_for_repetition(value: str) -> str:
    value = normalize_spaces(value)
    value = value.lower()
    value = re.sub(r"\d+", "#", value)
    value = re.sub(r"[^\wа-яё# ]+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_line(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([(«])\s+", r"\1", value)
    value = re.sub(r"\s+([)»])", r"\1", value)
    return value.strip()


def _is_likely_hyphenation(word_before_hyphen: str, word_after: str) -> bool:
    """
    Определяет, является ли дефис переносом строки (а не частью составного слова).

    Составные слова типа "интернет-магазин", "кто-то" не должны склеиваться.
    Переносы типа "компью-тер" — должны.

    Эвристика:
    - Если часть перед дефисом слишком короткая (< 2 символов) — не перенос
    - Если часть после дефиса начинается с заглавной — не перенос
    - Если обе части достаточно длинные (>= 4 буквы) — скорее составное слово
    - Если часть после дефиса короткая (1-3 буквы) — скорее перенос
    """
    if len(word_before_hyphen) < 2 or not word_after:
        return False

    # Если слово после дефиса начинается с заглавной — это не перенос
    if word_after[0].isupper():
        return False

    # Извлекаем первое слово из word_after (может быть "тер продолжение")
    first_word_after = word_after.split()[0] if word_after.split() else word_after

    # Если обе части — полноценные слова (>= 4 буквы каждая),
    # скорее всего это составное слово ("интернет-магазин"), а не перенос
    if len(word_before_hyphen) >= 4 and len(first_word_after) >= 4:
        return False

    # Если часть после дефиса короткая (1-3 буквы) — скорее перенос
    if len(first_word_after) <= 3:
        return True

    # Русские и латинские гласные
    vowels = set("аеёиоуыэюяaeiouyАЕЁИОУЫЭЮЯAEIOUY")

    # Если часть перед дефисом заканчивается слогом (гласная + согласная),
    # это выглядит как слог, разорванный переносом
    last_chars = word_before_hyphen[-3:]
    has_vowel = any(c in vowels for c in last_chars)
    has_consonant = any(c.isalpha() and c not in vowels for c in last_chars)

    if has_vowel and has_consonant:
        return True

    return False


def repair_hyphenation(value: str) -> str:
    """
    Склеивает слова, разорванные переносом строк.

    Обрабатывает случаи:
    1. Слово с дефисом + newline + продолжение (компью-\\nтер → компьютер)
    2. Слово с дефисом + пробел + продолжение (компью- тер → компьютер)
    3. Двойной дефис на стыке строк

    Args:
        value: Текст с возможными переносами.

    Returns:
        Текст со склеенными словами.
    """
    # 1. Классический случай: слово + дефис + newline(s) + пробелы + строчная буква
    # Захватываем всё слово перед дефисом для контекстного анализа
    def _repair_newline_hyphen(match: re.Match) -> str:
        word_before = match.group(1)
        after = match.group(2)
        if _is_likely_hyphenation(word_before, after):
            return word_before + after
        return match.group(0)

    value = re.sub(r'([A-Za-zА-Яа-яЁё]+)-\s*\n\s*([a-zа-яё])', _repair_newline_hyphen, value)

    # 2. Двойной дефис на стыке строк: -\n- → "" (полное удаление)
    value = re.sub(r'-\s*\n\s*-', '', value)

    # 3. Дефис + пробел(ы) + строчная буква (после join строк в одну)
    # "компью- тер" → "компьютер"
    def _repair_space_hyphen(match: re.Match) -> str:
        word_before = match.group(1)
        after = match.group(2)
        if _is_likely_hyphenation(word_before, after):
            return word_before + after
        return match.group(0)

    value = re.sub(r'([A-Za-zА-Яа-яЁё]+)-\s+([a-zа-яё])', _repair_space_hyphen, value)

    return value


def block_plain_text_from_lines(lines: list[list[str]]) -> str:
    return normalize_spaces(" ".join(" ".join(line) for line in lines))


def safe_filename_fragment(value: str, max_length: int = 64) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^\wа-яё.-]+", "_", normalized, flags=re.IGNORECASE)
    normalized = normalized.strip("._-")

    if not normalized:
        normalized = "item"

    return normalized[:max_length]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_metadata_value(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = normalize_spaces(str(value))
    return cleaned or None