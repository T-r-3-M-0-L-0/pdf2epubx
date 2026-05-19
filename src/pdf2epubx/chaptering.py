from __future__ import annotations

from dataclasses import dataclass
from collections import Counter

import fitz


@dataclass(frozen=True)
class ChapterPlan:
    title: str
    start_page_index: int
    end_page_index: int


def build_chapter_plan(
    doc: fitz.Document,
    split_by_outline: bool,
    pages_per_chapter: int,
) -> list[ChapterPlan]:
    if pages_per_chapter < 1:
        raise ValueError("pages_per_chapter must be >= 1")

    if split_by_outline:
        outline_plan = build_outline_chapter_plan(doc)

        if outline_plan_is_safe(outline_plan, len(doc)):
            return outline_plan

    return build_fixed_chapter_plan(doc, pages_per_chapter)


def build_outline_chapter_plan(doc: fitz.Document) -> list[ChapterPlan]:
    toc = doc.get_toc(simple=True)

    if not toc:
        return []

    page_count = len(doc)

    raw_entries: list[tuple[int, str, int]] = []

    for level, title, page_number in toc:
        cleaned_title = normalize_chapter_title(title)

        if not cleaned_title:
            continue

        if page_number <= 0:
            continue

        page_index = min(max(page_number - 1, 0), page_count - 1)

        raw_entries.append((int(level), cleaned_title, page_index))

    if not raw_entries:
        return []

    level_one_entries = [
        item
        for item in raw_entries
        if item[0] == 1
    ]

    if len(level_one_entries) >= 2:
        selected_entries = level_one_entries
    else:
        selected_entries = [
            item
            for item in raw_entries
            if item[0] <= 2
        ]

    if not selected_entries:
        return []

    selected_entries = sorted(
        selected_entries,
        key=lambda item: (item[2], item[0], item[1]),
    )

    deduplicated: list[tuple[int, str, int]] = []
    seen_pages: set[int] = set()
    seen_titles_on_page: set[tuple[int, str]] = set()

    for level, title, page_index in selected_entries:
        key = (page_index, title)

        if key in seen_titles_on_page:
            continue

        seen_titles_on_page.add(key)

        if page_index in seen_pages:
            continue

        seen_pages.add(page_index)
        deduplicated.append((level, title, page_index))

    if not deduplicated:
        return []

    if deduplicated[0][2] > 0:
        deduplicated.insert(0, (1, "Start", 0))

    plans: list[ChapterPlan] = []

    for index, (_, title, start_page_index) in enumerate(deduplicated):
        if index + 1 < len(deduplicated):
            end_page_index = deduplicated[index + 1][2]
        else:
            end_page_index = page_count

        if start_page_index >= end_page_index:
            continue

        plans.append(
            ChapterPlan(
                title=title,
                start_page_index=start_page_index,
                end_page_index=end_page_index,
            )
        )

    return plans


def outline_plan_is_safe(
    plans: list[ChapterPlan],
    page_count: int,
) -> bool:
    if not plans:
        return False

    if page_count <= 0:
        return False

    covered_pages = sum(
        max(0, plan.end_page_index - plan.start_page_index)
        for plan in plans
    )

    coverage_ratio = covered_pages / page_count

    if coverage_ratio < 0.80:
        return False

    starts = [plan.start_page_index for plan in plans]
    titles = [plan.title for plan in plans]

    if len(set(starts)) != len(starts):
        return False

    title_counter = Counter(titles)

    most_common_title_count = title_counter.most_common(1)[0][1]

    if len(titles) >= 3 and most_common_title_count / len(titles) > 0.50:
        return False

    for plan in plans:
        if plan.start_page_index < 0:
            return False

        if plan.end_page_index > page_count:
            return False

        if plan.end_page_index <= plan.start_page_index:
            return False

    sorted_plans = sorted(plans, key=lambda plan: plan.start_page_index)

    for previous, current in zip(sorted_plans, sorted_plans[1:]):
        if current.start_page_index < previous.end_page_index:
            return False

    return True


def build_fixed_chapter_plan(
    doc: fitz.Document,
    pages_per_chapter: int,
) -> list[ChapterPlan]:
    page_count = len(doc)
    plans: list[ChapterPlan] = []

    for start in range(0, page_count, pages_per_chapter):
        end = min(start + pages_per_chapter, page_count)
        title = f"Pages {start + 1}-{end}"

        plans.append(
            ChapterPlan(
                title=title,
                start_page_index=start,
                end_page_index=end,
            )
        )

    return plans


def normalize_chapter_title(title: str) -> str:
    cleaned = str(title).strip()

    cleaned = " ".join(cleaned.split())

    if not cleaned:
        return ""

    return cleaned


