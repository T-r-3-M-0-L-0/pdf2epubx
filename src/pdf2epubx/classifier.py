from __future__ import annotations

import re

from pdf2epubx.code_repair import looks_like_commit_block_text, looks_like_diff_block_text
from pdf2epubx.models import ClassifiedBlock, PageContent, RawBlock
from pdf2epubx.profiles import ConversionProfile
from pdf2epubx.utils import normalize_for_repetition, normalize_line, normalize_spaces


MONOSPACE_MARKERS = (
    "mono",
    "courier",
    "consolas",
    "menlo",
    "monaco",
    "liberationmono",
    "dejavusansmono",
    "nimbusmono",
)


COMMAND_PREFIXES = (
    "$ ",
    "# ",
    "> ",
    "sudo ",
    "su ",
    "cd ",
    "ls ",
    "cat ",
    "less ",
    "more ",
    "grep ",
    "egrep ",
    "fgrep ",
    "awk ",
    "sed ",
    "find ",
    "chmod ",
    "chown ",
    "systemctl ",
    "journalctl ",
    "dnf ",
    "yum ",
    "apt ",
    "apt-get ",
    "pacman ",
    "zypper ",
    "docker ",
    "podman ",
    "kubectl ",
    "ssh ",
    "scp ",
    "rsync ",
    "ip ",
    "ifconfig ",
    "nmcli ",
    "firewall-cmd ",
    "iptables ",
    "nft ",
    "mount ",
    "umount ",
    "tar ",
    "curl ",
    "wget ",
    "vim ",
    "nano ",
    "git ",
)


CAPTION_PREFIXES = (
    "figure ",
    "fig. ",
    "рисунок ",
    "рис. ",
    "table ",
    "таблица ",
)


class BlockClassifier:
    def __init__(
        self,
        profile: ConversionProfile,
        normal_font_size: float,
        repeated_marginal_texts: set[str],
    ) -> None:
        self.profile = profile
        self.normal_font_size = normal_font_size
        self.repeated_marginal_texts = repeated_marginal_texts
        self.heading_threshold = max(normal_font_size * 1.25, normal_font_size + 1.5)

    def classify_page(self, page: PageContent) -> list[ClassifiedBlock]:
        result: list[ClassifiedBlock] = []

        for block in page.blocks:
            result.append(self.classify_block(page, block))

        return result

    def classify_block(self, page: PageContent, block: RawBlock) -> ClassifiedBlock:
        if block.kind == "image":
            return ClassifiedBlock(raw=block, kind="image", reason="PDF image block")

        text = self.block_text(block)

        if not text:
            return ClassifiedBlock(raw=block, kind="unknown", reason="empty text block")

        if self.profile.remove_headers_footers and self.is_repeated_marginal(page, block, text):
            y0 = block.bbox[1]

            if y0 < page.height * 0.5:
                return ClassifiedBlock(raw=block, kind="header", reason="repeated marginal top block")

            return ClassifiedBlock(raw=block, kind="footer", reason="repeated marginal bottom block")

        if self.is_page_number(page, block, text):
            return ClassifiedBlock(raw=block, kind="footer", reason="page number detected")

        if self.is_caption(text):
            return ClassifiedBlock(raw=block, kind="caption", reason="caption prefix detected")

        if self.profile.preserve_code_blocks and self.is_code_block(block):
            return ClassifiedBlock(raw=block, kind="code", reason="code heuristics matched")

        if self.profile.detect_tables and self.is_table_block(block):
            return ClassifiedBlock(raw=block, kind="table", reason="table heuristics matched")

        if self.profile.detect_headings and self.is_heading(block, text):
            level = self.guess_heading_level(block, text)
            return ClassifiedBlock(raw=block, kind="heading", level=level, reason="font-size heading heuristic")

        return ClassifiedBlock(raw=block, kind="paragraph", reason="default text paragraph")

    def block_text(self, block: RawBlock) -> str:
        lines: list[str] = []

        for line in block.lines:
            line_text = normalize_line("".join(span.text for span in line.spans))

            if line_text:
                lines.append(line_text)

        return normalize_spaces(" ".join(lines))

    def block_lines(self, block: RawBlock) -> list[str]:
        result: list[str] = []

        for line in block.lines:
            text = normalize_line("".join(span.text for span in line.spans))

            if text:
                result.append(text)

        return result

    def is_repeated_marginal(self, page: PageContent, block: RawBlock, text: str) -> bool:
        y0 = block.bbox[1]
        y1 = block.bbox[3]

        top_limit = page.height * 0.12
        bottom_limit = page.height * 0.88

        is_top_or_bottom = y1 <= top_limit or y0 >= bottom_limit

        if not is_top_or_bottom:
            return False

        normalized = normalize_for_repetition(text)

        return normalized in self.repeated_marginal_texts

    def is_page_number(self, page: PageContent, block: RawBlock, text: str) -> bool:
        stripped = text.strip()

        # Проверяем не только чистые цифры, но и номера с маркерами
        # Удаляем распространенные маркеры: тире, точки, буллеты, "стр.", "page" и т.п.
        cleaned = re.sub(r'^[\s\-\u2013\u2014\.\u2022\u25e6]*|[\s\-\u2013\u2014\.\u2022\u25e6]*$', '', stripped)
        cleaned = re.sub(r'^(стр\.?|page|p\.?|с\.?)\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if not cleaned.isdigit():
            return False

        if len(cleaned) > 4:
            return False

        y0 = block.bbox[1]
        y1 = block.bbox[3]

        top_limit = page.height * 0.10
        bottom_limit = page.height * 0.90

        return y1 <= top_limit or y0 >= bottom_limit

    def is_caption(self, text: str) -> bool:
        lowered = text.lower().strip()
        return any(lowered.startswith(prefix) for prefix in CAPTION_PREFIXES)

    def is_heading(self, block: RawBlock, text: str) -> bool:
        if len(text) > 180:
            return False

        if len(text.split()) > 18:
            return False

        max_size = self.max_font_size(block)

        if max_size < self.heading_threshold:
            return False

        if text.endswith(".") and len(text.split()) > 7:
            return False

        return True

    def guess_heading_level(self, block: RawBlock, text: str) -> int:
        max_size = self.max_font_size(block)
        stripped = text.strip()

        if re.match(r"^(chapter|part|глава|часть)\s+\d+", stripped, flags=re.IGNORECASE):
            return 1

        if re.match(r"^\d+\.\d+(\.\d+)?\s+", stripped):
            return 2

        if max_size >= self.normal_font_size * 1.8:
            return 1

        if max_size >= self.normal_font_size * 1.45:
            return 2

        return 3

    def is_code_block(self, block: RawBlock) -> bool:
        lines = self.block_lines(block)

        if not lines:
            return False

        text = "\n".join(lines)
        lowered_text = text.lower().lstrip()

        if looks_like_commit_block_text(text):
            return True

        if looks_like_diff_block_text(text):
            return True

        monospace_ratio = self.monospace_span_ratio(block)
        special_density = self.special_character_density(text)
        command_line_count = sum(1 for line in lines if self.looks_like_command_line(line))
        config_line_count = sum(1 for line in lines if self.looks_like_config_line(line))

        if lowered_text.startswith(
            (
                "commit ",
                "merge:",
                "author:",
                "date:",
                "автор:",
                "дата:",
                "diff --git",
                "index ",
                "--- ",
                "+++ ",
                "@@ ",
            )
        ):
            return True

        if monospace_ratio >= 0.60 and len(lines) >= 1:
            return True

        if command_line_count >= 2:
            return True

        if command_line_count >= 1 and len(lines) <= 3:
            return True

        if config_line_count >= 2 and special_density >= 0.08:
            return True

        if lowered_text.startswith(COMMAND_PREFIXES):
            return True

        if len(lines) >= 3 and special_density >= 0.16:
            return True

        return False

    def is_table_block(self, block: RawBlock) -> bool:
        lines = self.block_lines(block)

        if len(lines) < 2:
            return False

        pipe_lines = sum(1 for line in lines if "|" in line)
        multi_space_lines = sum(1 for line in lines if re.search(r"\S\s{2,}\S", line))
        balanced_column_lines = sum(1 for line in lines if len(re.split(r"\s{2,}", line.strip())) >= 3)

        if pipe_lines >= 2:
            return True

        if multi_space_lines >= 3 and balanced_column_lines >= 2:
            return True

        return False

    def looks_like_command_line(self, line: str) -> bool:
        stripped = line.strip()
        lowered = stripped.lower()

        if lowered.startswith(COMMAND_PREFIXES):
            return True

        if re.match(r"^[a-z0-9_.-]+@[a-z0-9_.-]+[:~/$#>]", lowered):
            return True

        if re.match(r"^(sudo\s+)?[a-z0-9_.-]+\s+(-{1,2}[a-z0-9][a-z0-9-]*|/[a-z0-9_.-]+)", lowered):
            return True

        if re.match(r"^git\s+[a-z0-9_.-]+", lowered):
            return True

        return False

    def looks_like_config_line(self, line: str) -> bool:
        stripped = line.strip()

        if not stripped:
            return False

        if re.match(r"^\[[A-Za-z0-9_. -]+\]$", stripped):
            return True

        if re.match(r"^[A-Za-z0-9_.-]+\s*=\s*.+$", stripped):
            return True

        if re.match(r"^[A-Za-z0-9_.-]+\s*:\s*.+$", stripped):
            return True

        if stripped.endswith("{") or stripped == "}":
            return True

        return False

    def monospace_span_ratio(self, block: RawBlock) -> float:
        total_chars = 0
        monospace_chars = 0

        for line in block.lines:
            for span in line.spans:
                text_length = len(span.text)
                total_chars += text_length

                font_name = span.font.lower().replace(" ", "")

                if any(marker in font_name for marker in MONOSPACE_MARKERS):
                    monospace_chars += text_length

        if total_chars == 0:
            return 0.0

        return monospace_chars / total_chars

    def special_character_density(self, text: str) -> float:
        if not text:
            return 0.0

        special_chars = sum(1 for char in text if char in "/\\-_=$#.:;|&><*{}[]()@+")
        return special_chars / len(text)

    def max_font_size(self, block: RawBlock) -> float:
        max_size = 0.0

        for line in block.lines:
            for span in line.spans:
                max_size = max(max_size, span.size)

        return max_size