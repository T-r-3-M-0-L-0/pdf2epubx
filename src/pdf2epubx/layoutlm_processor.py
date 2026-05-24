"""
Модуль для интеграции LayoutLM (ML-модель) для улучшения распознавания структуры документа.
Использует предобученные модели Microsoft LayoutLM для классификации блоков.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
import json

# Опциональные импорты - модуль работает и без ML
try:
    from transformers import AutoTokenizer, AutoModelForTokenClassification
    from PIL import Image
    import torch
    HAS_LAYOUTLM = True
except ImportError:
    HAS_LAYOUTLM = False


@dataclass
class LayoutBlock:
    """Блок с ML-классификацией."""
    text: str
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    label: str  # например: "text", "title", "list", "table", "figure", "formula"
    confidence: float
    page_number: int


class LayoutLMProcessor:
    """
    Процессор на основе LayoutLM для семантической сегментации страниц PDF.

    Поддерживаемые модели:
    - microsoft/layoutlm-base-uncased
    - microsoft/layoutlm-large-uncased
    - microsoft/layoutlmv2-base-uncased (требует изображения)
    """

    SUPPORTED_LABELS = {
        0: "other",
        1: "title",
        2: "text",
        3: "list",
        4: "table",
        5: "figure",
        6: "formula",
        7: "header",
        8: "footer",
        9: "caption",
        10: "code",
    }

    def __init__(
        self,
        model_name: str = "microsoft/layoutlm-base-uncased",
        device: str = "cpu",
        confidence_threshold: float = 0.7,
    ):
        """
        Инициализация процессора LayoutLM.

        Args:
            model_name: Название модели HuggingFace
            device: "cpu" или "cuda"
            confidence_threshold: Порог уверенности для классификации
        """
        if not HAS_LAYOUTLM:
            raise ImportError(
                "LayoutLM требует установки дополнительных зависимостей:\n"
                "pip install transformers torch pillow\n"
                "Для GPU также: pip install torchvision cudatoolkit"
            )

        self.model_name = model_name
        self.device = device
        self.confidence_threshold = confidence_threshold

        # Загружаем модель и токенизатор
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForTokenClassification.from_pretrained(
            model_name,
            num_labels=len(self.SUPPORTED_LABELS),
        )
        self.model.to(device)
        self.model.eval()

    def process_page(
        self,
        text: str,
        words: List[str],
        boxes: List[List[int]],
        page_number: int,
        image: Optional[Image.Image] = None,
    ) -> List[LayoutBlock]:
        """
        Обрабатывает страницу PDF через LayoutLM.

        Args:
            text: Полный текст страницы
            words: Список слов (tokenized)
            boxes: Bounding boxes для каждого слова [x0, y0, x1, y1]
            page_number: Номер страницы
            image: Изображение страницы (для LayoutLMv2/v3)

        Returns:
            Список классифицированных блоков
        """
        if not words:
            return []

        # Токенизация
        encoding = self.tokenizer(
            words,
            boxes=boxes,
            return_tensors="pt",
            padding="max_length",
            truncation=True,
            max_length=512,
        )

        # Перемещаем на устройство
        input_ids = encoding["input_ids"].to(self.device)
        attention_mask = encoding["attention_mask"].to(self.device)
        bbox = encoding["bbox"].to(self.device)

        # Предсказание
        with torch.no_grad():
            outputs = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                bbox=bbox,
            )

        predictions = outputs.logits.argmax(dim=2)[0].cpu().numpy()
        confidences = torch.max(outputs.logits, dim=2).values[0].cpu().numpy()

        # Группируем слова в блоки по labels
        blocks = self._group_words_into_blocks(
            words=words,
            boxes=boxes,
            labels=predictions,
            confidences=confidences,
            page_number=page_number,
        )

        return blocks

    def _group_words_into_blocks(
        self,
        words: List[str],
        boxes: List[List[int]],
        labels: List[int],
        confidences: List[float],
        page_number: int,
    ) -> List[LayoutBlock]:
        """Группирует слова в семантические блоки."""
        if not words:
            return []

        blocks = []
        current_block_words = []
        current_block_boxes = []
        current_label = None
        current_confidences = []

        for i, (word, box, label, conf) in enumerate(zip(words, boxes, labels, confidences)):
            label_name = self.SUPPORTED_LABELS.get(label, "other")

            # Новый блок если label изменился или большой gap
            if current_label is None:
                current_label = label
                current_block_words = [word]
                current_block_boxes = [box]
                current_confidences = [conf]
            elif label == current_label and self._is_adjacent(current_block_boxes[-1], box):
                # Продолжаем текущий блок
                current_block_words.append(word)
                current_block_boxes.append(box)
                current_confidences.append(conf)
            else:
                # Сохраняем текущий блок и начинаем новый
                if current_block_words:
                    block = self._create_block(
                        words=current_block_words,
                        boxes=current_block_boxes,
                        label=self.SUPPORTED_LABELS.get(current_label, "other"),
                        confidences=current_confidences,
                        page_number=page_number,
                    )
                    if block and block.confidence >= self.confidence_threshold:
                        blocks.append(block)

                current_label = label
                current_block_words = [word]
                current_block_boxes = [box]
                current_confidences = [conf]

        # Последний блок
        if current_block_words:
            block = self._create_block(
                words=current_block_words,
                boxes=current_block_boxes,
                label=self.SUPPORTED_LABELS.get(current_label, "other"),
                confidences=current_confidences,
                page_number=page_number,
            )
            if block and block.confidence >= self.confidence_threshold:
                blocks.append(block)

        return blocks

    def _is_adjacent(self, box1: List[int], box2: List[int], threshold: int = 50) -> bool:
        """Проверяет, являются ли два box соседними."""
        x0_1, y0_1, x1_1, y1_1 = box1
        x0_2, y0_2, x1_2, y1_2 = box2

        # Горизонтальная близость
        horizontal_gap = abs(x0_2 - x1_1)
        # Вертикальная близость (в пределах одной строки)
        vertical_overlap = not (y1_1 < y0_2 or y1_2 < y0_1)

        return horizontal_gap < threshold and vertical_overlap

    def _create_block(
        self,
        words: List[str],
        boxes: List[List[int]],
        label: str,
        confidences: List[float],
        page_number: int,
    ) -> Optional[LayoutBlock]:
        """Создаёт блок из группы слов."""
        if not words:
            return None

        text = " ".join(words)

        # Объединяем bounding boxes
        all_x0 = min(b[0] for b in boxes)
        all_y0 = min(b[1] for b in boxes)
        all_x1 = max(b[2] for b in boxes)
        all_y1 = max(b[3] for b in boxes)

        avg_confidence = sum(confidences) / len(confidences)

        return LayoutBlock(
            text=text,
            bbox=(float(all_x0), float(all_y0), float(all_x1), float(all_y1)),
            label=label,
            confidence=avg_confidence,
            page_number=page_number,
        )


class DocLayNetProcessor(LayoutLMProcessor):
    """
    Специализированный процессор на основе DocLayNet для сложных документов.
    DocLayNet имеет более детальную схему аннотаций.
    """

    # DocLayNet labels
    DOCLAYNET_LABELS = {
        0: "caption",
        1: "footnote",
        2: "formula",
        3: "list-item",
        4: "page-footer",
        5: "page-header",
        6: "picture",
        7: "section-header",
        8: "table",
        9: "text",
        10: "title",
        11: "other",
    }

    def __init__(
        self,
        model_name: str = "ibm-doclaynet/layoutlmv2-base-doclaynet",
        device: str = "cpu",
        confidence_threshold: float = 0.7,
    ):
        try:
            super().__init__(
                model_name=model_name,
                device=device,
                confidence_threshold=confidence_threshold,
            )
        except Exception as e:
            # Fallback если модель не доступна
            if not HAS_LAYOUTLM:
                raise ImportError("DocLayNet требует transformers и torch")
            raise RuntimeError(f"Не удалось загрузить DocLayNet модель: {e}")

    def map_to_standard_labels(self, blocks: List[LayoutBlock]) -> List[LayoutBlock]:
        """Конвертирует DocLayNet labels в стандартные."""
        label_mapping = {
            "caption": "caption",
            "footnote": "text",
            "formula": "formula",
            "list-item": "list",
            "page-footer": "footer",
            "page-header": "header",
            "picture": "figure",
            "section-header": "title",
            "table": "table",
            "text": "text",
            "title": "title",
            "other": "other",
        }

        for block in blocks:
            if block.label in label_mapping:
                block.label = label_mapping[block.label]

        return blocks


def create_layout_processor(
    model_type: str = "layoutlm",
    device: str = "cpu",
    confidence_threshold: float = 0.7,
) -> Optional[LayoutLMProcessor]:
    """
    Фабричная функция для создания процессора.

    Args:
        model_type: "layoutlm" | "doclaynet" | "none"
        device: "cpu" | "cuda"
        confidence_threshold: Порог уверенности

    Returns:
        Процессор или None если ML недоступен
    """
    if not HAS_LAYOUTLM:
        return None

    if model_type == "none":
        return None

    if model_type == "doclaynet":
        try:
            return DocLayNetProcessor(
                device=device,
                confidence_threshold=confidence_threshold,
            )
        except Exception:
            # Fallback на обычный LayoutLM
            pass

    # Default: обычный LayoutLM
    return LayoutLMProcessor(
        device=device,
        confidence_threshold=confidence_threshold,
    )


if __name__ == "__main__":
    # Пример использования
    print("LayoutLM Processor Module")
    print(f"LayoutLM available: {HAS_LAYOUTLM}")

    if HAS_LAYOUTLM:
        print(f"CUDA available: {torch.cuda.is_available()}")
        print(f"Device count: {torch.cuda.device_count() if torch.cuda.is_available() else 0}")