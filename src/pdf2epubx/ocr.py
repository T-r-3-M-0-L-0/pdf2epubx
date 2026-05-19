from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


def run_ocrmypdf(
    input_pdf: Path,
    output_dir: Path,
    ocr_language: str,
) -> Path:
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