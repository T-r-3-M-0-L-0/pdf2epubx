from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import fitz

from pdf2epubx.pdf_inspector import inspect_pdf
from pdf2epubx.utils import normalize_for_repetition, normalize_spaces


@dataclass(frozen=True)
class PagePreflight:
    page_number: int
    width: float
    height: float
    text_chars: int
    word_count: int
    image_count: int
    top_text: list[str]
    bottom_text: list[str]
    has_toc_markers: bool
    has_code_markers: bool
    has_dot_leaders: bool


@dataclass(frozen=True)
class CropRecommendation:
    mode: str = "ratio"
    top_ratio: float = 0.07
    bottom_ratio: float = 0.065
    left_ratio: float = 0.0
    right_ratio: float = 0.0


@dataclass(frozen=True)
class HeaderFooterCandidate:
    text: str
    normalized: str
    repeats: int
    area: str


@dataclass(frozen=True)
class PreflightReport:
    input: str
    page_count: int
    sampled_pages: int
    total_sampled_text_chars: int
    average_text_chars_per_sampled_page: float
    looks_scanned: bool
    recommended_profile: str
    recommended_ocr_mode: str
    recommended_crop: CropRecommendation
    toc_candidate_pages: list[int]
    code_candidate_pages: list[int]
    repeated_header_footer_candidates: list[HeaderFooterCandidate]
    page_reports: list[PagePreflight]
    warnings: list[str] = field(default_factory=list)


TOC_MARKERS = (
    "содержание",
    "оглавление",
    "contents",
    "глава ",
    "раздел ",
    "chapter ",
    "section ",
)


CODE_MARKERS = (
    "git ",
    "commit ",
    "merge:",
    "author:",
    "автор:",
    "date:",
    "diff --git",
    "@@ ",
    "index ",
    "git log",
    "git show",
    "git commit",
    "git remote",
    "git checkout",
    "git branch",
    "git rebase",
    "git merge",
    "git pull",
    "git push",
)


DOT_LEADER_RE = re.compile(r"\.{5,}")


def run_preflight(
    input_pdf: Path,
    output_json: Path | None = None,
    max_pages_for_report: int = 40,
    header_footer_sample_pages: int = 80,
) -> PreflightReport:
    input_pdf = input_pdf.resolve()

    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF does not exist: {input_pdf}")

    if input_pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Input file is not a PDF: {input_pdf}")

    pdf_stats = inspect_pdf(input_pdf)

    doc = fitz.open(input_pdf)

    try:
        page_reports = analyze_pages(
            doc=doc,
            max_pages=max_pages_for_report,
        )

        repeated_candidates = find_repeated_header_footer_candidates(
            doc=doc,
            max_pages=header_footer_sample_pages,
        )

        toc_candidate_pages = [
            page.page_number
            for page in page_reports
            if page.has_toc_markers or page.has_dot_leaders
        ]

        code_candidate_pages = [
            page.page_number
            for page in page_reports
            if page.has_code_markers
        ]

        recommended_profile = choose_recommended_profile(
            looks_scanned=pdf_stats.looks_scanned,
            toc_candidate_pages=toc_candidate_pages,
            code_candidate_pages=code_candidate_pages,
            page_reports=page_reports,
        )

        recommended_ocr_mode = "auto" if pdf_stats.looks_scanned else "never"

        warnings = build_warnings(
            looks_scanned=pdf_stats.looks_scanned,
            toc_candidate_pages=toc_candidate_pages,
            code_candidate_pages=code_candidate_pages,
            repeated_candidates=repeated_candidates,
            page_reports=page_reports,
        )

        report = PreflightReport(
            input=str(input_pdf),
            page_count=pdf_stats.page_count,
            sampled_pages=pdf_stats.sampled_pages,
            total_sampled_text_chars=pdf_stats.total_sampled_text_chars,
            average_text_chars_per_sampled_page=pdf_stats.average_text_chars_per_sampled_page,
            looks_scanned=pdf_stats.looks_scanned,
            recommended_profile=recommended_profile,
            recommended_ocr_mode=recommended_ocr_mode,
            recommended_crop=CropRecommendation(),
            toc_candidate_pages=toc_candidate_pages,
            code_candidate_pages=code_candidate_pages,
            repeated_header_footer_candidates=repeated_candidates,
            page_reports=page_reports,
            warnings=warnings,
        )

        if output_json is not None:
            write_preflight_report(report, output_json)

        return report
    finally:
        doc.close()


def analyze_pages(
    doc: fitz.Document,
    max_pages: int,
) -> list[PagePreflight]:
    reports: list[PagePreflight] = []

    page_count = min(len(doc), max_pages)

    for page_index in range(page_count):
        page = doc[page_index]
        page_number = page_index + 1
        rect = page.rect

        text = page.get_text("text", sort=True) or ""
        normalized_text = normalize_spaces(text)
        lowered_text = normalized_text.lower()

        words = page.get_text("words", sort=True)
        images = page.get_images(full=True)

        top_text, bottom_text = extract_top_bottom_text(
            page=page,
            top_ratio=0.12,
            bottom_ratio=0.12,
        )

        has_toc_markers = detect_toc_markers(lowered_text)
        has_code_markers = detect_code_markers(lowered_text)
        has_dot_leaders = bool(DOT_LEADER_RE.search(text))

        reports.append(
            PagePreflight(
                page_number=page_number,
                width=float(rect.width),
                height=float(rect.height),
                text_chars=len(normalized_text),
                word_count=len(words),
                image_count=len(images),
                top_text=top_text,
                bottom_text=bottom_text,
                has_toc_markers=has_toc_markers,
                has_code_markers=has_code_markers,
                has_dot_leaders=has_dot_leaders,
            )
        )

    return reports


def extract_top_bottom_text(
    page: fitz.Page,
    top_ratio: float,
    bottom_ratio: float,
) -> tuple[list[str], list[str]]:
    height = float(page.rect.height)
    top_limit = height * top_ratio
    bottom_limit = height * (1.0 - bottom_ratio)

    top_items: list[str] = []
    bottom_items: list[str] = []

    data = page.get_text("dict", sort=True)

    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue

        bbox = block.get("bbox", (0.0, 0.0, 0.0, 0.0))

        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue

        y0 = float(bbox[1])
        y1 = float(bbox[3])

        text = extract_text_from_block(block)

        if not text:
            continue

        if y1 <= top_limit:
            top_items.append(text)

        if y0 >= bottom_limit:
            bottom_items.append(text)

    return top_items[:8], bottom_items[:8]


def extract_text_from_block(block: dict[str, Any]) -> str:
    lines: list[str] = []

    for line in block.get("lines", []):
        parts: list[str] = []

        for span in line.get("spans", []):
            text = str(span.get("text", ""))

            if text:
                parts.append(text)

        line_text = normalize_spaces("".join(parts))

        if line_text:
            lines.append(line_text)

    return normalize_spaces(" ".join(lines))


def detect_toc_markers(lowered_text: str) -> bool:
    if "содержание" in lowered_text or "оглавление" in lowered_text or "contents" in lowered_text:
        return True

    marker_hits = sum(1 for marker in TOC_MARKERS if marker in lowered_text)

    if marker_hits >= 4:
        return True

    if DOT_LEADER_RE.search(lowered_text):
        return True

    return False


def detect_code_markers(lowered_text: str) -> bool:
    marker_hits = sum(1 for marker in CODE_MARKERS if marker in lowered_text)

    if marker_hits >= 2:
        return True

    if re.search(r"\bgit\s+[a-z0-9_.-]+", lowered_text):
        return True

    if re.search(r"\bcommit\s+[0-9a-f]{7,40}\b", lowered_text):
        return True

    return False


def find_repeated_header_footer_candidates(
    doc: fitz.Document,
    max_pages: int,
    min_repeats: int = 3,
    top_ratio: float = 0.12,
    bottom_ratio: float = 0.12,
) -> list[HeaderFooterCandidate]:
    top_counter: Counter[str] = Counter()
    bottom_counter: Counter[str] = Counter()
    original_by_normalized: dict[str, str] = {}

    page_count = min(len(doc), max_pages)

    for page_index in range(page_count):
        page = doc[page_index]
        top_texts, bottom_texts = extract_top_bottom_text(
            page=page,
            top_ratio=top_ratio,
            bottom_ratio=bottom_ratio,
        )

        for text in top_texts:
            normalized = normalize_for_repetition(text)

            if is_useful_repeated_candidate(normalized):
                top_counter[normalized] += 1
                original_by_normalized.setdefault(normalized, text)

        for text in bottom_texts:
            normalized = normalize_for_repetition(text)

            if is_useful_repeated_candidate(normalized):
                bottom_counter[normalized] += 1
                original_by_normalized.setdefault(normalized, text)

    candidates: list[HeaderFooterCandidate] = []

    for normalized, repeats in top_counter.most_common():
        if repeats >= min_repeats:
            candidates.append(
                HeaderFooterCandidate(
                    text=original_by_normalized.get(normalized, normalized),
                    normalized=normalized,
                    repeats=repeats,
                    area="top",
                )
            )

    for normalized, repeats in bottom_counter.most_common():
        if repeats >= min_repeats:
            candidates.append(
                HeaderFooterCandidate(
                    text=original_by_normalized.get(normalized, normalized),
                    normalized=normalized,
                    repeats=repeats,
                    area="bottom",
                )
            )

    return candidates[:30]


def is_useful_repeated_candidate(normalized: str) -> bool:
    if not normalized:
        return False

    if len(normalized) < 2:
        return False

    if normalized.isdigit():
        return True

    if len(normalized) >= 3:
        return True

    return False


def choose_recommended_profile(
    looks_scanned: bool,
    toc_candidate_pages: list[int],
    code_candidate_pages: list[int],
    page_reports: list[PagePreflight],
) -> str:
    if looks_scanned:
        return "hybrid"

    if code_candidate_pages:
        return "technical"

    if toc_candidate_pages and has_many_images(page_reports):
        return "hybrid"

    return "technical"


def has_many_images(page_reports: list[PagePreflight]) -> bool:
    if not page_reports:
        return False

    total_images = sum(page.image_count for page in page_reports)
    return total_images >= max(8, len(page_reports) // 2)


def build_warnings(
    looks_scanned: bool,
    toc_candidate_pages: list[int],
    code_candidate_pages: list[int],
    repeated_candidates: list[HeaderFooterCandidate],
    page_reports: list[PagePreflight],
) -> list[str]:
    warnings: list[str] = []

    if looks_scanned:
        warnings.append("PDF looks scanned or has a weak text layer. Use OCR mode: auto or always.")

    if toc_candidate_pages:
        warnings.append(
            "TOC-like pages detected. Dot leaders should be converted semantically instead of being preserved as text."
        )

    if code_candidate_pages:
        warnings.append(
            "Code-like pages detected. Use profile technical or hybrid to preserve code blocks."
        )

    if repeated_candidates:
        warnings.append(
            "Repeated header/footer candidates detected. Enable repeated header/footer removal and moderate crop."
        )

    pages_with_low_text = [
        page.page_number
        for page in page_reports
        if page.text_chars < 50 and page.image_count > 0
    ]

    if pages_with_low_text:
        warnings.append(
            "Some pages contain images with little text. Consider OCR or image fallback for these pages: "
            + ", ".join(str(page) for page in pages_with_low_text[:20])
        )

    return warnings


def write_preflight_report(
    report: PreflightReport,
    output_json: Path,
) -> None:
    output_json = output_json.resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(report)

    output_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def print_preflight_summary(report: PreflightReport) -> str:
    lines: list[str] = []

    lines.append(f"Input: {report.input}")
    lines.append(f"Pages: {report.page_count}")
    lines.append(f"Looks scanned: {report.looks_scanned}")
    lines.append(f"Average sampled text chars/page: {report.average_text_chars_per_sampled_page:.1f}")
    lines.append(f"Recommended profile: {report.recommended_profile}")
    lines.append(f"Recommended OCR mode: {report.recommended_ocr_mode}")
    lines.append(
        "Recommended crop: "
        f"top={report.recommended_crop.top_ratio}, "
        f"bottom={report.recommended_crop.bottom_ratio}"
    )

    if report.toc_candidate_pages:
        lines.append(
            "TOC candidate pages: "
            + ", ".join(str(page) for page in report.toc_candidate_pages)
        )

    if report.code_candidate_pages:
        lines.append(
            "Code candidate pages: "
            + ", ".join(str(page) for page in report.code_candidate_pages[:30])
        )

    if report.repeated_header_footer_candidates:
        lines.append("Repeated header/footer candidates:")

        for candidate in report.repeated_header_footer_candidates[:10]:
            lines.append(
                f"  - [{candidate.area}] repeats={candidate.repeats}: {candidate.text}"
            )

    if report.warnings:
        lines.append("Warnings:")

        for warning in report.warnings:
            lines.append(f"  - {warning}")

    return "\n".join(lines)


def build_recommended_rules_json(report: PreflightReport) -> dict[str, Any]:
    toc_pages = collapse_pages_to_range(report.toc_candidate_pages)

    return {
        "crop": {
            "mode": report.recommended_crop.mode,
            "top_ratio": report.recommended_crop.top_ratio,
            "bottom_ratio": report.recommended_crop.bottom_ratio,
            "left_ratio": report.recommended_crop.left_ratio,
            "right_ratio": report.recommended_crop.right_ratio,
        },
        "toc": {
            "mode": "semantic" if toc_pages else "auto",
            "pages": toc_pages,
            "drop_original_dot_leaders": True,
        },
        "headers_footers": {
            "remove_repeated": True,
            "remove_page_numbers": True,
            "top_ratio": 0.12,
            "bottom_ratio": 0.12,
            "min_repeats": 3,
        },
        "code": {
            "repair_git_spacing": True,
            "detect_commit_blocks": True,
            "detect_diff_blocks": True,
        },
        "exclude_regions": [],
    }


def write_recommended_rules_json(
    report: PreflightReport,
    output_json: Path,
) -> None:
    output_json = output_json.resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)

    data = build_recommended_rules_json(report)

    output_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def collapse_pages_to_range(pages: list[int]) -> str:
    if not pages:
        return ""

    unique_pages = sorted(set(pages))
    ranges: list[str] = []

    start = unique_pages[0]
    previous = unique_pages[0]

    for page in unique_pages[1:]:
        if page == previous + 1:
            previous = page
            continue

        ranges.append(format_page_range(start, previous))
        start = page
        previous = page

    ranges.append(format_page_range(start, previous))

    return ",".join(ranges)


def format_page_range(start: int, end: int) -> str:
    if start == end:
        return str(start)

    return f"{start}-{end}"