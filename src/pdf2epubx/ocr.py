from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

import fitz


def run_ocrmypdf(
    input_pdf: Path,
    output_dir: Path,
    ocr_language: str,
) -> Path:
    """OCR через внешний ocrmypdf (Tesseract)."""
    executable = shutil.which("ocrmypdf")

    if executable is None:
        raise RuntimeError(
            "OCR was requested, but OCRmyPDF was not found. "
            "Install OCRmyPDF and Tesseract, then run the command again."
        )

    output_pdf = output_dir / f"{input_pdf.stem}.ocr.pdf"

    command = [
        executable,
        "--skip-text",
        "--deskew",
        "--rotate-pages",
        "--clean",
        "-l",
        ocr_language,
        str(input_pdf),
        str(output_pdf),
    ]

    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "OCRmyPDF failed.\n\n"
            f"Command: {' '.join(command)}\n\n"
            f"STDOUT:\n{completed.stdout}\n\n"
            f"STDERR:\n{completed.stderr}"
        )

    return output_pdf


def run_builtin_ocr(
    input_pdf: Path,
    output_dir: Path,
    ocr_language: str = "rus+eng",
) -> Path:
    """
    OCR через встроенный механизм PyMuPDF + Tesseract.
    Не требует отдельной установки ocrmypdf.
    Требуется установленный Tesseract (tesseract-ocr) в системе.

    Args:
        input_pdf: Путь к входному PDF.
        output_dir: Директория для результата.
        ocr_language: Языки OCR (формат Tesseract: rus+eng).

    Returns:
        Путь к PDF с текстовым слоем.
    """
    # Проверяем наличие Tesseract
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise RuntimeError(
            "Встроенный OCR требует Tesseract. "
            "Установите tesseract-ocr: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "После установки убедитесь, что tesseract доступен в PATH."
        )

    output_pdf = output_dir / f"{input_pdf.stem}.ocr.pdf"

    doc = fitz.open(input_pdf)
    try:
        # Конвертируем формат языка (rus+eng → rus, eng)
        languages = [lang.strip() for lang in ocr_language.replace("+", ",").split(",")]

        for page_index in range(len(doc)):
            page = doc[page_index]

            # Проверяем, есть ли текстовый слой
            existing_text = page.get_text("text") or ""
            if len(existing_text.strip()) > 30:
                # На странице уже есть текст — пропускаем OCR
                continue

            # Запускаем OCR для этой страницы
            try:
                tp = page.get_textpage_ocr(
                    flags=fitz.TEXT_PRESERVE_WHITESPACE,
                    language="+".join(languages),
                    dpi=300,
                    full=True,
                )
                # TextPage создан с OCR данными — PyMuPDF автоматически
                # добавляет текстовый слой при следующем get_text()
            except Exception:
                # Если OCR для конкретной страницы не удался — пропускаем
                continue

        # Сохраняем результат
        doc.save(str(output_pdf), garbage=4, deflate=True, clean=True)
        return output_pdf
    finally:
        doc.close()


def is_ocr_available() -> dict[str, bool]:
    """
    Проверяет доступность OCR-движков.

    Returns:
        Словарь {'ocrmypdf': bool, 'tesseract': bool, 'builtin': bool}
    """
    ocrmypdf_available = shutil.which("ocrmypdf") is not None
    tesseract_available = shutil.which("tesseract") is not None

    return {
        "ocrmypdf": ocrmypdf_available,
        "tesseract": tesseract_available,
        "builtin": tesseract_available,  # встроенный OCR тоже требует Tesseract
    }


def get_best_ocr_method() -> str:
    """
    Определяет лучший доступный метод OCR.

    Returns:
        'ocrmypdf', 'builtin' или 'none'
    """
    available = is_ocr_available()

    if available["ocrmypdf"]:
        return "ocrmypdf"
    if available["builtin"]:
        return "builtin"
    return "none"