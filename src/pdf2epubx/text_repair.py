"""
Модуль восстановления текста из "плохих" PDF.
Обрабатывает повреждённые кодировки, разорванные spans, лигатуры,
и артефакты сканирования (фальшивый bold, мусорные символы).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence


# ──────────────────────────────────────────────
# 1. Encoding repair
# ──────────────────────────────────────────────

# Частые замены PUA (Private Use Area) символов
PUA_REPLACEMENTS: dict[str, str] = {
    "\uF06C": "•", "\uF0B7": "•", "\uF0A1": "•",
    "\uF06E": "•", "\uF070": "•", "\uF0A7": "•", "\uF0AD": "•",
    "\uF022": '"', "\uF023": "#", "\uF025": "%",
    "\uF02D": "-", "\uF02E": ".",
    "\uF0D0": "—", "\uF0D1": "–",
    "\uF020": " ",
    "\uF0FC": "✓",
}

# Mojibake: частые ошибки при неправильной интерпретации кодировок
MOJIBAKE_REPAIRS: list[tuple[str, str]] = [
    ("\u00c3\u00a9", "\u00e9"),   # Ã© → é
    ("\u00c3\u00a8", "\u00e8"),   # Ã¨ → è
    ("\u00c3\u00a0", "\u00e0"),   # Ã  → à
    ("\u00c3\u00bc", "\u00fc"),   # Ã¼ → ü
    ("\u00c3\u00b6", "\u00f6"),   # Ã¶ → ö
    ("\u00c3\u00a4", "\u00e4"),   # Ã¤ → ä
    ("\u00c3\u00b1", "\u00f1"),   # Ã± → ñ
    ("\u00c2\u00ab", "\u00ab"),   # Â« → «
    ("\u00c2\u00bb", "\u00bb"),   # Â» → »
    ("\u00c2\u00a0", " "),        # Â  → пробел
]

# Лигатуры, которые PDF иногда не раскладывает
LIGATURE_MAP: dict[str, str] = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
    "\ufb03": "ffi", "\ufb04": "ffl",
    "\ufb05": "ſt", "\ufb06": "st",
}


def repair_encoding(text: str, font_name: str = "") -> str:
    """
    Исправляет повреждённые кодировки.

    Args:
        text: Исходный текст.
        font_name: Имя шрифта (для контекстно-зависимых исправлений).

    Returns:
        Исправленный текст.
    """
    if not text:
        return text

    # PUA символы
    for pua_char, replacement in PUA_REPLACEMENTS.items():
        text = text.replace(pua_char, replacement)

    # Mojibake
    for broken, fixed in MOJIBAKE_REPAIRS:
        text = text.replace(broken, fixed)

    # Лигатуры
    for lig, expanded in LIGATURE_MAP.items():
        text = text.replace(lig, expanded)

    # Удаляем невидимые управляющие символы (кроме \n \r \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Замена soft hyphen
    text = text.replace("\u00ad", "")

    # Замена no-break space
    text = text.replace("\u00a0", " ")

    return text


# ──────────────────────────────────────────────
# 2. Bold normalization (для сканов)
# ──────────────────────────────────────────────

# Flags в PyMuPDF: bit 4 (0x10) = bold, bit 1 (0x02) = italic
BOLD_FLAG = 0x10
ITALIC_FLAG = 0x02


@dataclass
class SpanInfo:
    """Информация о span для анализа."""
    text: str
    font: str
    size: float
    flags: int
    bbox: tuple[float, float, float, float]
    color: int = 0

    @property
    def is_bold(self) -> bool:
        return bool(self.flags & BOLD_FLAG) or _font_name_is_bold(self.font)

    @property
    def is_italic(self) -> bool:
        return bool(self.flags & ITALIC_FLAG) or _font_name_is_italic(self.font)


def _font_name_is_bold(font: str) -> bool:
    """Проверяет, содержит ли имя шрифта маркер bold."""
    lowered = font.lower().replace("-", "").replace("_", "")
    return any(marker in lowered for marker in ("bold", "heavy", "black", "demibold", "semibold"))


def _font_name_is_italic(font: str) -> bool:
    """Проверяет, содержит ли имя шрифта маркер italic."""
    lowered = font.lower().replace("-", "").replace("_", "")
    return any(marker in lowered for marker in ("italic", "oblique", "inclined"))


def should_normalize_bold(spans: Sequence[SpanInfo]) -> bool:
    """
    Определяет, нужно ли нормализовать bold для страницы.
    Если > 40% текста bold — это скорее всего артефакт скана.

    Args:
        spans: Последовательность SpanInfo с одной страницы.

    Returns:
        True если bold нужно нормализовать.
    """
    if not spans:
        return False

    total_chars = 0
    bold_chars = 0

    for span in spans:
        length = len(span.text.strip())
        total_chars += length
        if span.is_bold:
            bold_chars += length

    if total_chars < 50:
        return False

    bold_ratio = bold_chars / total_chars
    return bold_ratio > 0.40


def normalize_bold_flags(flags: int, font_name: str, should_normalize: bool) -> int:
    """
    Нормализует флаги для сканированных документов.
    Убирает фальшивый bold, если задетектирован артефакт.

    Args:
        flags: Оригинальные флаги span.
        font_name: Имя шрифта.
        should_normalize: True если нужно убирать bold.

    Returns:
        Скорректированные флаги.
    """
    if not should_normalize:
        return flags

    # Убираем bold flag
    return flags & ~BOLD_FLAG


# ──────────────────────────────────────────────
# 3. Kerning / span merge
# ──────────────────────────────────────────────

def repair_kerning_spans(spans: list[SpanInfo], expected_space_width: float = 0.0) -> list[SpanInfo]:
    """
    Склеивает разорванные spans (когда PDF разбивает одно слово на части из-за кернинга).

    Args:
        spans: Spans одной текстовой строки.
        expected_space_width: Ожидаемая ширина пробела (вычисляется из размера шрифта).

    Returns:
        Склеенные spans.
    """
    if len(spans) <= 1:
        return spans

    merged: list[SpanInfo] = [spans[0]]

    for span in spans[1:]:
        prev = merged[-1]

        # Оцениваем ожидаемую ширину пробела
        if expected_space_width <= 0:
            space_w = prev.size * 0.25  # ~25% размера шрифта = ширина пробела
        else:
            space_w = expected_space_width

        # Горизонтальный gap между spans
        gap = span.bbox[0] - prev.bbox[2]

        # Условия для склеивания:
        # 1. Тот же шрифт и размер (или очень похожий)
        # 2. Gap меньше ширины пробела (кернинг)
        # 3. Spans на одной линии (вертикально)
        same_font = (prev.font == span.font)
        same_size = abs(prev.size - span.size) < 0.5
        small_gap = (-1.0 < gap < space_w * 0.3)
        same_line = abs(prev.bbox[1] - span.bbox[1]) < 2.0

        if same_font and same_size and small_gap and same_line:
            # Склеиваем: объединяем текст, расширяем bbox
            new_bbox = (
                prev.bbox[0],
                min(prev.bbox[1], span.bbox[1]),
                span.bbox[2],
                max(prev.bbox[3], span.bbox[3]),
            )
            merged[-1] = SpanInfo(
                text=prev.text + span.text,
                font=prev.font,
                size=prev.size,
                flags=prev.flags,
                bbox=new_bbox,
                color=prev.color,
            )
        else:
            merged.append(span)

    return merged


# ──────────────────────────────────────────────
# 4. Unicode normalization
# ──────────────────────────────────────────────

# Полноширинные символы → ASCII
FULLWIDTH_ASCII_OFFSET = 0xFEE0  # 'Ａ' (U+FF21) - 'A' (0x41) = 0xFEE0


def normalize_unicode(text: str) -> str:
    """
    Нормализует Unicode текст.

    - NFC нормализация (разложенные символы → составные)
    - Полноширинные символы → ASCII
    - Различные виды тире → стандартные
    - Различные виды кавычек → стандартные
    """
    if not text:
        return text

    # NFC нормализация
    text = unicodedata.normalize("NFC", text)

    # Полноширинные ASCII → обычные
    result = []
    for char in text:
        code = ord(char)
        # Fullwidth ASCII (U+FF01 — U+FF5E)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - FULLWIDTH_ASCII_OFFSET))
        else:
            result.append(char)
    text = "".join(result)

    # Различные тире → стандартные
    text = text.replace("\u2012", "–")  # figure dash → en dash
    text = text.replace("\u2013", "–")  # en dash
    text = text.replace("\u2014", "—")  # em dash
    text = text.replace("\u2015", "—")  # horizontal bar → em dash
    text = text.replace("\u2010", "-")  # hyphen
    text = text.replace("\u2011", "-")  # non-breaking hyphen
    text = text.replace("\uFE58", "—")  # small em dash
    text = text.replace("\uFE63", "-")  # small hyphen-minus

    # Различные пробелы → обычный
    for space_char in "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000":
        text = text.replace(space_char, " ")

    # Zero-width символы → удалить
    for zw_char in "\u200B\u200C\u200D\uFEFF":
        text = text.replace(zw_char, "")

    return text


# ──────────────────────────────────────────────
# 5. Комбинированная функция
# ──────────────────────────────────────────────

def full_text_repair(text: str, font_name: str = "") -> str:
    """
    Применяет все текстовые исправления последовательно.

    Args:
        text: Исходный текст.
        font_name: Имя шрифта (опционально).

    Returns:
        Полностью исправленный текст.
    """
    text = repair_encoding(text, font_name)
    text = normalize_unicode(text)
    return text


# ──────────────────────────────────────────────
# 6. Scan-specific heuristics
# ──────────────────────────────────────────────

def estimate_text_quality(text: str) -> float:
    """
    Быстрая оценка качества текста (0.0–1.0).
    Полезна для определения, стоит ли использовать текстовый рендеринг.

    Args:
        text: Текст для оценки.

    Returns:
        Оценка от 0.0 (мусор) до 1.0 (чистый текст).
    """
    if not text or len(text.strip()) < 5:
        return 0.0

    stripped = text.strip()
    total = len(stripped)

    # Считаем "хорошие" символы (буквы, цифры, базовая пунктуация, пробелы)
    good_chars = sum(
        1 for c in stripped
        if c.isalpha() or c.isdigit() or c in " .,;:!?-–—()[]{}\"'«»\n\t"
    )

    # Считаем Unicode "мусор" (PUA, control, unassigned)
    garbage = sum(
        1 for c in stripped
        if unicodedata.category(c) in ("Co", "Cc", "Cn", "Cf") and c not in "\n\r\t"
    )

    # Средняя длина слова (мусор обычно даёт ~1-2 символа)
    words = stripped.split()
    avg_word_len = sum(len(w) for w in words) / max(len(words), 1) if words else 0

    # Оценка
    char_quality = good_chars / total if total else 0
    garbage_penalty = garbage / total if total else 0
    word_quality = min(1.0, avg_word_len / 4.0)  # идеально ~4+ символов/слово

    score = char_quality * 0.5 + word_quality * 0.3 - garbage_penalty * 0.5

    return max(0.0, min(1.0, score))
