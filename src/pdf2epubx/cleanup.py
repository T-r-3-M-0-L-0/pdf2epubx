from __future__ import annotations

import re
from collections import Counter

import fitz  # PyMuPDF

from pdf2epubx.utils import normalize_for_repetition, normalize_spaces


# ====================== УЛУЧШЕННАЯ ОЧИСТКА ======================

def clean_garbage_symbols(text: str) -> str:
    """Исправляем все PDF-артефакты буллетов и спецсимволов."""
    replacements = {
        r'z\s*z': '•',
        r'zz': '•',
        r'z→': '→',
        r'z←': '←',
        r'z↑': '↑',
        r'z↓': '↓',
        r'z\.': '•',
        r'\s+·\s+': ' • ',
        r'■': '•',      # закрашенный квадрат
        r'□': '•',      # пустой квадрат — САМАЯ ЧАСТАЯ ПРОБЛЕМА
        r'▪': '•',
        r'▫': '•',
        r'●': '•',
        r'○': '•',
    }
    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def clean_page_numbers(text: str) -> str:
    """Удаляем номера страниц."""
    text = re.sub(r'\bPage\s+\d+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bстр\.?\s*\d+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+\d+\s*\n', '\n', text)
    return text.strip()


def clean_toc_leaders(text: str) -> str:
    """Максимально агрессивная очистка точек-лидеров (включая наслаивающиеся)."""
    # 1. Классика: 6+ точек + число в конце строки
    text = re.sub(r'\s*\.{6,}\s*\d+\s*$', '', text, flags=re.MULTILINE)
    # 2. Любое количество точек между текстом и числом
    text = re.sub(r'\s*\.{4,}\s*', ' — ', text)
    # 3. Несколько строк подряд с точками (наслаивание)
    text = re.sub(r'(\.{3,}\s*)+', ' — ', text)
    # 4. Точки в начале строки
    text = re.sub(r'^\s*\.{4,}', '', text, flags=re.MULTILINE)
    return text


def clean_side_chapter_numbers(text: str) -> str:
    """Удаляем висячие номера глав справа (одиночные цифры 1–3 символа)."""
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        # Если вся строка — это просто число длиной 1–3 символа → пропускаем
        if re.fullmatch(r'\d{1,3}', stripped):
            continue
        clean_lines.append(line)
    return '\n'.join(clean_lines)


def clean_text_post_processing(text: str) -> str:
    """Главная функция — вызывать после извлечения текста."""
    text = clean_garbage_symbols(text)
    text = clean_page_numbers(text)
    text = clean_toc_leaders(text)
    text = clean_side_chapter_numbers(text)      # ← новое
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


# ====================== СТАРЫЕ ФУНКЦИИ (оставляем как есть) ======================

def detect_repeated_marginal_texts(
    doc: fitz.Document,
    max_pages: int = 80,
    min_repeats: int = 3,
    top_ratio: float = 0.12,
    bottom_ratio: float = 0.12,
) -> set[str]:
    counter: Counter[str] = Counter()
    page_count = min(len(doc), max_pages)

    for page_index in range(page_count):
        page = doc[page_index]
        height = float(page.rect.height)
        top_limit = height * top_ratio
        bottom_limit = height * (1.0 - bottom_ratio)

        data = page.get_text("dict", sort=True)

        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            bbox = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue

            y0, y1 = float(bbox[1]), float(bbox[3])
            if not (y1 <= top_limit or y0 >= bottom_limit):
                continue

            text = extract_text_from_block_dict(block)
            normalized = normalize_for_repetition(text)
            if len(normalized) >= 3:
                counter[normalized] += 1

    return {text for text, count in counter.items() if count >= min_repeats}


def extract_text_from_block_dict(block: dict) -> str:
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
    rect = page.rect
    clip = fitz.Rect(0, header_height, rect.width, rect.height - footer_height)
    return page.get_text("text", clip=clip, sort=True)