from __future__ import annotations

import re


GIT_WORD_REPAIRS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bg\s*i\s*t\b", flags=re.IGNORECASE), "git"),
    (re.compile(r"\bcommi\s*t\b", flags=re.IGNORECASE), "commit"),
    (re.compile(r"\bAutho\s*r\b", flags=re.IGNORECASE), "Author"),
    (re.compile(r"\bАвто\s*р\b", flags=re.IGNORECASE), "Автор"),
    (re.compile(r"\bDat\s*e\b", flags=re.IGNORECASE), "Date"),
    (re.compile(r"\bMerg\s*e\b", flags=re.IGNORECASE), "Merge"),
    (re.compile(r"\bmaste\s*r\b", flags=re.IGNORECASE), "master"),
    (re.compile(r"\borigi\s*n\b", flags=re.IGNORECASE), "origin"),
    (re.compile(r"\bbranc\s*h\b", flags=re.IGNORECASE), "branch"),
    (re.compile(r"\bremot\s*e\b", flags=re.IGNORECASE), "remote"),
    (re.compile(r"\breposit\s*o\s*ry\b", flags=re.IGNORECASE), "repository"),
)


def repair_code_text(text: str, repair_git_spacing: bool = True) -> str:
    lines = text.splitlines()
    repaired_lines = [repair_code_line(line, repair_git_spacing=repair_git_spacing) for line in lines]
    return "\n".join(repaired_lines).rstrip()


def repair_code_line(line: str, repair_git_spacing: bool = True) -> str:
    value = line.rstrip()

    value = value.replace("\u00ad", "")
    value = value.replace("\ufffe", "")
    value = value.replace("￾", "")

    value = re.sub(r"\s+-\s+-", " --", value)
    value = re.sub(r"(?<=\s)-\s+(?=[A-Za-z])", "-", value)
    value = re.sub(r"(?<=\w)\s+\.\s+(?=\w)", ".", value)
    value = re.sub(r"(?<=\w)\s+/\s+(?=\w)", "/", value)
    value = re.sub(r"(?<=\w)\s+:\s+/\s+/", "://", value)

    if repair_git_spacing:
        for pattern, replacement in GIT_WORD_REPAIRS:
            value = pattern.sub(replacement, value)

    value = repair_hash_spacing(value)
    value = repair_option_spacing(value)

    return value


def repair_hash_spacing(value: str) -> str:
    value = re.sub(
        r"\b([0-9a-fA-F]{3,20})\s+([0-9a-fA-F]{3,20})\b",
        lambda match: match.group(1) + match.group(2)
        if len(match.group(1) + match.group(2)) in {7, 8, 12, 16, 20, 40}
        else match.group(0),
        value,
    )

    return value


def repair_option_spacing(value: str) -> str:
    value = re.sub(r"--\s+([A-Za-z][A-Za-z0-9-]+)", r"--\1", value)
    value = re.sub(r"(?<=\s)-\s+([A-Za-z])", r"-\1", value)
    return value


def looks_like_commit_block_text(text: str) -> bool:
    lowered = text.lower()

    commit_hits = sum(
        1
        for marker in (
            "commit ",
            "merge:",
            "author:",
            "автор",
            "date:",
            "diff --git",
            "@@",
            "index ",
            "git log",
            "git show",
        )
        if marker in lowered
    )

    return commit_hits >= 2


def looks_like_diff_block_text(text: str) -> bool:
    lines = text.splitlines()

    diff_markers = 0

    for line in lines:
        stripped = line.strip()

        if stripped.startswith(("diff --git", "index ", "--- ", "+++ ", "@@ ", "+", "-")):
            diff_markers += 1

    return diff_markers >= 3