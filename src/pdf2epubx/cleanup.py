from __future__ import annotations

import re
from collections import Counter

import fitz

from pdf2epubx.utils import normalize_for_repetition, normalize_spaces


def repair_broken_paragraphs(text: str, level: str = "Medium") -> str:
    if level == "Off":
        return text
    lines = [line.rstrip() for line in text.split('\n')]
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        if result and not re.search(r'[.!?]$', result[-1].strip()):
            prev = result.pop()
            joined = prev.rstrip('- ') + " " + stripped.lstrip('- ')
            result.append(joined)
        else:
            result.append(line)
    text = '\n'.join(result)
    if level in ["Medium", "Aggressive"]:
        text = re.sub(r'(\S)\s*\n\s*(\S)', r'\1 \2', text)
        text = re.sub(r'\s{2,}', ' ', text)
    if level == "Aggressive":
        text = re.sub(r'([a-zA-Zа-яА-Я0-9])\s+([a-zA-Zа-яА-Я0-9])', r'\1\2', text)
        text = re.sub(r'-\s+', '', text)
    return text.strip()


def clean_chart_artifacts(text: str, preserve_figure_references: bool = False) -> str:
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            clean_lines.append(line)
            continue
        lower = stripped.lower()
        length = len(stripped)

        if preserve_figure_references and re.search(r'(рис\.?|рисунок|figure|fig\.?)\s*\d', lower):
            clean_lines.append(line)
            continue

        if length > 70 or "—" in stripped:
            clean_lines.append(line)
            continue

        if (
            re.fullmatch(r'[а-яa-z]\.?', lower) or
            re.search(r'\b(19|20)\d{2}\b', stripped) or
            re.search(r'\b(млрд|млн|тыс|ев|eb|pb|г\.|р\.|эксабайты)\b', lower) or
            (len(re.findall(r'\d', stripped)) > length * 0.45 and length < 50) or
            (length < 60 and any(kw in lower for kw in ["mainframe", "мейнфрейм", "оператор", "пакет заданий", "ввода", "польз.", "терминал", "устройство", "график", "трафика"]))
        ):
            continue
        clean_lines.append(line)
    return '\n'.join(clean_lines)


def clean_text_post_processing_full(text: str, aggressive_level: str = "Medium", preserve_figure_references: bool = False) -> str:
    text = clean_garbage_symbols(text)
    text = clean_page_numbers(text)
    text = clean_toc_leaders(text)
    text = clean_side_chapter_numbers(text)
    text = clean_chart_artifacts(text, preserve_figure_references)
    text = repair_broken_paragraphs(text, aggressive_level)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def clean_garbage_symbols(text: str) -> str:
    replacements = {
        r'z\s*z': '•', r'zz': '•', r'z→': '→', r'z←': '←',
        r'z↑': '↑', r'z↓': '↓', r'z\.': '•',
        r'\s+·\s+': ' • ',
        r'■': '•', r'□': '•', r'▪': '•', r'▫': '•',
    }
    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def clean_page_numbers(text: str) -> str:
    text = re.sub(r'\bPage\s+\d+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bстр\.?\s*\d+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+\d+\s*\n', '\n', text)
    return text.strip()


def clean_toc_leaders(text: str) -> str:
    text = re.sub(r'\s*\.{6,}\s*\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*\.{4,}\s*', ' — ', text)
    text = re.sub(r'(\.{3,}\s*)+', ' — ', text)
    text = re.sub(r'^\s*\.{4,}', '', text, flags=re.MULTILINE)
    return text


def clean_side_chapter_numbers(text: str) -> str:
    lines = text.split('\n')
    clean_lines = [line for line in lines if not re.fullmatch(r'\d{1,3}', line.strip())]
    return '\n'.join(clean_lines)


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