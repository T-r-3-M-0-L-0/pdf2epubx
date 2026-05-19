from __future__ import annotations

import re
from collections import Counter

import fitz  # PyMuPDF

from pdf2epubx.utils import normalize_for_repetition, normalize_spaces


# ====================== НОВЫЕ ФУНКЦИИ ОЧИСТКИ ======================

def clean_page_numbers(text: str) -> str:
    #Удаляем все варианты номеров страниц
    text = re.sub(r'\bPage\s+\d+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bстр\.?\s*\d+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+\d+\s*$', '', text, flags=re.MULTILINE)      # число в конце строки
    text = re.sub(r'\s+\d+\s*\n', '\n', text)
    return text.strip()


def clean_toc_leaders(text: str) -> str:
    #Убираем точки-лидеры в оглавлении: «Название ................ 407»
    # Длинная цепочка точек + число в конце строки
    text = re.sub(r'\s*\.{5,}\s*\d+\s*$', '', text, flags=re.MULTILINE)
    # Заменяем оставшиеся точки на тире (выглядит красиво в EPUB)
    text = re.sub(r'\s*\.{4,}\s*', ' — ', text)
    return text


def clean_text_post_processing(text: str) -> str:
    """Главная функция пост-обработки (вызывать после извлечения текста)."""
    text = clean_page_numbers(text)
    text = clean_toc_leaders(text)
    text = re.sub(r'\n{3,}', '\n\n', text)      # убираем лишние пустые строки
    text = re.sub(r'[ \t]+', ' ', text)         # лишние пробелы
    return text.strip()


# ====================== СТАРЫЕ ФУНКЦИИ (оставляем без изменений) ======================

def detect_repeated_marginal_texts(
    doc: fitz.Document,
    max_pages: int = 80,
    min_repeats: int = 3,
    top_ratio: float = 0.12,
    bottom_ratio: float = 0.12,
) -> set[str]:
    """Улучшенное обнаружение повторяющихся колонтитулов."""
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

            if len(normalized) >= 3:
                counter[normalized] += 1

    return {
        text
        for text, count in counter.items()
        if count >= min_repeats
    }


def extract_text_from_block_dict(block: dict) -> str:
    """Вспомогательная функция."""
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


def remove_headers_footers_by_height(
    page: fitz.Page,
    header_height: float = 50.0,
    footer_height: float = 45.0,
) -> str:
    """Жёсткая очистка по высоте (fallback)."""
    rect = page.rect
    clip = fitz.Rect(0, header_height, rect.width, rect.height - footer_height)
    text = page.get_text("text", clip=clip, sort=True)
    return text