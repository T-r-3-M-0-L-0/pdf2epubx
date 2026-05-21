from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TableMode = Literal["text", "image", "hybrid"]
ProgrammingLanguage = Literal["General", "Python", "Java", "Golang", "C++", "C#", "C", "PowerShell", "Bash"]


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

    programming_language: ProgrammingLanguage = "General"


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
    "programming": ConversionProfile(
        name="programming",
        description="Books about programming, code examples, Python, Java, Golang, C/C++, etc.",
        force_facsimile=False,
        preserve_images=False,
        preserve_code_blocks=True,
        detect_tables=True,
        table_mode="hybrid",
        join_paragraph_lines=True,
        aggressive_paragraph_joining=True,
        remove_headers_footers=True,
        detect_headings=True,
        split_by_outline=True,
        fallback_render_empty_pages=True,
        fallback_render_low_confidence_pages=True,
        programming_language="General",
    ),
}


def get_profile(profile_name: str, programming_language: ProgrammingLanguage = "General") -> ConversionProfile:
    normalized = profile_name.strip().lower()
    if normalized not in PROFILES:
        available = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown profile '{profile_name}'. Available profiles: {available}")
    profile = PROFILES[normalized]
    if normalized == "programming":
        return ConversionProfile(
            name=profile.name,
            description=profile.description,
            force_facsimile=profile.force_facsimile,
            preserve_images=profile.preserve_images,
            preserve_code_blocks=profile.preserve_code_blocks,
            detect_tables=profile.detect_tables,
            table_mode=profile.table_mode,
            join_paragraph_lines=profile.join_paragraph_lines,
            aggressive_paragraph_joining=profile.aggressive_paragraph_joining,
            remove_headers_footers=profile.remove_headers_footers,
            detect_headings=profile.detect_headings,
            split_by_outline=profile.split_by_outline,
            fallback_render_empty_pages=profile.fallback_render_empty_pages,
            fallback_render_low_confidence_pages=profile.fallback_render_low_confidence_pages,
            programming_language=programming_language,
        )
    return profile