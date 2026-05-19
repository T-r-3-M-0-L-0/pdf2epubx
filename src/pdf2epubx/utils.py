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


def repair_hyphenation(value: str) -> str:
    value = re.sub(r"([A-Za-zА-Яа-яЁё])-[\n ]+([A-Za-zА-Яа-яЁё])", r"\1\2", value)
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