from __future__ import annotations

import hashlib
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional, Any

import fitz

# Импорт всех необходимых модулей
from pdf2epubx.chaptering import build_chapter_plan
from pdf2epubx.classifier import BlockClassifier
from pdf2epubx.cleanup import detect_repeated_marginal_texts
from pdf2epubx.edit_rules import is_toc_page, load_edit_rules
from pdf2epubx.epub_writer import EpubWriter
from pdf2epubx.extractor import PdfExtractor
from pdf2epubx.ocr import run_ocrmypdf
from pdf2epubx.pdf_inspector import inspect_pdf, median_font_size
from pdf2epubx.profiles import get_profile, ProgrammingLanguage
from pdf2epubx.renderer import HtmlRenderer
from pdf2epubx.toc_parser import parse_toc_page, render_toc_entries
from pdf2epubx.utils import clean_metadata_value, html_escape, safe_filename_fragment
from pdf2epubx.cache import ConversionCache, compute_pdf_cache_key
from pdf2epubx.logger import ConversionLogger, create_logger
from pdf2epubx.epub_validator import validate_epub

# Импорты новых модулей (убедитесь, что они существуют)
try:
    from pdf2epubx.table_parser import TableParser
    HAS_TABLES = True
except ImportError:
    HAS_TABLES = False

try:
    from pdf2epubx.formula_detector import FormulaDetector
    HAS_FORMULAS = True
except ImportError:
    HAS_FORMULAS = False


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
    header_height: float = 50.0,
    footer_height: float = 45.0,
    preserve_images: bool = True,
    skip_printed_toc: bool = False,
    aggressive_level: str = "Medium",
    preserve_figure_references: bool = False,
    programming_language: str = "General",
    # Новые параметры
    cache_enabled: bool = False,
    cache_dir: Path | None = None,
    optimize_images: bool = False,
    image_quality: int = 85,
    image_format: str = "webp",
    validate_output: bool = False,
    verbose: bool = False,
    quiet: bool = False,
    log_file: Path | None = None,
    # Параметры нового функционала
    enable_tables: bool = True,
    enable_formulas: bool = True,
    # Callback для прогресса: func(current_step: int, total_steps: int, message: str)
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Path:
    """
    Основная функция конвертации PDF → EPUB с поддержкой прогресс-бара.
    """
    
    def report_progress(step: int, total: int, msg: str):
        if progress_callback:
            progress_callback(step, total, msg)

    # Инициализация логгера
    logger = create_logger(verbose=verbose, quiet=quiet, log_file=log_file)
    logger.info(f"Начало конвертации: {input_pdf.name}")

    input_pdf = input_pdf.resolve()
    output_epub = output_epub.resolve()

    report_progress(1, 10, "Загрузка профиля и правил...")
    profile = get_profile(profile_name, programming_language=programming_language)
    edit_rules = load_edit_rules(rules_path)

    if pages_per_chapter < 1:
        raise ValueError("pages_per_chapter must be >= 1")

    output_epub.parent.mkdir(parents=True, exist_ok=True)

    # Инициализация кэша
    cache = ConversionCache(cache_dir=cache_dir, enabled=cache_enabled)
    cache_key = None
    if cache_enabled:
        cache_key = compute_pdf_cache_key(input_pdf, {"profile": profile_name, "language": language})
        logger.debug(f"Кэш-ключ: {cache_key[:16] if cache_key else 'none'}...")

    report_progress(2, 10, "Анализ структуры PDF...")
    
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
        
        if should_ocr:
            report_progress(3, 10, "Запуск OCR (это может занять время)...")
            logger.info("Запуск OCR...")
            working_pdf = run_ocrmypdf(
                input_pdf=input_pdf,
                output_dir=tmp_dir,
                ocr_language=ocr_language,
            )
            logger.info("OCR завершен")
            report_progress(4, 10, "OCR завершен, открытие документа...")

        doc = fitz.open(working_pdf)
        total_pages = len(doc)
        logger.set_total_pages(total_pages)

        try:
            metadata = doc.metadata or {}
            resolved_title = clean_metadata_value(title) or clean_metadata_value(metadata.get("title")) or input_pdf.stem
            resolved_author = clean_metadata_value(author) or clean_metadata_value(metadata.get("author")) or "Unknown author"
            
            identifier_seed = f"{input_pdf.name}:{input_pdf.stat().st_size}:{resolved_title}"
            identifier = hashlib.sha256(identifier_seed.encode("utf-8")).hexdigest()

            report_progress(5, 10, "Инициализация движка EPUB...")
            
            writer = EpubWriter(
                title=resolved_title,
                author=resolved_author,
                language=language,
                identifier=identifier,
                optimize_images=optimize_images,
                image_quality=image_quality,
                image_format=image_format,
            )

            extractor = PdfExtractor(
                doc=doc,
                edit_rules=edit_rules,
                preserve_images=preserve_images,
            )

            repeated_marginals = detect_repeated_marginal_texts(doc) if profile.remove_headers_footers else set()
            normal_font_size = median_font_size(doc)

            classifier = BlockClassifier(
                profile=profile,
                normal_font_size=normal_font_size,
                repeated_marginal_texts=repeated_marginals,
            )

            # Инициализация новых парсеров
            table_parser = TableParser() if (enable_tables and HAS_TABLES) else None
            formula_detector = FormulaDetector() if (enable_formulas and HAS_FORMULAS) else None
            
            # Передаем парсеры в рендерер (если ваш HtmlRenderer поддерживает их через kwargs или нужно модифицировать renderer)
            # В данном примере предполагаем, что renderer использует глобальные настройки или мы передадим их явно, 
            # если сигнатура HtmlRenderer позволяет. Если нет - можно расширить класс renderer.
            # Для совместимости передадим их в контекст или используем напрямую в цикле, если renderer не обновлен.
            # Здесь мы предполагаем, что renderer уже обновлен или мы обрабатываем текст до рендеринга.
            
            renderer = HtmlRenderer(
                profile=profile,
                writer=writer,
                edit_rules=edit_rules,
                header_height=header_height,
                footer_height=footer_height,
                preserve_images=preserve_images,
                skip_printed_toc=skip_printed_toc,
                aggressive_level=aggressive_level,
                preserve_figure_references=preserve_figure_references,
                # Добавьте эти аргументы в __init__ HtmlRenderer, если нужно:
                # table_parser=table_parser,
                # formula_detector=formula_detector,
            )

            effective_split_by_outline = profile.split_by_outline if split_by_outline is None else split_by_outline

            report_progress(6, 10, "Планирование глав...")
            chapter_plan = build_chapter_plan(
                doc=doc,
                split_by_outline=effective_split_by_outline,
                pages_per_chapter=pages_per_chapter,
            )

            if not chapter_plan:
                raise RuntimeError("Chapter plan is empty.")

            logger.set_total_chapters(len(chapter_plan))
            total_chapters = len(chapter_plan)

            for chapter_index, chapter in enumerate(chapter_plan, start=1):
                # Расчет прогресса: от 60% до 90%
                current_progress_step = 6 + int((chapter_index / total_chapters) * 3)
                report_progress(current_progress_step, 10, f"Обработка главы {chapter_index}/{total_chapters}: {chapter.title}")

                chapter_body_parts: list[str] = [f"<h1>{html_escape(chapter.title)}</h1>"]

                for page_index in range(chapter.start_page_index, chapter.end_page_index):
                    pdf_page = doc[page_index]
                    page_number = page_index + 1

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

                    # --- ЗДЕСЬ ИНТЕГРАЦИЯ НОВЫХ МОДУЛЕЙ ---
                    # Если HtmlRenderer не обновлен для приема парсеров, можно обработать текст здесь
                    # Но лучше передать их в renderer. Для примера оставим вызов renderer как есть,
                    # предполагая, что вы обновите HtmlRenderer или передадите парсеры туда.
                    
                    # Пример ручной обработки (если renderer не умеет):
                    # raw_html = renderer.render_page(...)
                    # if formula_detector: raw_html = formula_detector.process_html(raw_html)
                    
                    page_html = renderer.render_page(
                        pdf_page=pdf_page,
                        page=page_content,
                        blocks=classified_blocks,
                    )
                    
                    # Если renderer не обрабатывает таблицы/формулы внутри, раскомментируйте и адаптируйте:
                    # if table_parser: page_html = table_parser.post_process(page_html)
                    # if formula_detector: page_html = formula_detector.post_process(page_html)

                    chapter_body_parts.append(page_html)
                    logger.page_processed(page_number, chapter_index)

                file_name_fragment = safe_filename_fragment(chapter.title)
                chapter_file_name = f"chapters/chapter_{chapter_index:04d}_{file_name_fragment}.xhtml"

                writer.add_chapter(
                    title=chapter.title,
                    file_name=chapter_file_name,
                    html_body="\n".join(chapter_body_parts),
                    language=language,
                )
                logger.chapter_completed(chapter_index, chapter.title)

            report_progress(9, 10, "Сборка EPUB файла...")
            writer.write(output_epub)
            logger.info(f"EPUB сохранен: {output_epub}")

            if validate_output:
                report_progress(9, 10, "Валидация EPUB...")
                logger.info("Валидация EPUB...")
                validation_result = validate_epub(output_epub)
                if not validation_result.is_valid:
                    logger.error(f"EPUB невалиден: {validation_result.errors[:3]}")
            
            report_progress(10, 10, "Готово!")
            
            if cache_enabled:
                cache_stats = cache.get_stats()
                logger.debug(f"Кэш: {cache_stats['entries']} записей")

            stats = logger.finalize()
            return output_epub

        except Exception as e:
            logger.error(f"Критическая ошибка: {str(e)}")
            logger.finalize()
            raise
        finally:
            doc.close()