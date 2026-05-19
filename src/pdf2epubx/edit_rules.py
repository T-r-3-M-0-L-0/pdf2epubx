from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


CropMode = Literal["points", "ratio"]


@dataclass(frozen=True)
class CropRules:
    mode: CropMode = "ratio"

    top: float = 0.0
    bottom: float = 0.0
    left: float = 0.0
    right: float = 0.0

    top_ratio: float = 0.0
    bottom_ratio: float = 0.0
    left_ratio: float = 0.0
    right_ratio: float = 0.0


@dataclass(frozen=True)
class TocRules:
    mode: str = "auto"
    pages: str = ""
    drop_original_dot_leaders: bool = True


@dataclass(frozen=True)
class HeaderFooterRules:
    remove_repeated: bool = True
    remove_page_numbers: bool = True
    top_ratio: float = 0.12
    bottom_ratio: float = 0.12
    min_repeats: int = 3


@dataclass(frozen=True)
class CodeRules:
    repair_git_spacing: bool = True
    detect_commit_blocks: bool = True
    detect_diff_blocks: bool = True


@dataclass(frozen=True)
class ExcludeRegion:
    pages: str
    rect: tuple[float, float, float, float]


@dataclass(frozen=True)
class EditRules:
    crop: CropRules = field(default_factory=CropRules)
    toc: TocRules = field(default_factory=TocRules)
    headers_footers: HeaderFooterRules = field(default_factory=HeaderFooterRules)
    code: CodeRules = field(default_factory=CodeRules)
    exclude_regions: list[ExcludeRegion] = field(default_factory=list)


def load_edit_rules(path: Path | None) -> EditRules:
    if path is None:
        return EditRules()

    if not path.exists():
        raise FileNotFoundError(f"Rules file does not exist: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    crop_raw = raw.get("crop", {})
    toc_raw = raw.get("toc", {})
    hf_raw = raw.get("headers_footers", {})
    code_raw = raw.get("code", {})

    crop_mode = str(crop_raw.get("mode", "ratio")).strip().lower()

    if crop_mode not in {"points", "ratio"}:
        raise ValueError("crop.mode must be either 'points' or 'ratio'")

    regions: list[ExcludeRegion] = []

    for item in raw.get("exclude_regions", []):
        rect_raw = item.get("rect", [0, 0, 0, 0])

        if len(rect_raw) != 4:
            raise ValueError(f"Invalid exclude region rect: {rect_raw}")

        regions.append(
            ExcludeRegion(
                pages=str(item.get("pages", "")),
                rect=(
                    float(rect_raw[0]),
                    float(rect_raw[1]),
                    float(rect_raw[2]),
                    float(rect_raw[3]),
                ),
            )
        )

    return EditRules(
        crop=CropRules(
            mode=crop_mode,  # type: ignore[arg-type]

            top=float(crop_raw.get("top", 0.0)),
            bottom=float(crop_raw.get("bottom", 0.0)),
            left=float(crop_raw.get("left", 0.0)),
            right=float(crop_raw.get("right", 0.0)),

            top_ratio=float(crop_raw.get("top_ratio", 0.0)),
            bottom_ratio=float(crop_raw.get("bottom_ratio", 0.0)),
            left_ratio=float(crop_raw.get("left_ratio", 0.0)),
            right_ratio=float(crop_raw.get("right_ratio", 0.0)),
        ),
        toc=TocRules(
            mode=str(toc_raw.get("mode", "auto")),
            pages=str(toc_raw.get("pages", "")),
            drop_original_dot_leaders=bool(toc_raw.get("drop_original_dot_leaders", True)),
        ),
        headers_footers=HeaderFooterRules(
            remove_repeated=bool(hf_raw.get("remove_repeated", True)),
            remove_page_numbers=bool(hf_raw.get("remove_page_numbers", True)),
            top_ratio=float(hf_raw.get("top_ratio", 0.12)),
            bottom_ratio=float(hf_raw.get("bottom_ratio", 0.12)),
            min_repeats=int(hf_raw.get("min_repeats", 3)),
        ),
        code=CodeRules(
            repair_git_spacing=bool(code_raw.get("repair_git_spacing", True)),
            detect_commit_blocks=bool(code_raw.get("detect_commit_blocks", True)),
            detect_diff_blocks=bool(code_raw.get("detect_diff_blocks", True)),
        ),
        exclude_regions=regions,
    )


def page_in_range(page_number: int, range_expr: str) -> bool:
    expr = range_expr.strip()

    if not expr:
        return False

    parts = [part.strip() for part in expr.split(",") if part.strip()]

    for part in parts:
        if "-" not in part:
            if part.isdigit() and page_number == int(part):
                return True
            continue

        left, right = part.split("-", 1)
        left = left.strip()
        right = right.strip()

        start = int(left) if left else 1
        end = int(right) if right else 10**9

        if start <= page_number <= end:
            return True

    return False


def is_toc_page(page_number: int, rules: EditRules) -> bool:
    if not rules.toc.pages.strip():
        return False

    return page_in_range(page_number, rules.toc.pages)


def should_exclude_rect(
    page_number: int,
    bbox: tuple[float, float, float, float],
    rules: EditRules,
) -> bool:
    for region in rules.exclude_regions:
        if not page_in_range(page_number, region.pages):
            continue

        if rects_intersect(bbox, region.rect):
            return True

    return False


def rects_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b

    if ax1 <= bx0 or bx1 <= ax0:
        return False

    if ay1 <= by0 or by1 <= ay0:
        return False

    return True


def build_clip_rect(
    page_width: float,
    page_height: float,
    rules: EditRules,
) -> tuple[float, float, float, float]:
    if rules.crop.mode == "points":
        left = rules.crop.left
        top = rules.crop.top
        right = page_width - rules.crop.right
        bottom = page_height - rules.crop.bottom
    else:
        left = page_width * rules.crop.left_ratio
        top = page_height * rules.crop.top_ratio
        right = page_width * (1.0 - rules.crop.right_ratio)
        bottom = page_height * (1.0 - rules.crop.bottom_ratio)

    left = clamp(left, 0.0, page_width)
    right = clamp(right, 0.0, page_width)
    top = clamp(top, 0.0, page_height)
    bottom = clamp(bottom, 0.0, page_height)

    if right <= left:
        left = 0.0
        right = page_width

    if bottom <= top:
        top = 0.0
        bottom = page_height

    return left, top, right, bottom


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))