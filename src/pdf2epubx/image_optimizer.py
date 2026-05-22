"""
Модуль для оптимизации изображений.
Сжатие, конвертация в WebP, downsampling.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Literal

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


ImageFormat = Literal["png", "jpeg", "webp"]


class ImageOptimizer:
    """Оптимизатор изображений для EPUB."""

    def __init__(
        self,
        max_width: int = 1600,
        max_height: int = 2400,
        quality: int = 85,
        output_format: ImageFormat = "webp",
        dpi: int = 150,
    ):
        """
        Инициализация оптимизатора.

        Args:
            max_width: Максимальная ширина изображения.
            max_height: Максимальная высота изображения.
            quality: Качество сжатия (1-100).
            output_format: Формат выходного изображения.
            dpi: Целевое DPI для ресемплинга.
        """
        self.max_width = max_width
        self.max_height = max_height
        self.quality = quality
        self.output_format = output_format
        self.dpi = dpi

    def optimize(self, image_bytes: bytes, ext: str = "png") -> tuple[bytes, str]:
        """
        Оптимизирует изображение.

        Args:
            image_bytes: Байты изображения.
            ext: Расширение исходного изображения.

        Returns:
            Кортеж (оптимизированные байты, новое расширение).
        """
        if not PIL_AVAILABLE:
            # Если PIL нет, возвращаем оригинал
            return image_bytes, ext.lower().lstrip(".")

        try:
            img = Image.open(io.BytesIO(image_bytes))

            # Конвертируем RGBA в RGB для JPEG
            if self.output_format == "jpeg" and img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
            elif self.output_format in ("jpeg", "webp") and img.mode == "P":
                img = img.convert("RGB")

            # Ресемплинг если нужно
            img = self._resize_if_needed(img)

            # Сохраняем в нужном формате
            output = io.BytesIO()

            save_kwargs = self._get_save_kwargs(img)

            if self.output_format == "webp":
                img.save(output, format="WEBP", **save_kwargs)
            elif self.output_format == "jpeg":
                img.save(output, format="JPEG", **save_kwargs)
            else:
                img.save(output, format="PNG", optimize=True, compression_level=6)

            return output.getvalue(), self.output_format

        except Exception:
            # При ошибке возвращаем оригинал
            return image_bytes, ext.lower().lstrip(".")

    def _resize_if_needed(self, img: Image.Image) -> Image.Image:
        """Уменьшает изображение если оно превышает максимальные размеры."""
        width, height = img.size

        if width <= self.max_width and height <= self.max_height:
            return img

        # Вычисляем коэффициент масштабирования
        ratio = min(self.max_width / width, self.max_height / height)

        new_width = int(width * ratio)
        new_height = int(height * ratio)

        # Используем Lanczos для лучшего качества
        return img.resize((new_width, new_height), Image.LANCZOS)

    def _get_save_kwargs(self, img: Image.Image) -> dict:
        """Возвращает параметры сохранения для формата."""
        if self.output_format == "webp":
            return {
                "quality": self.quality,
                "method": 6,  # Лучшее качество сжатия
            }
        elif self.output_format == "jpeg":
            return {
                "quality": self.quality,
                "optimize": True,
                "progressive": True,
            }
        return {}

    @staticmethod
    def estimate_compression_ratio(original: bytes, optimized: bytes) -> float:
        """Оценивает коэффициент сжатия."""
        if not original:
            return 0.0
        return len(optimized) / len(original)


def optimize_image_for_epub(
    image_bytes: bytes,
    ext: str = "png",
    max_width: int = 1600,
    max_height: int = 2400,
    quality: int = 85,
    output_format: ImageFormat = "webp",
) -> tuple[bytes, str]:
    """
    Удобная функция для оптимизации одного изображения.

    Args:
        image_bytes: Байты изображения.
        ext: Расширение исходного изображения.
        max_width: Максимальная ширина.
        max_height: Максимальная высота.
        quality: Качество сжатия.
        output_format: Выходной формат.

    Returns:
        Кортеж (оптимизированные байты, новое расширение).
    """
    optimizer = ImageOptimizer(
        max_width=max_width,
        max_height=max_height,
        quality=quality,
        output_format=output_format,
    )
    return optimizer.optimize(image_bytes, ext)