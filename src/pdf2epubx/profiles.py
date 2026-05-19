from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TableMode = Literal["text", "image", "hybrid"]


@dataclass(frozen=True)
class ConversionProfile:
    name: str
    description: str

    force_facsimile: bool
    preserve_images: bool
    preserve_code_blocks: bool
    detect_tables: bool
    table_mode: TableMode

    join_paragraph_lines: bool
    aggressive_paragraph_joining: bool
    remove_headers_footers: bool
    detect_headings: bool
    split_by_outline: bool

    fallback_render_empty_pages: bool
    fallback_render_low_confidence_pages: bool


PROFILES: dict[str, ConversionProfile] = {
    "novel": ConversionProfile(
        name="novel",
        description="Fiction and mostly linear books.",
        force_facsimile=False,
        preserve_images=True,
        preserve_code_blocks=False,
        detect_tables=False,
        table_mode="text",
        join_paragraph_lines=True,
        aggressive_paragraph_joining=True,
        remove_headers_footers=True,
        detect_headings=True,
        split_by_outline=True,
        fallback_render_empty_pages=True,
        fallback_render_low_confidence_pages=False,
    ),
    "technical": ConversionProfile(
        name="technical",
        description="Technical books, Linux manuals, programming books, DevOps books.",
        force_facsimile=False,
        preserve_images=True,
        preserve_code_blocks=True,
        detect_tables=True,
        table_mode="hybrid",
        join_paragraph_lines=True,
        aggressive_paragraph_joining=False,
        remove_headers_footers=True,
        detect_headings=True,
        split_by_outline=True,
        fallback_render_empty_pages=True,
        fallback_render_low_confidence_pages=True,
    ),
    "facsimile": ConversionProfile(
        name="facsimile",
        description="Page-as-image EPUB for complex layouts, old scans and visually strict books.",
        force_facsimile=True,
        preserve_images=True,
        preserve_code_blocks=False,
        detect_tables=False,
        table_mode="image",
        join_paragraph_lines=False,
        aggressive_paragraph_joining=False,
        remove_headers_footers=False,
        detect_headings=False,
        split_by_outline=False,
        fallback_render_empty_pages=True,
        fallback_render_low_confidence_pages=True,
    ),
    "hybrid": ConversionProfile(
        name="hybrid",
        description="Semantic extraction with image fallback for problematic pages.",
        force_facsimile=False,
        preserve_images=True,
        preserve_code_blocks=True,
        detect_tables=True,
        table_mode="hybrid",
        join_paragraph_lines=True,
        aggressive_paragraph_joining=False,
        remove_headers_footers=True,
        detect_headings=True,
        split_by_outline=True,
        fallback_render_empty_pages=True,
        fallback_render_low_confidence_pages=True,
    ),
    # === НОВЫЙ ПРОФИЛЬ ДЛЯ КНИГ ПО ПРОГРАММИРОВАНИЮ ===
    "programming": ConversionProfile(
        name="programming",
        description="Books about programming, Python, AI, Telegram bots, code examples (best paragraph joining).",
        force_facsimile=False,
        preserve_images=False,
        preserve_code_blocks=True,
        detect_tables=True,
        table_mode="hybrid",
        join_paragraph_lines=True,
        aggressive_paragraph_joining=True,      # ← главное отличие
        remove_headers_footers=True,
        detect_headings=True,
        split_by_outline=True,
        fallback_render_empty_pages=True,
        fallback_render_low_confidence_pages=True,
    ),
}


def get_profile(profile_name: str) -> ConversionProfile:
    normalized = profile_name.strip().lower()

    if normalized not in PROFILES:
        available = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown profile '{profile_name}'. Available profiles: {available}")

    return PROFILES[normalized]