from __future__ import annotations

import re

import fitz

from pdf2epubx.cleanup import clean_text_post_processing_full
from pdf2epubx.epub_writer import EpubWriter
from pdf2epubx.models import ClassifiedBlock, PageContent, RawBlock
from pdf2epubx.profiles import ConversionProfile
from pdf2epubx.utils import html_escape, normalize_line, repair_hyphenation, safe_filename_fragment
from pdf2epubx.code_repair import repair_code_text
from pdf2epubx.edit_rules import EditRules
from pdf2epubx.quality_scorer import score_page_quality


class HtmlRenderer:
    def __init__(
        self,
        profile: ConversionProfile,
        writer: EpubWriter,
        edit_rules: EditRules,
        header_height: float = 50.0,
        footer_height: float = 45.0,
        preserve_images: bool = True,
        skip_printed_toc: bool = False,
        aggressive_level: str = "Medium",
        preserve_figure_references: bool = False,
        auto_quality_fallback: bool = False,
    ) -> None:
        self.profile = profile
        self.writer = writer
        self.edit_rules = edit_rules
        self.header_height = header_height
        self.footer_height = footer_height
        self.preserve_images = preserve_images
        self.skip_printed_toc = skip_printed_toc
        self.aggressive_level = aggressive_level
        self.preserve_figure_references = preserve_figure_references
        self.auto_quality_fallback = auto_quality_fallback

        # Статистика quality для лога
        self.quality_stats: list[tuple[int, float, str]] = []  # (page_number, score, strategy)

    def render_pdf_page_as_facsimile(self, page: fitz.Page, page_number: int) -> str:
        matrix = fitz.Matrix(2.0, 2.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image_bytes = pixmap.tobytes("png")
        file_name = self.writer.add_image_bytes(image_bytes=image_bytes, ext="png", file_name_prefix=f"page_{page_number:04d}_facsimile")
        src = "../" + file_name
        return "\n".join([
            f'<section class="pdf-page facsimile-page" id="page-{page_number}">',
            "<figure>",
            f'<img src="{html_escape(src)}" alt="Rendered page {page_number}"/>',
            "</figure>",
            "</section>",
        ])

    def render_page(self, pdf_page: fitz.Page, page: PageContent, blocks: list[ClassifiedBlock]) -> str:
        if self.profile.force_facsimile:
            return self.render_pdf_page_as_facsimile(pdf_page, page.page_number)

        # Quality-based fallback: оцениваем качество и решаем стратегию
        if self.auto_quality_fallback and self.profile.fallback_render_low_confidence_pages:
            quality = score_page_quality(page)
            self.quality_stats.append((page.page_number, quality.score, quality.strategy))

            if quality.strategy == "facsimile":
                return self.render_pdf_page_as_facsimile(pdf_page, page.page_number)
            elif quality.strategy == "hybrid":
                return self._render_hybrid_page(pdf_page, page, blocks)

        # Склеиваем фрагментированные параграфы перед рендерингом
        if self.profile.join_paragraph_lines:
            blocks = self._merge_continuation_paragraphs(blocks)

        parts: list[str] = [f'<section class="pdf-page" id="page-{page.page_number}">']
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

    def _render_hybrid_page(self, pdf_page: fitz.Page, page: PageContent, blocks: list[ClassifiedBlock]) -> str:
        """
        Hybrid рендеринг: текст + fallback-изображение для подстраховки.
        Полезно для страниц со средним качеством текста.
        """
        parts: list[str] = [f'<section class="pdf-page hybrid-page" id="page-{page.page_number}">']

        # Склеиваем фрагментированные параграфы
        if self.profile.join_paragraph_lines:
            blocks = self._merge_continuation_paragraphs(blocks)

        # Сначала текстовый контент
        visible_count = 0
        for block in blocks:
            html = self.render_block(page, block)
            if html:
                parts.append(html)
                visible_count += 1

        # Если текст есть, но качество среднее — добавляем изображение как доп. контекст
        if visible_count == 0:
            parts.append(self.render_page_fallback_image(pdf_page, page.page_number))

        parts.append("</section>")
        return "\n".join(parts)

    def render_block(self, page: PageContent, classified: ClassifiedBlock) -> str:
        kind = classified.kind
        raw = classified.raw

        if kind in {"header", "footer", "unknown"}:
            return ""

        if not self.preserve_images and kind in {"image", "caption"}:
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
            # Всегда ремонтируем переносы — не только для aggressive профилей
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
        text = repair_code_text(text, repair_git_spacing=self.edit_rules.code.repair_git_spacing)
        return f"<pre><code>{html_escape(text)}</code></pre>"

    def render_table(self, block: RawBlock) -> str:
        """Рендерит таблицу."""
        lines = self.block_lines_preserve(block)
        text = "\n".join(lines).rstrip()
        if not text:
            return ""

        # Пробуем распарсить как HTML таблицу
        from pdf2epubx.table_parser import TableParser, render_table_html, render_table_fallback

        parser = TableParser(mode="smart")
        parsed_table = parser.parse_block(block)

        if parsed_table and parsed_table.confidence > 0.6:
            # Рендерим как настоящую HTML таблицу
            return render_table_html(parsed_table, block)
        else:
            # Fallback на <pre>
            return render_table_fallback(block)

    def render_caption(self, block: RawBlock) -> str:
        text = self.block_text_joined(block)
        if not text:
            return ""
        return f'<p class="caption">{html_escape(text)}</p>'

    def render_image_block(self, page: PageContent, block: RawBlock) -> str:
        if not self.preserve_images or not self.profile.preserve_images:
            return ""
        if not block.image_bytes:
            return ""
        file_name = self.writer.add_image_bytes(
            image_bytes=block.image_bytes,
            ext=block.image_ext,
            file_name_prefix=f"page_{page.page_number:04d}_image",
        )
        src = "../" + file_name
        return f'<figure><img src="{html_escape(src)}" alt="Image from page {page.page_number}"/></figure>'

    def render_page_fallback_image(self, pdf_page: fitz.Page, page_number: int) -> str:
        matrix = fitz.Matrix(2.0, 2.0)
        pixmap = pdf_page.get_pixmap(matrix=matrix, alpha=False)
        image_bytes = pixmap.tobytes("png")
        file_name = self.writer.add_image_bytes(
            image_bytes=image_bytes,
            ext="png",
            file_name_prefix=f"page_{page_number:04d}_fallback",
        )
        src = "../" + file_name
        return f'<figure class="page-fallback"><img src="{html_escape(src)}" alt="Rendered fallback page {page_number}"/></figure>'

    def block_text_joined(self, block: RawBlock) -> str:
        lines = self.block_lines(block)
        if not lines:
            return ""
        text = self._join_lines_with_hyphen_repair(lines)
        text = clean_text_post_processing_full(text, self.aggressive_level, self.preserve_figure_references)
        return normalize_line(text)

    def block_lines(self, block: RawBlock, apply_cleanup: bool = True) -> list[str]:
        """Извлекает строки текста из блока.

        Args:
            block: Текстовый блок.
            apply_cleanup: Если True — применяет post-processing cleanup.
                           False — только normalize_line (для code/table).
        """
        result: list[str] = []
        for line in block.lines:
            text = normalize_line("".join(span.text for span in line.spans))
            if text:
                if apply_cleanup:
                    text = clean_text_post_processing_full(text, self.aggressive_level, self.preserve_figure_references)
                result.append(text)
        return result

    def block_lines_preserve(self, block: RawBlock) -> list[str]:
        """Извлекает строки текста из блока без cleanup (для code/table)."""
        return self.block_lines(block, apply_cleanup=False)

    @staticmethod
    def _join_lines_with_hyphen_repair(lines: list[str]) -> str:
        """Склеивает строки блока, ремонтируя дефисные переносы на стыках.

        Обрабатывает:
        - "компью-" + "тер" → "компьютер" (дефисный перенос)
        - "компью- " + "тер" → "компьютер" (дефис с пробелом)
        - Обычные строки склеиваются через пробел
        """
        if not lines:
            return ""
        result = lines[0]
        for line in lines[1:]:
            if not line:
                result += " "
                continue
            stripped_result = result.rstrip()
            # Дефисный перенос: "компью-" + "тер" → "компьютер"
            if stripped_result.endswith("-") and line and line[0].islower():
                result = stripped_result[:-1] + line
            else:
                result += " " + line
        return result

    def get_quality_summary(self) -> dict:
        """Возвращает сводку по качеству страниц."""
        if not self.quality_stats:
            return {"total_scored": 0}

        scores = [s[1] for s in self.quality_stats]
        strategies = [s[2] for s in self.quality_stats]

        return {
            "total_scored": len(self.quality_stats),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "text_pages": strategies.count("text"),
            "hybrid_pages": strategies.count("hybrid"),
            "facsimile_pages": strategies.count("facsimile"),
        }

    # ──────────────────────────────────────────────────────────────
    # Слияние фрагментированных параграфов (cross-block merging)
    # ──────────────────────────────────────────────────────────────

    def _merge_continuation_paragraphs(self, blocks: list[ClassifiedBlock]) -> list[ClassifiedBlock]:
        """Объединяет смежные параграфные блоки, которые являются частями одного абзаца.

        PyMuPDF часто разбивает один визуальный абзац на несколько RawBlock.
        Результат без merge:
            <p>Эволюция компьютерных</p>
            <p>сетей</p>
        После merge:
            <p>Эволюция компьютерных сетей</p>
        """
        if len(blocks) < 2:
            return blocks

        merged: list[ClassifiedBlock] = [blocks[0]]

        for block in blocks[1:]:
            prev = merged[-1]

            if (prev.kind == "paragraph" and block.kind == "paragraph"
                    and self._should_merge_paragraph_blocks(prev, block)):
                # Объединяем TextLines обоих блоков
                combined_lines = list(prev.raw.lines) + list(block.raw.lines)
                combined_bbox = (
                    min(prev.raw.bbox[0], block.raw.bbox[0]),
                    min(prev.raw.bbox[1], block.raw.bbox[1]),
                    max(prev.raw.bbox[2], block.raw.bbox[2]),
                    max(prev.raw.bbox[3], block.raw.bbox[3]),
                )
                merged_raw = RawBlock(
                    kind="text",
                    bbox=combined_bbox,
                    lines=combined_lines,
                )
                merged[-1] = ClassifiedBlock(
                    raw=merged_raw,
                    kind="paragraph",
                    reason=f"merged: {prev.reason} + continuation",
                )
            else:
                merged.append(block)

        return merged

    def _should_merge_paragraph_blocks(self, prev: ClassifiedBlock, curr: ClassifiedBlock) -> bool:
        """Определяет, нужно ли объединять два соседних параграфных блока.

        Условия для слияния:
        - Предыдущий текст НЕ заканчивается терминальной пунктуацией (.!?;:)
        - Текущий текст начинается со строчной буквы или символа-продолжения
        - Блоки вертикально близки друг к другу
        """
        prev_text = self._quick_block_text(prev.raw)
        curr_text = self._quick_block_text(curr.raw)

        if not prev_text or not curr_text:
            return False

        prev_stripped = prev_text.rstrip()
        curr_stripped = curr_text.strip()

        if not curr_stripped:
            return False

        # Не склеиваем, если предыдущий заканчивается на терминальную пунктуацию
        if re.search(r'[.!?;:\u00bb"\u201d]\s*$', prev_stripped):
            return False

        # Не склеиваем, если текущий блок начинается с заглавной буквы
        # (скорее всего новый абзац или заголовок)
        if curr_stripped[0].isupper():
            return False

        # Не склеиваем, если текущий начинается с маркера списка
        if curr_stripped[0] in '\u2022\u2013\u2014' or re.match(r'^\d+[.)\s]', curr_stripped):
            return False

        # Вертикальная близость: gap между блоками не должен быть слишком большим
        # (больше 2x высоты строки = скорее всего разные абзацы)
        prev_bottom = prev.raw.bbox[3]
        curr_top = curr.raw.bbox[1]
        vertical_gap = curr_top - prev_bottom

        # Оценка высоты строки по bbox предыдущего блока
        if prev.raw.lines:
            prev_line_height = max(
                (line.bbox[3] - line.bbox[1]) for line in prev.raw.lines
            )
        else:
            prev_line_height = 14.0  # fallback

        # Gap > 2x высоты строки — скорее всего разные абзацы
        if vertical_gap > prev_line_height * 2.0:
            return False

        # Склеиваем если текущий начинается со строчной или символа-продолжения
        if curr_stripped[0].islower():
            return True

        if curr_stripped[0] in '(\u00ab\u201c\u2014\u2013':
            return True

        return False

    @staticmethod
    def _quick_block_text(block: RawBlock) -> str:
        """Быстрое извлечение текста из блока без cleanup (для принятия решений о merge)."""
        parts: list[str] = []
        for line in block.lines:
            line_text = "".join(span.text for span in line.spans).strip()
            if line_text:
                parts.append(line_text)
        return " ".join(parts)