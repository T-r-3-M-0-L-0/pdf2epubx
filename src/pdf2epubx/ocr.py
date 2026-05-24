from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

import fitz

# Проверяем доступность ocrmypdf как Python-пакета
try:
    import ocrmypdf as _ocrmypdf_module
    _HAS_OCRMYPDF_PACKAGE = True
except ImportError:
    _HAS_OCRMYPDF_PACKAGE = False


def run_ocrmypdf(
    input_pdf: Path,
    output_dir: Path,
    ocr_language: str,
) -> Path:
    """
    OCR через ocrmypdf.

    Приоритет:
    1. Python API (import ocrmypdf) — надёжнее, не зависит от PATH
    2. CLI (subprocess) — fallback, если пакет не установлен
    """
    output_pdf = output_dir / f"{input_pdf.stem}.ocr.pdf"

    # Способ 1: Python API (приоритетный)
    if _HAS_OCRMYPDF_PACKAGE:
        try:
            _ocrmypdf_module.ocr(
                input_file=str(input_pdf),
                output_file=str(output_pdf),
                language=ocr_language.replace("+", "+"),  # ocrmypdf использует "+" как разделитель
                skip_text=True,
                deskew=True,
                rotate_pages=True,
                clean=True,
                progress_bar=False,
            )
            return output_pdf
        except Exception as api_err:
            # Если Python API не сработал — пробуем CLI
            pass

    # Способ 2: CLI (fallback)
    executable = shutil.which("ocrmypdf")

    if executable is None:
        if _HAS_OCRMYPDF_PACKAGE:
            raise RuntimeError(
                f"ocrmypdf Python API вернул ошибку. "
                "Убедитесь, что Tesseract и Ghostscript установлены:\n"
                "  - Tesseract: https://github.com/UB-Mannheim/tesseract/wiki\n"
                "  - Ghostscript: https://www.ghostscript.com/releases/gsdnld.html"
            )
        raise RuntimeError(
            "OCR was requested, but OCRmyPDF was not found. "
            "Install: pip install ocrmypdf\n"
            "Also install Tesseract and Ghostscript."
        )

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

    Проверяет:
    - ocrmypdf: Python-пакет ИЛИ CLI-утилита в PATH
    - tesseract: CLI-утилита в PATH (нужна для обоих методов)

    Returns:
        Словарь {'ocrmypdf': bool, 'tesseract': bool, 'builtin': bool}
    """
    # ocrmypdf: проверяем и Python-пакет, и CLI
    ocrmypdf_available = _HAS_OCRMYPDF_PACKAGE or (shutil.which("ocrmypdf") is not None)
    tesseract_available = shutil.which("tesseract") is not None

    return {
        "ocrmypdf": ocrmypdf_available,
        "tesseract": tesseract_available,
        "builtin": tesseract_available,  # встроенный OCR тоже требует Tesseract
    }


def get_best_ocr_method() -> str:
    """
    Определяет лучший доступный метод OCR.

    Приоритет: ocrmypdf (лучшее качество) → builtin (Tesseract через PyMuPDF) → none.

    Returns:
        'ocrmypdf', 'builtin' или 'none'
    """
    available = is_ocr_available()

    if available["ocrmypdf"]:
        return "ocrmypdf"
    if available["builtin"]:
        return "builtin"
    return "none"