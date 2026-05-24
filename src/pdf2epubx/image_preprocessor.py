"""
Модуль для предобработки изображений перед OCR.
Включает deskew, denoise, binarization и другие улучшения.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, TYPE_CHECKING
import io

if TYPE_CHECKING:
    import numpy as np
    from PIL import Image as PILImage
else:
    np = None
    PILImage = None

try:
    from PIL import Image, ImageFilter, ImageEnhance
    import numpy as np
    _HAS_PIL_NUMPY = True
except ImportError:
    _HAS_PIL_NUMPY = False
    if not TYPE_CHECKING:
        np = None
        Image = None

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# HAS_OPENCV = True только когда ВСЕ зависимости доступны (PIL + numpy + cv2)
HAS_OPENCV = _HAS_PIL_NUMPY and HAS_CV2


class ImagePreprocessor:
    """
    Предобработчик изображений для улучшения качества OCR.

    Поддерживаемые операции:
    - Deskew (выпрямление)
    - Denoise (удаление шума)
    - Binarization (бинаризация)
    - Contrast enhancement (улучшение контраста)
    - Border removal (удаление границ)
    - Resolution scaling (масштабирование)
    """

    def __init__(
        self,
        deskew: bool = True,
        denoise: bool = True,
        binarize: bool = False,
        enhance_contrast: bool = True,
        remove_borders: bool = False,
        target_dpi: int = 300,
    ):
        """
        Инициализация предобработчика.

        Args:
            deskew: Выпрямлять изображение
            denoise: Удалять шум
            binarize: Бинаризовать (черно-белое)
            enhance_contrast: Улучшать контраст
            remove_borders: Удалять черные границы
            target_dpi: Целевое DPI
        """
        self.deskew = deskew
        self.denoise = denoise
        self.binarize = binarize
        self.enhance_contrast = enhance_contrast
        self.remove_borders = remove_borders
        self.target_dpi = target_dpi

    def preprocess(self, image_bytes: bytes) -> bytes:
        """
        Применяет все включенные улучшения к изображению.

        Args:
            image_bytes: Исходное изображение в байтах

        Returns:
            Обработанное изображение в байтах
        """
        if not HAS_OPENCV:
            return image_bytes

        # Открываем изображение
        img = Image.open(io.BytesIO(image_bytes))

        # Конвертируем в numpy array для OpenCV
        img_array = np.array(img)

        # Конвертируем RGB -> BGR для OpenCV если нужно
        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # Применяем улучшения
        if self.deskew:
            img_array = self._deskew(img_array)

        if self.denoise:
            img_array = self._denoise(img_array)

        if self.enhance_contrast:
            img_array = self._enhance_contrast(img_array)

        if self.binarize:
            img_array = self._binarize(img_array)

        if self.remove_borders:
            img_array = self._remove_borders(img_array)

        # Конвертируем обратно в PIL
        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)

        result_img = Image.fromarray(img_array)

        # Сохраняем в bytes
        output = io.BytesIO()
        result_img.save(output, format="PNG")
        return output.getvalue()

    def _deskew(self, img_array: np.ndarray) -> np.ndarray:
        """Выпрямляет изображение."""
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)

        # Края
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # Линии через Hough Transform
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)

        if lines is None:
            return img_array

        # Находим угол наклона
        angles = []
        for rho, theta in lines[:, 0]:
            angle = (theta * 180) / np.pi - 90
            if abs(angle) < 45:  # Игнорируем вертикальные линии
                angles.append(angle)

        if not angles:
            return img_array

        median_angle = np.median(angles)

        if abs(median_angle) < 0.5:  # Уже прямо
            return img_array

        # Поворачиваем
        h, w = img_array.shape[:2]
        center = (w // 2, h // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(
            img_array,
            rotation_matrix,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        return rotated

    def _denoise(self, img_array: np.ndarray) -> np.ndarray:
        """Удаляет шум с изображения."""
        # Non-local means denoising - хорошее качество но медленное
        if len(img_array.shape) == 3:
            denoised = cv2.fastNlMeansDenoisingColored(img_array, None, 10, 10, 7, 21)
        else:
            denoised = cv2.fastNlMeansDenoising(img_array, None, 10, 7, 21)

        return denoised

    def _enhance_contrast(self, img_array: np.ndarray) -> np.ndarray:
        """Улучшает контраст через CLAHE."""
        # Конвертируем в LAB цветовое пространство
        lab = cv2.cvtColor(img_array, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        # Применяем CLAHE к L каналу (lightness)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced_l = clahe.apply(l)

        # Собираем обратно
        enhanced_lab = cv2.merge((enhanced_l, a, b))
        enhanced = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

        return enhanced

    def _binarize(self, img_array: np.ndarray) -> np.ndarray:
        """Бинаризует изображение (Otsu's thresholding)."""
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)

        # Otsu's thresholding
        _, binary = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )

        # Конвертируем обратно в BGR
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    def _remove_borders(self, img_array: np.ndarray) -> np.ndarray:
        """Удаляет черные/белые границы."""
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)

        # Находим координаты ненулевых пикселей
        coords = cv2.findNonZero(255 - gray)  # Инвертируем для черных границ

        if coords is None:
            return img_array

        x, y, w, h = cv2.boundingRect(coords)

        # Обрезаем
        cropped = img_array[y:y+h, x:x+w]

        return cropped


def preprocess_for_ocr(
    image_bytes: bytes,
    quality_mode: str = "quality",
) -> bytes:
    """
    Быстрая функция для предобработки изображения перед OCR.

    Args:
        image_bytes: Исходное изображение
        quality_mode: "quality" | "speed" | "balanced"

    Returns:
        Обработанное изображение
    """
    if not HAS_OPENCV:
        return image_bytes

    if quality_mode == "speed":
        preprocessor = ImagePreprocessor(
            deskew=False,
            denoise=False,
            binarize=False,
            enhance_contrast=True,
            remove_borders=False,
        )
    elif quality_mode == "balanced":
        preprocessor = ImagePreprocessor(
            deskew=True,
            denoise=True,
            binarize=False,
            enhance_contrast=True,
            remove_borders=False,
        )
    else:  # quality
        preprocessor = ImagePreprocessor(
            deskew=True,
            denoise=True,
            binarize=False,
            enhance_contrast=True,
            remove_borders=True,
        )

    return preprocessor.preprocess(image_bytes)


if __name__ == "__main__":
    print("Image Preprocessor Module")
    print(f"OpenCV available: {HAS_CV2}")
    print(f"PIL/numpy available: {HAS_OPENCV}")