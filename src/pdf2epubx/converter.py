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
from pdf2epubx.ocr import run_ocrmypdf, run_builtin_ocr, get_best_ocr_method
from pdf2epubx.pdf_inspector import inspect_pdf, median_font_size
from pdf2epubx.profiles import get_profile, ProgrammingLanguage
from pdf2epubx.renderer import HtmlRenderer
from pdf2epubx.toc_parser import parse_toc_page, render_toc_entries
from pdf2epubx.utils import clean_metadata_value, html_escape, safe_filename_fragment
from pdf2epubx.cache import ConversionCache, compute_pdf_cache_key
from pdf2epubx.logger import ConversionLogger, create_logger
from pdf2epubx.epub_validator import validate_epub
from pdf2epubx.models import ClassifiedBlock, PageContent

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

try:
    from pdf2epubx.image_preprocessor import ImagePreprocessor, preprocess_for_ocr, HAS_OPENCV
    HAS_IMAGE_PREPROCESSING = HAS_OPENCV
except ImportError:
    HAS_IMAGE_PREPROCESSING = False

try:
    from pdf2epubx.layoutlm_processor import (
        create_layout_processor,
        LayoutLMProcessor,
        LayoutBlock,
        HAS_LAYOUTLM,
    )
    HAS_LAYOUTLM_AVAILABLE = HAS_LAYOUTLM
except ImportError:
    HAS_LAYOUTLM_AVAILABLE = False


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
    # Robustness / Scan support
    normalize_scan_bold: bool = True,
    auto_quality_fallback: bool = True,
    # Image preprocessing (требует opencv-python + numpy)
    enable_image_preprocessing: bool = False,
    image_prep_mode: str = "balanced",
    # LayoutLM ML-классификация (требует transformers + torch)
    enable_layoutlm: bool = False,
    layoutlm_model: str = "layoutlm",
    layoutlm_device: str = "cpu",
    layoutlm_confidence: float = 0.7,
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

    # Инициализация image preprocessor
    image_preprocessor = None
    if enable_image_preprocessing and HAS_IMAGE_PREPROCESSING:
        image_preprocessor = ImagePreprocessor(
            deskew=(image_prep_mode != "speed"),
            denoise=(image_prep_mode != "speed"),
            binarize=False,
            enhance_contrast=True,
            remove_borders=(image_prep_mode == "quality"),
        )
        logger.info(f"Image preprocessing: {image_prep_mode} mode")
    elif enable_image_preprocessing and not HAS_IMAGE_PREPROCESSING:
        logger.warning("Image preprocessing запрошен, но OpenCV/numpy недоступны")

    # Инициализация LayoutLM
    layout_processor = None
    if enable_layoutlm and HAS_LAYOUTLM_AVAILABLE:
        try:
            layout_processor = create_layout_processor(
                model_type=layoutlm_model,
                device=layoutlm_device,
                confidence_threshold=layoutlm_confidence,
            )
            if layout_processor:
                logger.info(f"LayoutLM: {layoutlm_model} на {layoutlm_device}")
            else:
                logger.warning("LayoutLM: не удалось создать процессор")
        except Exception as llm_err:
            logger.warning(f"LayoutLM: ошибка инициализации: {llm_err}")
            layout_processor = None
    elif enable_layoutlm and not HAS_LAYOUTLM_AVAILABLE:
        logger.warning("LayoutLM запрошен, но transformers/torch недоступны")
    
    with tempfile.TemporaryDirectory(prefix="pdf2epubx_") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)

        pdf_stats = inspect_pdf(input_pdf)
        working_pdf = input_pdf
        
        logger.info(f"Страниц: {pdf_stats.page_count}, "
                     f"Скан: {pdf_stats.looks_scanned}, "
                     f"Качество текста: {pdf_stats.text_quality_score:.2f}")

        # OCR
        should_ocr = False
        if ocr_mode == "always":
            should_ocr = True
        elif ocr_mode == "auto" and pdf_stats.looks_scanned:
            should_ocr = True
        
        if should_ocr:
            report_progress(3, 10, "Запуск OCR (это может занять время)...")
            logger.info("Запуск OCR...")
            
            # Выбираем лучший доступный метод OCR
            ocr_method = get_best_ocr_method()
            logger.info(f"Метод OCR: {ocr_method}")
            
            try:
                if ocr_method == "ocrmypdf":
                    working_pdf = run_ocrmypdf(
                        input_pdf=input_pdf,
                        output_dir=tmp_dir,
                        ocr_language=ocr_language,
                    )
                elif ocr_method == "builtin":
                    working_pdf = run_builtin_ocr(
                        input_pdf=input_pdf,
                        output_dir=tmp_dir,
                        ocr_language=ocr_language,
                    )
                else:
                    logger.warning("OCR недоступен: ни ocrmypdf, ни Tesseract не найдены. "
                                   "Продолжаем без OCR.")
                    
                logger.info("OCR завершен")
            except Exception as ocr_err:
                logger.warning(f"OCR не удался: {ocr_err}. Продолжаем без OCR.")
                
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

            # Определяем, нужна ли нормализация bold (для сканов)
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
                auto_quality_fallback=auto_quality_fallback,
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
            
            # Счётчик проблемных страниц
            failed_pages: list[tuple[int, str]] = []

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

                    # ── Per-page try/except: одна битая страница НЕ валит конвертацию ──
                    try:
                        page_content = extractor.extract_page(page_index)
                        classified_blocks = classifier.classify_page(page_content)

                        # LayoutLM: опционально улучшаем классификацию
                        if layout_processor is not None:
                            classified_blocks = _enhance_with_layoutlm(
                                layout_processor=layout_processor,
                                page_content=page_content,
                                classified_blocks=classified_blocks,
                                page_number=page_number,
                                logger=logger,
                            )

                        page_html = renderer.render_page(
                            pdf_page=pdf_page,
                            page=page_content,
                            blocks=classified_blocks,
                        )

                        chapter_body_parts.append(page_html)
                        logger.page_processed(page_number, chapter_index)

                    except Exception as page_err:
                        error_msg = f"Ошибка на странице {page_number}: {str(page_err)}"
                        logger.warning(error_msg)
                        failed_pages.append((page_number, str(page_err)))

                        # Fallback: рендерим страницу как изображение
                        try:
                            fallback_html = renderer.render_pdf_page_as_facsimile(pdf_page, page_number)
                            chapter_body_parts.append(fallback_html)
                            logger.info(f"Страница {page_number}: использован fallback (изображение)")
                        except Exception as fallback_err:
                            logger.error(f"Не удалось создать fallback для страницы {page_number}: {fallback_err}")
                            chapter_body_parts.append(
                                f'<p class="error-page">[Страница {page_number} не может быть отображена]</p>'
                            )

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

            # Логируем статистику quality
            quality_summary = renderer.get_quality_summary()
            if quality_summary.get("total_scored", 0) > 0:
                logger.info(
                    f"Quality: avg={quality_summary['avg_score']:.2f}, "
                    f"text={quality_summary['text_pages']}, "
                    f"hybrid={quality_summary['hybrid_pages']}, "
                    f"facsimile={quality_summary['facsimile_pages']}"
                )

            if failed_pages:
                logger.warning(f"Проблемных страниц: {len(failed_pages)}")
                for pn, err in failed_pages[:5]:
                    logger.warning(f"  Стр. {pn}: {err}")

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


def _enhance_with_layoutlm(
    layout_processor: LayoutLMProcessor,
    page_content: PageContent,
    classified_blocks: list[ClassifiedBlock],
    page_number: int,
    logger: ConversionLogger,
) -> list[ClassifiedBlock]:
    """
    Улучшает классификацию блоков с помощью LayoutLM.

    Если ML-модель даёт результат с высокой уверенностью, она переопределяет
    правила из rule-based классификатора. Иначе — оставляем исходную классификацию.
    """
    from pdf2epubx.models import ClassifiedBlock as CB

    try:
        # Собираем слова и bounding boxes из PageContent
        words: list[str] = []
        boxes: list[list[int]] = []

        for block in page_content.blocks:
            if block.kind != "text":
                continue
            for line in block.lines:
                for span in line.spans:
                    text = span.text.strip()
                    if not text:
                        continue
                    # Нормализуем bbox к 0-1000 (формат LayoutLM)
                    x0 = int(span.bbox[0] / page_content.width * 1000)
                    y0 = int(span.bbox[1] / page_content.height * 1000)
                    x1 = int(span.bbox[2] / page_content.width * 1000)
                    y1 = int(span.bbox[3] / page_content.height * 1000)
                    # Clamp
                    x0, y0 = max(0, x0), max(0, y0)
                    x1, y1 = min(1000, x1), min(1000, y1)

                    for word in text.split():
                        words.append(word)
                        boxes.append([x0, y0, x1, y1])

        if not words:
            return classified_blocks

        # Получаем ML-предсказания
        full_text = " ".join(words)
        layout_blocks = layout_processor.process_page(
            text=full_text,
            words=words,
            boxes=boxes,
            page_number=page_number,
        )

        if not layout_blocks:
            return classified_blocks

        # Маппинг LayoutLM labels → ClassifiedKind
        label_to_kind = {
            "title": "heading",
            "text": "paragraph",
            "list": "paragraph",
            "table": "table",
            "figure": "image",
            "formula": "code",       # формулы рендерим как код
            "header": "header",
            "footer": "footer",
            "caption": "caption",
            "code": "code",
            "other": "paragraph",
        }

        # Создаём карту: bbox → ML-label для быстрого поиска
        ml_labels_by_area: list[tuple[tuple[float, float, float, float], str, float]] = []
        for lb in layout_blocks:
            ml_labels_by_area.append((lb.bbox, lb.label, lb.confidence))

        # Для каждого classified блока проверяем, есть ли ML-предсказание
        enhanced: list[CB] = []
        for cb in classified_blocks:
            # Ищем пересечение с ML-блоками
            best_match = None
            best_overlap = 0.0

            for ml_bbox, ml_label, ml_conf in ml_labels_by_area:
                overlap = _bbox_overlap(cb.raw.bbox, ml_bbox)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = (ml_label, ml_conf)

            if best_match and best_overlap > 0.3:
                ml_label, ml_conf = best_match
                new_kind = label_to_kind.get(ml_label, cb.kind)

                # Переопределяем только если ML уверен И результат отличается
                if new_kind != cb.kind and ml_conf > 0.75:
                    enhanced.append(CB(
                        raw=cb.raw,
                        kind=new_kind,
                        level=1 if new_kind == "heading" else cb.level,
                        reason=f"LayoutLM: {ml_label} (conf={ml_conf:.2f})",
                    ))
                    continue

            enhanced.append(cb)

        return enhanced

    except Exception as e:
        logger.warning(f"LayoutLM: ошибка обработки стр. {page_number}: {e}")
        return classified_blocks


def _bbox_overlap(
    bbox1: tuple[float, float, float, float],
    bbox2: tuple[float, float, float, float],
) -> float:
    """Вычисляет IoU (пересечение / объединение) двух bounding boxes."""
    x0 = max(bbox1[0], bbox2[0])
    y0 = max(bbox1[1], bbox2[1])
    x1 = min(bbox1[2], bbox2[2])
    y1 = min(bbox1[3], bbox2[3])

    if x1 <= x0 or y1 <= y0:
        return 0.0

    intersection = (x1 - x0) * (y1 - y0)
    area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
    union = area1 + area2 - intersection

    if union <= 0:
        return 0.0

    return intersection / union