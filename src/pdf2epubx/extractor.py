from __future__ import annotations

import fitz

from pdf2epubx.edit_rules import EditRules, build_clip_rect, should_exclude_rect
from pdf2epubx.models import PageContent, RawBlock, TextLine, TextSpan
from pdf2epubx.text_repair import (
    SpanInfo,
    full_text_repair,
    repair_kerning_spans,
    should_normalize_bold,
    normalize_bold_flags,
)


# Минимальные размеры изображения (px) — меньше = декоративные символы, маркеры
MIN_IMAGE_WIDTH = 20
MIN_IMAGE_HEIGHT = 20


class PdfExtractor:
    def __init__(
        self,
        doc: fitz.Document,
        edit_rules: EditRules,
        preserve_images: bool = True,
        normalize_scan_bold: bool = False,
    ) -> None:
        self.doc = doc
        self.edit_rules = edit_rules
        self.preserve_images = preserve_images
        self.normalize_scan_bold = normalize_scan_bold

        # Предварительный анализ bold-распределения для детекции сканов
        self._bold_normalization_cache: dict[int, bool] = {}

    def extract_page(self, page_index: int) -> PageContent:
        page = self.doc[page_index]
        page_number = page_index + 1
        page_rect = page.rect

        clip_raw = build_clip_rect(
            page_width=float(page_rect.width),
            page_height=float(page_rect.height),
            rules=self.edit_rules,
        )

        clip = fitz.Rect(*clip_raw)
        data = page.get_text("dict", sort=True, clip=clip)

        blocks: list[RawBlock] = []

        # Определяем, нужно ли нормализовать bold для этой страницы
        should_norm_bold = self._should_normalize_bold_for_page(data) if self.normalize_scan_bold else False

        for block in data.get("blocks", []):
            block_type = block.get("type")
            bbox_raw = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
            bbox = self._as_bbox(bbox_raw)

            if should_exclude_rect(page_number, bbox, self.edit_rules):
                continue

            if block_type == 0:  # текст
                lines = self._extract_lines(block, should_norm_bold)
                if lines:
                    blocks.append(
                        RawBlock(
                            kind="text",
                            bbox=bbox,
                            lines=lines,
                        )
                    )

            elif block_type == 1:  # изображение
                if self.preserve_images:
                    image_bytes = block.get("image")
                    image_ext = str(block.get("ext", "png")).lower().strip(".") or "png"

                    # Фильтрация микро-изображений (декоративные символы, маркеры)
                    img_width = bbox[2] - bbox[0]
                    img_height = bbox[3] - bbox[1]

                    if img_width < MIN_IMAGE_WIDTH and img_height < MIN_IMAGE_HEIGHT:
                        continue

                    if isinstance(image_bytes, bytes) and image_bytes:
                        blocks.append(
                            RawBlock(
                                kind="image",
                                bbox=bbox,
                                image_bytes=image_bytes,
                                image_ext=image_ext,
                            )
                        )

        return PageContent(
            page_number=page_number,
            width=float(page_rect.width),
            height=float(page_rect.height),
            blocks=blocks,
        )

    def _extract_lines(self, block: dict, should_norm_bold: bool = False) -> list[TextLine]:
        result: list[TextLine] = []

        for line in block.get("lines", []):
            spans: list[TextSpan] = []

            line_bbox_raw = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
            line_bbox = self._as_bbox(line_bbox_raw)

            # Собираем SpanInfo для потенциального merge
            span_infos: list[SpanInfo] = []

            for span in line.get("spans", []):
                text = str(span.get("text", ""))
                if not text:
                    continue

                font_name = str(span.get("font", ""))
                size = float(span.get("size", 0.0) or 0.0)
                flags = int(span.get("flags", 0) or 0)
                color = int(span.get("color", 0) or 0)
                span_bbox_raw = span.get("bbox", line_bbox)
                span_bbox = self._as_bbox(span_bbox_raw)

                # Применяем text_repair к каждому span
                text = full_text_repair(text, font_name)

                if not text.strip() and not text:
                    continue

                # Нормализуем bold для сканов
                if should_norm_bold:
                    flags = normalize_bold_flags(flags, font_name, True)

                span_infos.append(SpanInfo(
                    text=text,
                    font=font_name,
                    size=size,
                    flags=flags,
                    bbox=span_bbox,
                    color=color,
                ))

            # Склеиваем разорванные spans (kerning)
            if span_infos:
                merged = repair_kerning_spans(span_infos)

                for si in merged:
                    spans.append(
                        TextSpan(
                            text=si.text,
                            font=si.font,
                            size=si.size,
                            flags=si.flags,
                            bbox=si.bbox,
                            color=si.color,
                        )
                    )

            if spans:
                result.append(
                    TextLine(
                        spans=spans,
                        bbox=line_bbox,
                    )
                )

        return result

    def _should_normalize_bold_for_page(self, page_data: dict) -> bool:
        """Определяет, нужно ли нормализовать bold для данных страницы."""
        span_infos: list[SpanInfo] = []

        for block in page_data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text", ""))
                    if not text.strip():
                        continue
                    font_name = str(span.get("font", ""))
                    flags = int(span.get("flags", 0) or 0)
                    size = float(span.get("size", 0.0) or 0.0)
                    span_bbox_raw = span.get("bbox", (0, 0, 0, 0))
                    span_bbox = self._as_bbox(span_bbox_raw)

                    span_infos.append(SpanInfo(
                        text=text,
                        font=font_name,
                        size=size,
                        flags=flags,
                        bbox=span_bbox,
                    ))

        return should_normalize_bold(span_infos)

    @staticmethod
    def _as_bbox(value: object) -> tuple[float, float, float, float]:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return 0.0, 0.0, 0.0, 0.0

        return (
            float(value[0]),
            float(value[1]),
            float(value[2]),
            float(value[3]),
        )