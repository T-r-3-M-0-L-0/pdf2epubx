from __future__ import annotations

import re
from dataclasses import dataclass

import fitz

from pdf2epubx.utils import html_escape, normalize_spaces


@dataclass(frozen=True)
class TocEntry:
    title: str
    page: int | None
    level: int


DOT_LEADER_RE = re.compile(r"\.{5,}")
PAGE_NUMBER_RE = re.compile(r"(\d{1,4})\s*$")


def is_probably_toc_text(text: str) -> bool:
    lowered = text.lower()
    dot_leaders = len(DOT_LEADER_RE.findall(text))
    has_toc_title = "содержание" in lowered or "оглавление" in lowered or "contents" in lowered
    has_chapters = lowered.count("глава") + lowered.count("раздел") + lowered.count("chapter") + lowered.count("section")

    return has_toc_title or dot_leaders >= 5 or has_chapters >= 8


def parse_toc_page(page: fitz.Page) -> list[TocEntry]:
    text = page.get_text("text", sort=True)
    lines = [normalize_spaces(line) for line in text.splitlines()]
    entries: list[TocEntry] = []

    for line in lines:
        if not line:
            continue

        if line.lower() in {"содержание", "оглавление", "contents"}:
            continue

        entry = parse_toc_line(line)

        if entry is not None:
            entries.append(entry)

    if entries:
        return entries

    return parse_toc_page_from_words(page)


def parse_toc_line(line: str) -> TocEntry | None:
    cleaned = normalize_spaces(line)

    if not cleaned:
        return None

    page_match = PAGE_NUMBER_RE.search(cleaned)
    page_number: int | None = None

    if page_match:
        page_number = int(page_match.group(1))
        cleaned = cleaned[: page_match.start()].rstrip()

    cleaned = DOT_LEADER_RE.sub(" ", cleaned)
    cleaned = normalize_spaces(cleaned)

    if not cleaned:
        return None

    if not looks_like_toc_title(cleaned):
        return None

    level = guess_toc_level(cleaned)

    return TocEntry(
        title=cleaned,
        page=page_number,
        level=level,
    )


def parse_toc_page_from_words(page: fitz.Page) -> list[TocEntry]:
    words = page.get_text("words", sort=True)
    line_map: dict[tuple[int, int], list[tuple[float, str]]] = {}

    for word in words:
        x0, y0, x1, y1, text, block_no, line_no, word_no = word
        line_map.setdefault((int(block_no), int(line_no)), []).append((float(x0), str(text)))

    entries: list[TocEntry] = []

    for _, line_words in sorted(line_map.items()):
        ordered = [text for _, text in sorted(line_words, key=lambda item: item[0])]
        line = normalize_spaces(" ".join(ordered))
        entry = parse_toc_line(line)

        if entry is not None:
            entries.append(entry)

    return entries


def looks_like_toc_title(text: str) -> bool:
    lowered = text.lower()

    if lowered.startswith(("глава ", "раздел ", "chapter ", "section ")):
        return True

    if re.match(r"^\d+(\.\d+)*\s+", text):
        return True

    return False


def guess_toc_level(text: str) -> int:
    lowered = text.lower()

    if lowered.startswith(("глава ", "chapter ")):
        return 1

    if lowered.startswith(("раздел ", "section ")):
        return 2

    if re.match(r"^\d+\.\d+\.\d+", text):
        return 3

    if re.match(r"^\d+\.\d+", text):
        return 2

    return 1


def render_toc_entries(entries: list[TocEntry]) -> str:
    if not entries:
        return ""

    parts: list[str] = [
        '<section class="source-toc">',
        "<h1>Содержание</h1>",
        '<ol class="toc-list">',
    ]

    for entry in entries:
        page_text = "" if entry.page is None else str(entry.page)
        css_class = f"toc-level-{entry.level}"

        parts.append(
            '<li class="' + css_class + '">'
            '<span class="toc-title">' + html_escape(entry.title) + "</span>"
            '<span class="toc-page">' + html_escape(page_text) + "</span>"
            "</li>"
        )

    parts.extend(
        [
            "</ol>",
            "</section>",
        ]
    )

    return "\n".join(parts)