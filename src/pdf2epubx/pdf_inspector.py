from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import statistics

import fitz


@dataclass(frozen=True)
class PdfStats:
    page_count: int
    sampled_pages: int
    total_sampled_text_chars: int
    average_text_chars_per_sampled_page: float
    looks_scanned: bool
    text_quality_score: float = 1.0  # 0.0 (мусор) — 1.0 (чистый текст)


def inspect_pdf(
    input_pdf: Path,
    sample_pages: int = 20,
    scanned_threshold_chars_per_page: int = 25,
) -> PdfStats:
    """
    Анализирует PDF, сканируя страницы РАВНОМЕРНО по документу
    (а не только первые N, которые могут быть обложкой/оглавлением).
    """
    doc = fitz.open(input_pdf)

    try:
        page_count = len(doc)
        sampled = min(page_count, sample_pages)

        # Выбираем страницы равномерно по документу
        if sampled >= page_count:
            indices = list(range(page_count))
        else:
            step = page_count / sampled
            indices = [int(i * step) for i in range(sampled)]
            # Убираем дубликаты и добавляем последнюю страницу
            indices = sorted(set(indices))
            sampled = len(indices)

        total_chars = 0
        good_chars_total = 0
        total_chars_total = 0

        for page_index in indices:
            text = doc[page_index].get_text("text") or ""
            stripped = text.strip()
            total_chars += len(stripped)

            # Оценка качества текста
            for c in stripped:
                total_chars_total += 1
                if c.isalpha() or c.isdigit() or c in " .,;:!?-–—()[]{}\"'«»\n\t":
                    good_chars_total += 1

        average = total_chars / sampled if sampled else 0.0
        looks_scanned = sampled > 0 and average < scanned_threshold_chars_per_page

        # Качество текста: доля хороших символов
        quality = good_chars_total / max(total_chars_total, 1) if total_chars_total > 0 else 0.0

        return PdfStats(
            page_count=page_count,
            sampled_pages=sampled,
            total_sampled_text_chars=total_chars,
            average_text_chars_per_sampled_page=average,
            looks_scanned=looks_scanned,
            text_quality_score=quality,
        )
    finally:
        doc.close()


def collect_font_sizes(doc: fitz.Document, max_pages: int = 30) -> list[float]:
    sizes: list[float] = []

    for page_index in range(min(len(doc), max_pages)):
        page = doc[page_index]
        data = page.get_text("dict", sort=True)

        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text", "")).strip()
                    size = span.get("size")

                    if text and isinstance(size, int | float):
                        sizes.append(float(size))

    return sizes


def median_font_size(doc: fitz.Document, default: float = 11.0) -> float:
    sizes = collect_font_sizes(doc)

    if not sizes:
        return default

    return float(statistics.median(sizes))