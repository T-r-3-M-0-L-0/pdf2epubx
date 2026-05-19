from __future__ import annotations

import hashlib
import tempfile
import fitz
from pathlib import Path
from pdf2epubx.chaptering import build_chapter_plan
from pdf2epubx.classifier import BlockClassifier
from pdf2epubx.cleanup import detect_repeated_marginal_texts
from pdf2epubx.edit_rules import is_toc_page, load_edit_rules
from pdf2epubx.epub_writer import EpubWriter
from pdf2epubx.extractor import PdfExtractor
from pdf2epubx.ocr import run_ocrmypdf
from pdf2epubx.pdf_inspector import inspect_pdf, median_font_size
from pdf2epubx.profiles import get_profile
from pdf2epubx.renderer import HtmlRenderer
from pdf2epubx.toc_parser import parse_toc_page, render_toc_entries
from pdf2epubx.utils import clean_metadata_value, html_escape, safe_filename_fragment

def convert_pdf_to_epub(
    input_pdf: Path,
    output_epub: Path,
    profile_name: str,
    title: str | None = None,
    author: str | None = None,
    language: str = "ru",
    ocr_mode: str = "auto",
    ocr_language: str = "rus+eng",
    pages_per_chapter: int = 10,
    rules_path: Path | None = None,
    split_by_outline: bool | None = None,
    # === НОВЫЕ ПАРАМЕТРЫ ИЗ GUI ===
    header_height: float = 50.0,
    footer_height: float = 45.0,
    preserve_images: bool = True,
    skip_printed_toc: bool = False,
) -> Path:
    """
    Основная функция конвертации PDF → EPUB.
    Все новые параметры из GUI добавлены с дефолтными значениями.
    """
    input_pdf = input_pdf.resolve()
    output_epub = output_epub.resolve()

    profile = get_profile(profile_name)
    edit_rules = load_edit_rules(rules_path)

    if pages_per_chapter < 1:
        raise ValueError("pages_per_chapter must be >= 1")

    output_epub.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pdf2epubx_") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)

        pdf_stats = inspect_pdf(input_pdf)
        working_pdf = input_pdf

        # OCR
        should_ocr = False
        if ocr_mode == "always":
            should_ocr = True
        elif ocr_mode == "auto" and pdf_stats.looks_scanned:
            should_ocr = True
        elif ocr_mode == "never":
            should_ocr = False

        if should_ocr:
            working_pdf = run_ocrmypdf(
                input_pdf=input_pdf,
                output_dir=tmp_dir,
                ocr_language=ocr_language,
            )

        doc = fitz.open(working_pdf)

        try:
            metadata = doc.metadata or {}

            resolved_title = (
                clean_metadata_value(title)
                or clean_metadata_value(metadata.get("title"))
                or input_pdf.stem
            )

            resolved_author = (
                clean_metadata_value(author)
                or clean_metadata_value(metadata.get("author"))
                or "Unknown author"
            )

            identifier_seed = f"{input_pdf.name}:{input_pdf.stat().st_size}:{resolved_title}"
            identifier = hashlib.sha256(identifier_seed.encode("utf-8")).hexdigest()

            writer = EpubWriter(
                title=resolved_title,
                author=resolved_author,
                language=language,
                identifier=identifier,
            )

            # Передаём новые параметры в extractor и renderer
            extractor = PdfExtractor(
                doc=doc,
                edit_rules=edit_rules,
                preserve_images=preserve_images,      # ← новая передача
            )

            repeated_marginals = (
                detect_repeated_marginal_texts(doc)
                if profile.remove_headers_footers
                else set()
            )

            normal_font_size = median_font_size(doc)

            classifier = BlockClassifier(
                profile=profile,
                normal_font_size=normal_font_size,
                repeated_marginal_texts=repeated_marginals,
            )

            renderer = HtmlRenderer(
                profile=profile,
                writer=writer,
                edit_rules=edit_rules,
                header_height=header_height,          # ← новая передача
                footer_height=footer_height,          # ← новая передача
                preserve_images=preserve_images,      # ← новая передача
                skip_printed_toc=skip_printed_toc,    # ← новая передача
            )

            effective_split_by_outline = (
                profile.split_by_outline
                if split_by_outline is None
                else split_by_outline
            )

            chapter_plan = build_chapter_plan(
                doc=doc,
                split_by_outline=effective_split_by_outline,
                pages_per_chapter=pages_per_chapter,
            )

            if not chapter_plan:
                raise RuntimeError("Chapter plan is empty. No EPUB chapters can be generated.")

            for chapter_index, chapter in enumerate(chapter_plan, start=1):
                chapter_body_parts: list[str] = [
                    f"<h1>{html_escape(chapter.title)}</h1>"
                ]

                for page_index in range(chapter.start_page_index, chapter.end_page_index):
                    pdf_page = doc[page_index]
                    page_number = page_index + 1

                    # Пропуск печатного оглавления
                    if skip_printed_toc and is_toc_page(page_number, edit_rules):
                        continue

                    if is_toc_page(page_number, edit_rules) and edit_rules.toc.mode == "semantic":
                        toc_entries = parse_toc_page(pdf_page)
                        toc_html = render_toc_entries(toc_entries)
                        if toc_html:
                            chapter_body_parts.append(toc_html)
                            continue

                    page_content = extractor.extract_page(page_index)
                    classified_blocks = classifier.classify_page(page_content)

                    page_html = renderer.render_page(
                        pdf_page=pdf_page,
                        page=page_content,
                        blocks=classified_blocks,
                    )

                    chapter_body_parts.append(page_html)

                file_name_fragment = safe_filename_fragment(chapter.title)
                chapter_file_name = f"chapters/chapter_{chapter_index:04d}_{file_name_fragment}.xhtml"

                writer.add_chapter(
                    title=chapter.title,
                    file_name=chapter_file_name,
                    html_body="\n".join(chapter_body_parts),
                    language=language,
                )

            writer.write(output_epub)
            return output_epub

        finally:
            doc.close()