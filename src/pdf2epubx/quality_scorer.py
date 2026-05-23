"""
Модуль оценки качества извлечённого текста.
Определяет, использовать ли текстовый рендеринг или fallback на изображение.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from pdf2epubx.models import PageContent, RawBlock


@dataclass(frozen=True)
class PageQuality:
    """Результат оценки качества страницы."""
    page_number: int
    score: float                    # 0.0 (мусор) — 1.0 (идеальный текст)
    total_chars: int
    good_chars: int
    garbage_chars: int
    avg_word_length: float
    word_count: int
    strategy: Literal["text", "hybrid", "facsimile"]
    reasons: list[str]


def score_page_quality(page: PageContent) -> PageQuality:
    """
    Оценивает качество извлечённого текста на странице.

    Args:
        page: Контент страницы.

    Returns:
        PageQuality с оценкой и рекомендуемой стратегией.
    """
    text_blocks = [b for b in page.blocks if b.kind == "text"]
    image_blocks = [b for b in page.blocks if b.kind == "image"]

    if not text_blocks:
        if image_blocks:
            return PageQuality(
                page_number=page.page_number,
                score=0.0,
                total_chars=0,
                good_chars=0,
                garbage_chars=0,
                avg_word_length=0.0,
                word_count=0,
                strategy="facsimile",
                reasons=["Нет текстовых блоков, только изображения"],
            )
        return PageQuality(
            page_number=page.page_number,
            score=0.0,
            total_chars=0,
            good_chars=0,
            garbage_chars=0,
            avg_word_length=0.0,
            word_count=0,
            strategy="facsimile",
            reasons=["Пустая страница"],
        )

    # Собираем весь текст страницы
    all_text = _extract_all_text(text_blocks)

    if not all_text.strip():
        return PageQuality(
            page_number=page.page_number,
            score=0.0,
            total_chars=0,
            good_chars=0,
            garbage_chars=0,
            avg_word_length=0.0,
            word_count=0,
            strategy="facsimile",
            reasons=["Текст пустой после извлечения"],
        )

    total_chars = len(all_text.strip())
    reasons: list[str] = []

    # 1. Считаем хорошие символы
    good_chars = sum(
        1 for c in all_text
        if c.isalpha() or c.isdigit() or c in " .,;:!?-–—()[]{}\"'«»\n\t/\\@#$%&*+=<>"
    )

    # 2. Считаем мусорные символы
    garbage_chars = sum(
        1 for c in all_text
        if unicodedata.category(c) in ("Co", "Cc", "Cn") and c not in "\n\r\t"
    )

    # 3. Анализ слов
    words = all_text.split()
    word_count = len(words)
    avg_word_length = sum(len(w) for w in words) / max(word_count, 1) if words else 0.0

    # Считаем "реальные" слова (3+ символов, содержат буквы)
    real_words = [w for w in words if len(w) >= 3 and any(c.isalpha() for c in w)]
    real_word_ratio = len(real_words) / max(word_count, 1)

    # 4. Оценки по компонентам
    char_quality = good_chars / max(total_chars, 1)
    garbage_penalty = min(garbage_chars / max(total_chars, 1) * 3.0, 1.0)
    word_quality = min(avg_word_length / 4.5, 1.0)
    real_word_quality = real_word_ratio

    # 5. Проверки на специфические проблемы

    # Слишком много заглавных (OCR мусор)
    upper_chars = sum(1 for c in all_text if c.isupper())
    alpha_chars = sum(1 for c in all_text if c.isalpha())
    if alpha_chars > 20:
        upper_ratio = upper_chars / alpha_chars
        if upper_ratio > 0.6:
            reasons.append(f"Слишком много заглавных: {upper_ratio:.0%}")
            char_quality *= 0.7

    # Слишком короткие "слова" (мусор)
    if avg_word_length < 2.0 and word_count > 10:
        reasons.append(f"Очень короткие слова: avg={avg_word_length:.1f}")
        word_quality *= 0.5

    # Много повторяющихся символов (OCR артефакты)
    repeated_pattern = re.findall(r"(.)\1{4,}", all_text)
    if len(repeated_pattern) > 3:
        reasons.append(f"Повторяющиеся символы: {len(repeated_pattern)} шт")
        char_quality *= 0.8

    # Очень мало текста на странице (< 30 символов)
    if total_chars < 30:
        reasons.append(f"Очень мало текста: {total_chars} символов")
        # Если есть изображения — вероятно page-as-image
        if image_blocks:
            return PageQuality(
                page_number=page.page_number,
                score=0.2,
                total_chars=total_chars,
                good_chars=good_chars,
                garbage_chars=garbage_chars,
                avg_word_length=avg_word_length,
                word_count=word_count,
                strategy="facsimile",
                reasons=reasons,
            )

    # 6. Итоговый score
    score = (
        char_quality * 0.35
        + word_quality * 0.20
        + real_word_quality * 0.25
        - garbage_penalty * 0.20
    )
    score = max(0.0, min(1.0, score))

    if garbage_chars > total_chars * 0.15:
        reasons.append(f"Много мусора: {garbage_chars}/{total_chars}")

    # 7. Определяем стратегию
    strategy = decide_strategy(score)

    if not reasons:
        if score > 0.7:
            reasons.append("Хорошее качество текста")
        elif score > 0.3:
            reasons.append("Среднее качество, рекомендуется hybrid")
        else:
            reasons.append("Плохое качество, рекомендуется facsimile")

    return PageQuality(
        page_number=page.page_number,
        score=score,
        total_chars=total_chars,
        good_chars=good_chars,
        garbage_chars=garbage_chars,
        avg_word_length=avg_word_length,
        word_count=word_count,
        strategy=strategy,
        reasons=reasons,
    )


def decide_strategy(score: float) -> Literal["text", "hybrid", "facsimile"]:
    """
    Определяет стратегию рендеринга по score.

    Args:
        score: Оценка качества (0.0–1.0).

    Returns:
        Стратегия рендеринга.
    """
    if score > 0.7:
        return "text"
    if score > 0.3:
        return "hybrid"
    return "facsimile"


def _extract_all_text(blocks: list[RawBlock]) -> str:
    """Извлекает весь текст из блоков."""
    parts: list[str] = []

    for block in blocks:
        if block.kind != "text":
            continue
        for line in block.lines:
            line_text = "".join(span.text for span in line.spans)
            if line_text.strip():
                parts.append(line_text)

    return " ".join(parts)
