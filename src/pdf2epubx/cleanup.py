from __future__ import annotations

from collections import Counter

import fitz

from pdf2epubx.utils import normalize_for_repetition, normalize_spaces


def detect_repeated_marginal_texts(
    doc: fitz.Document,
    max_pages: int = 80,
    min_repeats: int = 3,
    top_ratio: float = 0.12,
    bottom_ratio: float = 0.12,
) -> set[str]:
    """Улучшенное обнаружение повторяющихся колонтитулов (уже было, но чуть доработал)."""
    counter: Counter[str] = Counter()

    page_count = min(len(doc), max_pages)

    for page_index in range(page_count):
        page = doc[page_index]
        height = float(page.rect.height)
        top_limit = height * top_ratio
        bottom_limit = height * (1.0 - bottom_ratio)

        data = page.get_text("dict", sort=True)

        for block in data.get("blocks", []):
            if block.get("type") != 0:  # только текст
                continue

            bbox = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue

            y0 = float(bbox[1])
            y1 = float(bbox[3])

            is_top = y1 <= top_limit
            is_bottom = y0 >= bottom_limit

            if not is_top and not is_bottom:
                continue

            text = extract_text_from_block_dict(block)
            normalized = normalize_for_repetition(text)

            if len(normalized) >= 3:  # отбрасываем слишком короткие
                counter[normalized] += 1

    return {
        text
        for text, count in counter.items()
        if count >= min_repeats
    }


def extract_text_from_block_dict(block: dict) -> str:
    """Вспомогательная функция (была в старом файле)."""
    parts: list[str] = []

    for line in block.get("lines", []):
        line_parts: list[str] = []
        for span in line.get("spans", []):
            text = str(span.get("text", ""))
            if text:
                line_parts.append(text)
        line_text = normalize_spaces("".join(line_parts))
        if line_text:
            parts.append(line_text)

    return normalize_spaces(" ".join(parts))


# НОВАЯ ФУНКЦИЯ — можно вызывать дополнительно для жёсткой очистки
def remove_headers_footers_by_height(
    page: fitz.Page,
    header_height: float = 50.0,
    footer_height: float = 45.0,
) -> str:
    """Жёсткая очистка по высоте (fallback, если detect не сработал)."""
    rect = page.rect
    clip = fitz.Rect(0, header_height, rect.width, rect.height - footer_height)
    text = page.get_text("text", clip=clip, sort=True)
    return text