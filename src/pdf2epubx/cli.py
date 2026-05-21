from __future__ import annotations

import typer
from pathlib import Path
from typing import Annotated

from pdf2epubx.converter import convert_pdf_to_epub

app = typer.Typer()


@app.command()
def convert(
    input_pdf: Annotated[Path, typer.Argument(..., help="Путь к PDF-файлу")],
    output_epub: Annotated[Path, typer.Option("--output", "-o", help="Путь к выходному EPUB")] = None,
    profile: Annotated[str, typer.Option("--profile", "-p", help="Профиль: novel, technical, programming, hybrid, facsimile")] = "technical",
    backend: Annotated[str, typer.Option("--backend", "-b", help="Backend: pymupdf или mineru")] = "pymupdf",
    header_height: float = 50.0,
    footer_height: float = 45.0,
    preserve_images: bool = True,
    skip_printed_toc: bool = False,
):
    if output_epub is None:
        output_epub = input_pdf.with_suffix(".epub")

    typer.echo(f"🚀 Конвертация: {input_pdf.name}")
    typer.echo(f"   Профиль: {profile} | Backend: {backend}")

    result = convert_pdf_to_epub(
        input_pdf=input_pdf,
        output_epub=output_epub,
        profile_name=profile,
        backend=backend,                    # ← новый параметр
        header_height=header_height,
        footer_height=footer_height,
        preserve_images=preserve_images,
        skip_printed_toc=skip_printed_toc,
    )

    typer.echo(f"✅ Готово! → {result}")


if __name__ == "__main__":
    app()