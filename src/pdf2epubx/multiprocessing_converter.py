"""
Модуль для многопроцессорной конвертации PDF → EPUB.
Использует multiprocessing для параллельной обработки страниц.
"""

from __future__ import annotations

from multiprocessing import cpu_count
from pathlib import Path
from typing import Callable, Optional, List
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed
import traceback

import fitz

from pdf2epubx.profiles import get_profile, ConversionProfile
from pdf2epubx.edit_rules import load_edit_rules
from pdf2epubx.extractor import PdfExtractor
from pdf2epubx.classifier import BlockClassifier
from pdf2epubx.renderer import HtmlRenderer
from pdf2epubx.epub_writer import EpubWriter
from pdf2epubx.pdf_inspector import inspect_pdf, median_font_size
from pdf2epubx.cleanup import detect_repeated_marginal_texts
from pdf2epubx.chaptering import build_chapter_plan
from pdf2epubx.utils import clean_metadata_value, safe_filename_fragment
from pdf2epubx.logger import create_logger


@dataclass
class PageResult:
    """Результат обработки страницы."""
    page_number: int
    chapter_index: int
    html_content: str
    error: Optional[str] = None


def _process_page_chunk(args: dict) -> List[PageResult]:
    """Обрабатывает chunk страниц в отдельном процессе."""
    results = []

    try:
        pdf_path = Path(args['pdf_path'])
        page_indices = args['page_indices']
        profile_name = args['profile_name']
        edit_rules_path = args.get('edit_rules_path')
        header_height = args.get('header_height', 50.0)
        footer_height = args.get('footer_height', 45.0)
        preserve_images = args.get('preserve_images', True)
        aggressive_level = args.get('aggressive_level', 'Medium')
        programming_language = args.get('programming_language', 'General')
        normalize_scan_bold = args.get('normalize_scan_bold', True)
        auto_quality_fallback = args.get('auto_quality_fallback', True)
        enable_image_preprocessing = args.get('enable_image_preprocessing', False)
        image_prep_mode = args.get('image_prep_mode', 'balanced')

        profile = get_profile(profile_name, programming_language=programming_language)
        edit_rules = load_edit_rules(Path(edit_rules_path) if edit_rules_path else None)

        # Инициализация image preprocessor в worker-процессе
        image_preprocessor = None
        if enable_image_preprocessing:
            try:
                from pdf2epubx.image_preprocessor import ImagePreprocessor, HAS_OPENCV
                if HAS_OPENCV:
                    image_preprocessor = ImagePreprocessor(
                        deskew=(image_prep_mode != 'speed'),
                        denoise=(image_prep_mode != 'speed'),
                        binarize=False,
                        enhance_contrast=True,
                        remove_borders=(image_prep_mode == 'quality'),
                    )
            except ImportError:
                pass

        doc = fitz.open(pdf_path)

        try:
            normal_font_size = median_font_size(doc)
            repeated_marginals = detect_repeated_marginal_texts(doc) if profile.remove_headers_footers else set()

            classifier = BlockClassifier(
                profile=profile,
                normal_font_size=normal_font_size,
                repeated_marginal_texts=repeated_marginals,
            )

            # Определяем, нужна ли нормализация bold (для сканов)
            from pdf2epubx.pdf_inspector import inspect_pdf
            pdf_stats = inspect_pdf(pdf_path)
            effective_normalize_bold = normalize_scan_bold and (
                pdf_stats.looks_scanned or pdf_stats.text_quality_score < 0.5
            )

            extractor = PdfExtractor(
                doc=doc,
                edit_rules=edit_rules,
                preserve_images=preserve_images,
                normalize_scan_bold=effective_normalize_bold,
                image_preprocessor=image_preprocessor,
            )

            writer = EpubWriter(title="temp", author="temp", language="ru", identifier="temp")

            renderer = HtmlRenderer(
                profile=profile,
                writer=writer,
                edit_rules=edit_rules,
                header_height=header_height,
                footer_height=footer_height,
                preserve_images=preserve_images,
                skip_printed_toc=False,
                aggressive_level=aggressive_level,
                preserve_figure_references=False,
                auto_quality_fallback=auto_quality_fallback,
            )

            for page_index in page_indices:
                try:
                    pdf_page = doc[page_index]
                    page_number = page_index + 1

                    page_content = extractor.extract_page(page_index)
                    classified_blocks = classifier.classify_page(page_content)

                    page_html = renderer.render_page(
                        pdf_page=pdf_page,
                        page=page_content,
                        blocks=classified_blocks,
                    )

                    results.append(PageResult(
                        page_number=page_number,
                        chapter_index=args.get('chapter_map', {}).get(page_index, 0),
                        html_content=page_html,
                    ))

                except Exception as page_err:
                    try:
                        pdf_page = doc[page_index]
                        fallback_html = renderer.render_pdf_page_as_facsimile(pdf_page, page_index + 1)
                        results.append(PageResult(
                            page_number=page_index + 1,
                            chapter_index=args.get('chapter_map', {}).get(page_index, 0),
                            html_content=fallback_html,
                            error=str(page_err),
                        ))
                    except Exception as fallback_err:
                        results.append(PageResult(
                            page_number=page_index + 1,
                            chapter_index=args.get('chapter_map', {}).get(page_index, 0),
                            html_content=f'<p class="error-page">[Страница {page_index + 1} не может быть отображена]</p>',
                            error=f"{page_err}; fallback: {fallback_err}",
                        ))

        finally:
            doc.close()

    except Exception as e:
        results.append(PageResult(
            page_number=-1,
            chapter_index=0,
            html_content="",
            error=f"Chunk processing failed: {str(e)}\n{traceback.format_exc()}",
        ))

    return results


def convert_pdf_to_epub_parallel(
    input_pdf: Path,
    output_epub: Path,
    profile_name: str,
    title: str | None = None,
    author: str | None = None,
    language: str = "ru",
    pages_per_chapter: int = 10,
    rules_path: Path | None = None,
    header_height: float = 50.0,
    footer_height: float = 45.0,
    preserve_images: bool = True,
    aggressive_level: str = "Medium",
    programming_language: str = "General",
    num_workers: int | None = None,
    chunk_size: int = 5,
    # Scan handling
    normalize_scan_bold: bool = True,
    auto_quality_fallback: bool = True,
    # Image preprocessing
    enable_image_preprocessing: bool = False,
    image_prep_mode: str = "balanced",
    # OCR
    ocr_mode: str = "auto",
    ocr_language: str = "rus+eng",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Path:
    """
    Конвертация PDF → EPUB с использованием multiprocessing.

    Args:
        input_pdf: Путь к входному PDF
        output_epub: Путь к выходному EPUB
        profile_name: Имя профиля конвертации
        title: Заголовок книги (опционально)
        author: Автор (опционально)
        language: Язык книги
        pages_per_chapter: Страниц на главу
        rules_path: Путь к файлу правил (опционально)
        header_height: Высота области заголовка
        footer_height: Высота области подвала
        preserve_images: Сохранять изображения
        aggressive_level: Уровень агрессивности очистки текста
        programming_language: Язык программирования (для profile='programming')
        num_workers: Количество worker-процессов (по умолчанию = cpu_count())
        chunk_size: Размер chunk страниц для одного процесса
        progress_callback: Callback для прогресса func(current, total, message)

    Returns:
        Путь к созданному EPUB файлу
    """
    logger = create_logger(verbose=True, quiet=False)
    logger.info(f"[Multiprocessing] Начало конвертации: {input_pdf.name}")

    def report_progress(step: int, total: int, msg: str):
        if progress_callback:
            progress_callback(step, total, msg)

    input_pdf = input_pdf.resolve()
    output_epub = output_epub.resolve()

    if num_workers is None:
        num_workers = max(1, cpu_count() - 1)

    logger.info(f"[Multiprocessing] Используем {num_workers} процессов, chunk_size={chunk_size}")

    report_progress(1, 10, "Анализ структуры PDF...")

    pdf_stats = inspect_pdf(input_pdf)
    logger.info(f"Страниц: {pdf_stats.page_count}, Скан: {pdf_stats.looks_scanned}")

    doc = fitz.open(input_pdf)
    total_pages = len(doc)

    try:
        metadata = doc.metadata or {}
        resolved_title = clean_metadata_value(title) or clean_metadata_value(metadata.get("title")) or input_pdf.stem
        resolved_author = clean_metadata_value(author) or clean_metadata_value(metadata.get("author")) or "Unknown author"

        import hashlib
        identifier_seed = f"{input_pdf.name}:{input_pdf.stat().st_size}:{resolved_title}"
        identifier = hashlib.sha256(identifier_seed.encode("utf-8")).hexdigest()

        report_progress(2, 10, "Планирование глав...")
        chapter_plan = build_chapter_plan(
            doc=doc,
            split_by_outline=True,
            pages_per_chapter=pages_per_chapter,
        )

        if not chapter_plan:
            raise RuntimeError("Chapter plan is empty.")

        chapter_map = {}
        for chapter_index, chapter in enumerate(chapter_plan, start=1):
            for page_idx in range(chapter.start_page_index, chapter.end_page_index):
                chapter_map[page_idx] = chapter_index

        all_page_indices = list(range(total_pages))
        chunks = [
            all_page_indices[i:i + chunk_size]
            for i in range(0, len(all_page_indices), chunk_size)
        ]

        logger.info(f"Разбито на {len(chunks)} chunks для обработки")

        chunk_args = []
        for chunk in chunks:
            chunk_args.append({
                'pdf_path': str(input_pdf),
                'page_indices': chunk,
                'profile_name': profile_name,
                'edit_rules_path': str(rules_path) if rules_path else None,
                'header_height': header_height,
                'footer_height': footer_height,
                'preserve_images': preserve_images,
                'aggressive_level': aggressive_level,
                'programming_language': programming_language,
                'chapter_map': chapter_map,
                'normalize_scan_bold': normalize_scan_bold,
                'auto_quality_fallback': auto_quality_fallback,
                'enable_image_preprocessing': enable_image_preprocessing,
                'image_prep_mode': image_prep_mode,
            })

        report_progress(3, 10, f"Параллельная обработка страниц ({num_workers} процессов)...")

        all_results: dict[int, str] = {}
        errors: list[tuple[int, str]] = []

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(_process_page_chunk, args): idx
                      for idx, args in enumerate(chunk_args)}

            completed = 0
            for future in as_completed(futures):
                chunk_idx = futures[future]
                try:
                    chunk_results = future.result(timeout=300)

                    for result in chunk_results:
                        if result.error:
                            errors.append((result.page_number, result.error))
                            logger.warning(f"Страница {result.page_number}: {result.error[:100]}")
                        else:
                            all_results[result.page_number] = result.html_content

                    completed += 1
                    progress = int(3 + (completed / len(chunks)) * 6)
                    report_progress(progress, 10, f"Обработано {completed}/{len(chunks)} chunks")

                except Exception as e:
                    logger.error(f"Chunk {chunk_idx} failed: {e}")
                    errors.append((-1, f"Chunk {chunk_idx}: {e}"))

        logger.info(f"Обработка завершена. Успешно: {len(all_results)}, Ошибок: {len(errors)}")

        report_progress(9, 10, "Сборка EPUB файла...")

        writer = EpubWriter(
            title=resolved_title,
            author=resolved_author,
            language=language,
            identifier=identifier,
        )

        for chapter_index, chapter in enumerate(chapter_plan, start=1):
            chapter_body_parts = [f"<h1>{chapter.title}</h1>"]

            for page_idx in range(chapter.start_page_index, chapter.end_page_index):
                page_number = page_idx + 1
                if page_number in all_results:
                    chapter_body_parts.append(all_results[page_number])

            file_name_fragment = safe_filename_fragment(chapter.title)
            chapter_file_name = f"chapters/chapter_{chapter_index:04d}_{file_name_fragment}.xhtml"

            writer.add_chapter(
                title=chapter.title,
                file_name=chapter_file_name,
                html_body="\n".join(chapter_body_parts),
                language=language,
            )

        writer.write(output_epub)
        logger.info(f"EPUB сохранен: {output_epub}")

        report_progress(10, 10, "Готово!")

        return output_epub

    finally:
        doc.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python multiprocessing_converter.py <input.pdf> <output.epub> [profile]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    profile = sys.argv[3] if len(sys.argv) > 3 else "technical"

    result = convert_pdf_to_epub_parallel(
        input_pdf=input_path,
        output_epub=output_path,
        profile_name=profile,
        num_workers=4,
        chunk_size=5,
    )

    print(f"Конвертация завершена: {result}")