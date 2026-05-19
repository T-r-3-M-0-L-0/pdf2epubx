from __future__ import annotations

import fitz

from pdf2epubx.edit_rules import EditRules, build_clip_rect, should_exclude_rect
from pdf2epubx.models import PageContent, RawBlock, TextLine, TextSpan


class PdfExtractor:
    def __init__(
        self,
        doc: fitz.Document,
        edit_rules: EditRules,
        preserve_images: bool = True,          # ← НОВЫЙ ПАРАМЕТР
    ) -> None:
        self.doc = doc
        self.edit_rules = edit_rules
        self.preserve_images = preserve_images   # ← сохраняем

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

        for block in data.get("blocks", []):
            block_type = block.get("type")
            bbox_raw = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
            bbox = self._as_bbox(bbox_raw)

            if should_exclude_rect(page_number, bbox, self.edit_rules):
                continue

            if block_type == 0:  # текст
                lines = self._extract_lines(block)
                if lines:
                    blocks.append(
                        RawBlock(
                            kind="text",
                            bbox=bbox,
                            lines=lines,
                        )
                    )

            elif block_type == 1:  # изображение
                # ← Вот здесь теперь учитываем настройку
                if self.preserve_images:
                    image_bytes = block.get("image")
                    image_ext = str(block.get("ext", "png")).lower().strip(".") or "png"

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

    def _extract_lines(self, block: dict) -> list[TextLine]:
        result: list[TextLine] = []

        for line in block.get("lines", []):
            spans: list[TextSpan] = []

            line_bbox_raw = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
            line_bbox = self._as_bbox(line_bbox_raw)

            for span in line.get("spans", []):
                text = str(span.get("text", ""))

                if not text:
                    continue

                span_bbox_raw = span.get("bbox", line_bbox)
                span_bbox = self._as_bbox(span_bbox_raw)

                spans.append(
                    TextSpan(
                        text=text,
                        font=str(span.get("font", "")),
                        size=float(span.get("size", 0.0) or 0.0),
                        flags=int(span.get("flags", 0) or 0),
                        bbox=span_bbox,
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