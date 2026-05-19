from __future__ import annotations

import fitz

from pdf2epubx.epub_writer import EpubWriter
from pdf2epubx.models import ClassifiedBlock, PageContent, RawBlock
from pdf2epubx.profiles import ConversionProfile
from pdf2epubx.utils import html_escape, normalize_line, repair_hyphenation, safe_filename_fragment
from pdf2epubx.code_repair import repair_code_text
from pdf2epubx.edit_rules import EditRules


class HtmlRenderer:
    def __init__(
        self,
        profile: ConversionProfile,
        writer: EpubWriter,
        edit_rules: EditRules,
    ) -> None:
        self.profile = profile
        self.writer = writer
        self.edit_rules = edit_rules

    def render_pdf_page_as_facsimile(
        self,
        page: fitz.Page,
        page_number: int,
    ) -> str:
        matrix = fitz.Matrix(2.0, 2.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image_bytes = pixmap.tobytes("png")

        file_name = self.writer.add_image_bytes(
            image_bytes=image_bytes,
            ext="png",
            file_name_prefix=f"page_{page_number:04d}_facsimile",
        )

        src = "../" + file_name

        return "\n".join(
            [
                f'<section class="pdf-page facsimile-page" id="page-{page_number}">',
                f'<div class="page-marker">Page {page_number}</div>',
                "<figure>",
                f'<img src="{html_escape(src)}" alt="Rendered page {page_number}"/>',
                "</figure>",
                "</section>",
            ]
        )

    def render_page(
        self,
        pdf_page: fitz.Page,
        page: PageContent,
        blocks: list[ClassifiedBlock],
    ) -> str:
        if self.profile.force_facsimile:
            return self.render_pdf_page_as_facsimile(pdf_page, page.page_number)

        parts: list[str] = [
            f'<section class="pdf-page" id="page-{page.page_number}">',
            f'<div class="page-marker">Page {page.page_number}</div>',
        ]

        visible_count = 0

        for block in blocks:
            html = self.render_block(page, block)

            if html:
                parts.append(html)
                visible_count += 1

        if visible_count == 0 and self.profile.fallback_render_empty_pages:
            parts.append(self.render_page_fallback_image(pdf_page, page.page_number))

        parts.append("</section>")

        return "\n".join(parts)

    def render_block(
        self,
        page: PageContent,
        classified: ClassifiedBlock,
    ) -> str:
        kind = classified.kind
        raw = classified.raw

        if kind in {"header", "footer", "unknown"}:
            return ""

        if kind == "image":
            return self.render_image_block(page, raw)

        if kind == "heading":
            return self.render_heading(raw, classified.level)

        if kind == "code":
            return self.render_code(raw)

        if kind == "table":
            return self.render_table(raw)

        if kind == "caption":
            return self.render_caption(raw)

        if kind == "paragraph":
            return self.render_paragraph(raw)

        return ""

    def render_heading(self, block: RawBlock, level: int) -> str:
        text = self.block_text_joined(block)
        escaped = html_escape(text)

        if level <= 1:
            return f"<h1>{escaped}</h1>"

        if level == 2:
            return f"<h2>{escaped}</h2>"

        return f"<h3>{escaped}</h3>"

    def render_paragraph(self, block: RawBlock) -> str:
        if self.profile.join_paragraph_lines:
            text = self.block_text_joined(block)

            if self.profile.aggressive_paragraph_joining:
                text = repair_hyphenation(text)

            return f"<p>{html_escape(text)}</p>"

        lines = [html_escape(line) for line in self.block_lines(block)]

        if not lines:
            return ""

        return "<p>" + "<br/>".join(lines) + "</p>"

    def render_code(self, block: RawBlock) -> str:
        lines = self.block_lines_preserve(block)
        text = "\n".join(lines).rstrip()

        if not text:
            return ""

        text = repair_code_text(
            text,
            repair_git_spacing=self.edit_rules.code.repair_git_spacing,
        )

        return f"<pre><code>{html_escape(text)}</code></pre>"

    def render_table(self, block: RawBlock) -> str:
        lines = self.block_lines_preserve(block)
        text = "\n".join(lines).rstrip()

        if not text:
            return ""

        text = repair_code_text(
            text,
            repair_git_spacing=False,
        )

        if self.profile.table_mode in {"text", "hybrid"}:
            return f'<pre class="table-text"><code>{html_escape(text)}</code></pre>'

        return ""

    def render_caption(self, block: RawBlock) -> str:
        text = self.block_text_joined(block)

        if not text:
            return ""

        return f'<p class="caption">{html_escape(text)}</p>'

    def render_image_block(self, page: PageContent, block: RawBlock) -> str:
        if not self.profile.preserve_images:
            return ""

        if not block.image_bytes:
            return ""

        file_name = self.writer.add_image_bytes(
            image_bytes=block.image_bytes,
            ext=block.image_ext,
            file_name_prefix=f"page_{page.page_number:04d}_image",
        )

        src = "../" + file_name

        return "\n".join(
            [
                "<figure>",
                f'<img src="{html_escape(src)}" alt="Image from page {page.page_number}"/>',
                "</figure>",
            ]
        )

    def render_page_fallback_image(
        self,
        pdf_page: fitz.Page,
        page_number: int,
    ) -> str:
        matrix = fitz.Matrix(2.0, 2.0)
        pixmap = pdf_page.get_pixmap(matrix=matrix, alpha=False)
        image_bytes = pixmap.tobytes("png")

        file_name = self.writer.add_image_bytes(
            image_bytes=image_bytes,
            ext="png",
            file_name_prefix=f"page_{page_number:04d}_fallback",
        )

        src = "../" + file_name

        return "\n".join(
            [
                '<figure class="page-fallback">',
                f'<img src="{html_escape(src)}" alt="Rendered fallback page {page_number}"/>',
                "</figure>",
            ]
        )

    def block_text_joined(self, block: RawBlock) -> str:
        lines = self.block_lines(block)

        if not lines:
            return ""

        text = " ".join(lines)
        return normalize_line(text)

    def block_lines(self, block: RawBlock) -> list[str]:
        result: list[str] = []

        for line in block.lines:
            text = normalize_line("".join(span.text for span in line.spans))
            if text:
                result.append(text)

        return result

    def block_lines_preserve(self, block: RawBlock) -> list[str]:
        result: list[str] = []

        for line in block.lines:
            text = "".join(span.text for span in line.spans).rstrip()
            if text:
                result.append(text)

        return result