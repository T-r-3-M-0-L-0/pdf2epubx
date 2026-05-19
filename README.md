# pdf2epubx

Local PDF to EPUB converter for Windows/Linux.

## Profiles

- `novel` — fiction and mostly linear books.
- `technical` — Linux books, manuals, DevOps books, books with code blocks, commands, configs and tables.
- `facsimile` — page-as-image EPUB for complex layouts and scans.
- `hybrid` — semantic text extraction with image fallback for problematic pages.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .