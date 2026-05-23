from __future__ import annotations

import re
from collections import Counter

import fitz  # PyMuPDF

from pdf2epubx.utils import normalize_for_repetition, normalize_spaces


def repair_broken_paragraphs(text: str, level: str = "Medium") -> str:
    """
    Склеивает разорванные параграфы.

    Уровни:
    - Off — не трогать
    - Low — только дефисные переносы
    - Medium — склеивание строк, не заканчивающихся на .!?:;
    - Aggressive — также убирает лишние пробелы внутри слов (опасно)
    """
    if level == "Off":
        return text

    lines = [line.rstrip() for line in text.split('\n')]
    result: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Пустая строка → разделитель параграфов
        if not stripped:
            result.append("")
            continue

        # Первая строка — просто добавляем
        if not result or not result[-1]:
            result.append(stripped)
            continue

        prev = result[-1].rstrip()

        # Low: только дефисные переносы (слово-\n продолжение)
        if prev.endswith("-") and stripped and stripped[0].islower():
            result[-1] = prev[:-1] + stripped
            continue

        # Medium: склеиваем если предыдущая строка НЕ заканчивается
        # на терминальную пунктуацию и текущая начинается с маленькой буквы
        if level in ("Medium", "Aggressive"):
            ends_with_terminal = bool(re.search(r'[.!?;:»"]\s*$', prev))
            starts_with_lower = bool(stripped) and stripped[0].islower()
            starts_with_continuation = starts_with_lower or stripped[0] in '(«"—–'

            # Не склеиваем заголовки (короткие строки + капитализация)
            prev_is_heading = len(prev) < 80 and not ends_with_terminal and prev[0].isupper()
            current_is_heading = len(stripped) < 80 and stripped[0].isupper() and not starts_with_continuation

            if not ends_with_terminal and starts_with_continuation and not current_is_heading:
                result[-1] = prev + " " + stripped
                continue

        result.append(stripped)

    text = '\n'.join(result)

    # Убираем двойные пробелы
    text = re.sub(r'[ \t]{2,}', ' ', text)

    return text.strip()


def clean_garbage_symbols(text: str) -> str:
    """Максимально агрессивная очистка маркеров списков (включая выноски и отступы)"""

    # 0. Нормализуем все виды whitespace (включая NBSP, тонкие пробелы и т.д.)
    # Это важно, потому что между символами могут быть специальные пробелы
    text = re.sub(r'[\u00A0\u2000-\u200B\u202F\u3000]', ' ', text)

    # 1. z z и zz (включая варианты с разными пробелами после нормализации)
    text = re.sub(r'z\s+z', '•', text, flags=re.IGNORECASE)
    text = re.sub(r'zz+', '•', text, flags=re.IGNORECASE)
    # Отдельная Z в начале строки перед буквой
    text = re.sub(r'^\s*z\s+([А-ЯA-Zа-яa-z])', r'• \1', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\n\s*z\s+([А-ЯA-Zа-яa-z])', r'\n• \1', text, flags=re.IGNORECASE)

    # 2. Все виды квадратов и других маркеров (расширенный список Unicode)
    # Основные квадраты и подобные символы
    square_chars = '□■▪▫●○·∙⬜⬛◻◼▢❑❒☐'

    # Сначала обрабатываем комбинации квадратов в начале строки (самый частый случай)
    # Паттерн: начало строки + отступы + один или несколько квадратов + пробелы
    text = re.sub(rf'^\s*[{square_chars}]+[ \t]*', '• ', text, flags=re.MULTILINE)
    text = re.sub(rf'\n\s*[{square_chars}]+[ \t]*', '\n• ', text, flags=re.IGNORECASE)

    # Затем обрабатываем квадраты в середине текста (комбинации)
    # Паттерн: квадрат(пробелы+квадрат)* - последовательность квадратов через пробелы
    text = re.sub(rf'[{square_chars}](?:[ \t]*[{square_chars}])*', '•', text)

    # 3. Дополнительные маркеры списков (bullet-like symbols)
    bullet_replacements = {
        '▪': '•', '▫': '•', '■': '•', '●': '•', '○': '•',
        '·': '•', '∙': '•', '◦': '•', '‣': '•', '⁃': '•',
        '◘': '•', '◙': '•', '⦿': '•', '⦾': '•',
        # Checkbox-символы
        '☐': '•', '☑': '•', '☒': '•',
        # Геометрические фигуры
        '⬜': '•', '⬛': '•', '◻': '•', '◼': '•', '▢': '•',
        '❑': '•', '❒': '•', '❖': '•',
        # Стрелки и указатели (иногда используются как маркеры)
        '➢': '•', '➣': '•', '➤': '•', '➥': '•', '➧': '•',
        '➨': '•', '➩': '•', '➪': '•', '➫': '•', '➬': '•',
        '➭': '•', '➮': '•', '➯': '•', '➱': '•', '➲': '•',
        '➳': '•', '➴': '•', '➵': '•', '➶': '•', '➷': '•',
        '➸': '•', '➹': '•', '➺': '•', '➻': '•', '➼': '•',
        '➽': '•', '➾': '•',
        # Звёздочки и другие символы
        '✦': '•', '✧': '•', '★': '•', '☆': '•',
        '✩': '•', '✪': '•', '✫': '•', '✬': '•', '✭': '•',
        '✮': '•', '✯': '•', '✰': '•',
        # Ромбы
        '♦': '•', '◊': '•', '🞐': '•', '🞑': '•', '🞒': '•', '🞓': '•',
        # Треугольники
        '▲': '•', '▼': '•', '◀': '•', '▶': '•',
        '△': '•', '▽': '•', '◁': '•', '▷': '•',
    }
    for char, repl in bullet_replacements.items():
        text = text.replace(char, repl)

    # 4. Символы Private Use Area (PUA), которые часто используются для кастомных маркеров
    # Диапазоны: U+E000-U+F8FF, U+F0000-U+FFFFD, U+100000-U+10FFFD
    # Наиболее распространённые маркеры в PUA: U+F06C, U+F0B7, U+F0A1
    pua_markers = '\uF06C\uF0B7\uF0A1\uF06E\uF070\uF0A7\uF0AD'
    text = re.sub(f'[{pua_markers}]+', '•', text)

    # 5. Удаляем одиночные символы в начале строки (альтернативные маркеры)
    # Но только если это НЕ буквы алфавита и НЕ цифры
    # Заменяем только специальные символы, которые могут быть артефактами OCR
    # Паттерн: начало строки + отступ + одиночный символ (не буква/цифра) + пробел + текст
    text = re.sub(r'^\s*[^\w\sа-яА-Яa-zA-Z][ \t]+([А-ЯA-Zа-яa-z])', r'• \1', text, flags=re.MULTILINE)

    # Исключение: если это всё-таки буква, но она повторяется в нескольких строках подряд
    # (это может быть артефактом нумерации списка типа "a. b. c." или "z z z")
    # Обработку таких случаев оставляем для специальных паттернов выше (z, zz)

    # 6. Финальная очистка: множественные маркеры подряд и нормализация пробелов
    text = re.sub(r'•+', '•', text)
    # Убираем двойные пробелы после маркеров
    text = re.sub(r'•[ \t]+', '• ', text)

    return text


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
    text = clean_garbage_symbols(text)                    # ← первая и самая важная
    text = clean_page_numbers(text)
    text = clean_toc_leaders(text)
    text = clean_side_chapter_numbers(text)
    text = clean_chart_artifacts(text, preserve_figure_references)
    text = repair_broken_paragraphs(text, aggressive_level)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def clean_page_numbers(text: str) -> str:
    """
    Удаляет номера страниц, но НЕ трогает:
    - Годы (1900–2099)
    - Нумерованные списки (1. 2. 3.)
    - Номера портов, кодов и т.п.
    """
    # Убираем явные маркеры "Page N", "Стр. N"
    text = re.sub(r'\bPage\s+\d+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bстр\.?\s*\d+\b', '', text, flags=re.IGNORECASE)

    # Убираем изолированные числа на отдельных строках (но НЕ годы, НЕ длинные числа)
    # Только 1-4 цифры, стоящие как единственное содержимое строки
    def _is_page_number(match: re.Match) -> str:
        num = match.group(0).strip()
        if not num.isdigit():
            return match.group(0)
        n = int(num)
        # Не трогаем годы (1900–2099)
        if 1900 <= n <= 2099:
            return match.group(0)
        # Не трогаем числа > 9999 (порты, коды)
        if n > 9999:
            return match.group(0)
        return ""

    text = re.sub(r'^\s*\d{1,4}\s*$', _is_page_number, text, flags=re.MULTILINE)
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