from __future__ import annotations

from enum import Enum
from pathlib import Path

import typer

from pdf2epubx.converter import convert_pdf_to_epub
from pdf2epubx.preflight import (
    print_preflight_summary,
    run_preflight,
    write_recommended_rules_json,
)


class ProfileName(str, Enum):
    novel = "novel"
    technical = "technical"
    facsimile = "facsimile"
    hybrid = "hybrid"


class OcrMode(str, Enum):
    auto = "auto"
    always = "always"
    never = "never"


app = typer.Typer(
    help="Local PDF to EPUB converter with profile-based processing."
)


@app.command()
def convert(
    input_pdf: Path = typer.Argument(..., help="Path to source PDF file."),
    output_epub: Path = typer.Argument(..., help="Path to output EPUB file."),
    profile: ProfileName = typer.Option(ProfileName.hybrid, "--profile", "-p", help="Conversion profile."),
    title: str | None = typer.Option(None, "--title", "-t", help="Book title."),
    author: str | None = typer.Option(None, "--author", "-a", help="Book author."),
    language: str = typer.Option("ru", "--language", "-l", help="EPUB language code."),
    ocr: OcrMode = typer.Option(OcrMode.auto, "--ocr", help="OCR mode: auto, always or never."),
    ocr_language: str = typer.Option("rus+eng", "--ocr-language", help="OCR language for OCRmyPDF/Tesseract."),
    pages_per_chapter: int = typer.Option(10, "--pages-per-chapter", help="Fallback split size when PDF outline is unavailable."),
    rules: Path | None = typer.Option(None, "--rules", help="Path to JSON file with PDF cleanup/editing rules.",),
    split_by_outline: bool = typer.Option(True, "--split-by-outline/--no-split-by-outline", help="Use PDF bookmarks/outline to split EPUB chapters. Disable this for PDFs with broken outlines.",),
) -> None:
    if not input_pdf.exists():
        typer.echo(f"Input PDF does not exist: {input_pdf}")
        raise typer.Exit(code=1)

    if input_pdf.suffix.lower() != ".pdf":
        typer.echo(f"Input file is not a PDF: {input_pdf}")
        raise typer.Exit(code=1)

    try:
        result = convert_pdf_to_epub(
            input_pdf=input_pdf,
            output_epub=output_epub,
            profile_name=profile.value,
            title=title,
            author=author,
            language=language,
            ocr_mode=ocr.value,
            ocr_language=ocr_language,
            pages_per_chapter=pages_per_chapter,
            rules_path=rules,
            split_by_outline=split_by_outline,
        )
    except Exception as exc:
        typer.echo(f"Conversion failed: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created EPUB: {result}")


@app.command()
def profiles() -> None:
    typer.echo("Available profiles:")
    typer.echo("  novel      - fiction and mostly linear books")
    typer.echo("  technical  - Linux books, manuals, programming books, DevOps books")
    typer.echo("  facsimile  - page-as-image EPUB")
    typer.echo("  hybrid     - semantic extraction with image fallback")

@app.command()
def preflight(
    input_pdf: Path = typer.Argument(..., help="Path to source PDF file."),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to preflight JSON report.",
    ),
    recommended_rules: Path | None = typer.Option(
        None,
        "--recommended-rules",
        help="Path to generated recommended rules JSON.",
    ),
    max_pages: int = typer.Option(
        40,
        "--max-pages",
        help="Maximum number of pages to analyze in the page-level report.",
    ),
) -> None:
    try:
        report = run_preflight(
            input_pdf=input_pdf,
            output_json=output,
            max_pages_for_report=max_pages,
        )

        if recommended_rules is not None:
            write_recommended_rules_json(
                report=report,
                output_json=recommended_rules,
            )

    except Exception as exc:
        typer.echo(f"Preflight failed: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(print_preflight_summary(report))

    if output is not None:
        typer.echo(f"Preflight report written to: {output}")

    if recommended_rules is not None:
        typer.echo(f"Recommended rules written to: {recommended_rules}")