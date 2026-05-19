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


def inspect_pdf(
    input_pdf: Path,
    sample_pages: int = 12,
    scanned_threshold_chars_per_page: int = 25,
) -> PdfStats:
    doc = fitz.open(input_pdf)

    try:
        page_count = len(doc)
        sampled = min(page_count, sample_pages)
        total_chars = 0

        for page_index in range(sampled):
            text = doc[page_index].get_text("text") or ""
            total_chars += len(text.strip())

        average = total_chars / sampled if sampled else 0.0
        looks_scanned = sampled > 0 and average < scanned_threshold_chars_per_page

        return PdfStats(
            page_count=page_count,
            sampled_pages=sampled,
            total_sampled_text_chars=total_chars,
            average_text_chars_per_sampled_page=average,
            looks_scanned=looks_scanned,
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