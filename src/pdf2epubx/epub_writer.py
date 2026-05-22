from __future__ import annotations

import mimetypes
from pathlib import Path

from ebooklib import epub

from pdf2epubx.utils import sha256_hex


class EpubWriter:
    def __init__(
        self,
        title: str,
        author: str,
        language: str,
        identifier: str,
        optimize_images: bool = False,
        image_quality: int = 85,
        image_format: str = "webp",
    ) -> None:
        self.book = epub.EpubBook()
        self.book.set_identifier(identifier)
        self.book.set_title(title)
        self.book.set_language(language)
        self.book.add_author(author)

        self.chapters: list[epub.EpubHtml] = []
        self.chapter_file_names: set[str] = set()
        self.image_hash_to_file_name: dict[str, str] = {}

        # Оптимизация изображений
        self.optimize_images = optimize_images
        self.image_quality = image_quality
        self.image_format = image_format

        if optimize_images:
            from pdf2epubx.image_optimizer import ImageOptimizer
            self.image_optimizer = ImageOptimizer(
                quality=image_quality,
                output_format=image_format,  # type: ignore
            )
        else:
            self.image_optimizer = None

        self.css_item = epub.EpubItem(
            uid="style_main",
            file_name="style/main.css",
            media_type="text/css",
            content=self.build_css().encode("utf-8"),
        )
        self.book.add_item(self.css_item)

    def add_chapter(
        self,
        title: str,
        file_name: str,
        html_body: str,
        language: str,
    ) -> None:
        if file_name in self.chapter_file_names:
            raise RuntimeError(
                f"Duplicate chapter file name detected: {file_name}. "
                "This usually means writer.add_chapter(...) is placed inside the page loop "
                "instead of the chapter loop in converter.py."
            )

        chapter_number = len(self.chapters) + 1
        chapter_uid = f"chapter_{chapter_number:04d}"

        print(f"DEBUG add_chapter: uid={chapter_uid}, title={title}, file={file_name}")

        chapter = epub.EpubHtml(
            uid=chapter_uid,
            title=title,
            file_name=file_name,
            lang=language,
        )

        chapter.content = html_body
        chapter.add_item(self.css_item)

        self.book.add_item(chapter)
        self.chapters.append(chapter)
        self.chapter_file_names.add(file_name)

    def add_image_bytes(
        self,
        image_bytes: bytes,
        ext: str,
        file_name_prefix: str,
    ) -> str:
        normalized_ext = ext.lower().strip(".") or "png"

        if normalized_ext == "jpg":
            normalized_ext = "jpeg"

        # Оптимизация изображения если включена
        if self.image_optimizer:
            image_bytes, normalized_ext = self.image_optimizer.optimize(image_bytes, ext)

        image_hash = sha256_hex(image_bytes)
        existing_file_name = self.image_hash_to_file_name.get(image_hash)

        if existing_file_name is not None:
            return existing_file_name

        file_name = f"images/{file_name_prefix}_{image_hash[:16]}.{normalized_ext}"
        media_type = self.guess_media_type(normalized_ext)

        item = epub.EpubItem(
            uid=f"img_{image_hash[:24]}",
            file_name=file_name,
            media_type=media_type,
            content=image_bytes,
        )

        self.book.add_item(item)
        self.image_hash_to_file_name[image_hash] = file_name

        return file_name

    def write(self, output_epub: Path) -> None:
        self.book.toc = tuple(self.chapters)
        self.book.spine = ["nav", *self.chapters]

        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())

        epub.write_epub(str(output_epub), self.book, {})

    @staticmethod
    def guess_media_type(ext: str) -> str:
        if ext == "jpeg":
            return "image/jpeg"

        if ext == "png":
            return "image/png"

        if ext == "gif":
            return "image/gif"

        if ext == "webp":
            return "image/webp"

        guessed, _ = mimetypes.guess_type(f"image.{ext}")
        return guessed or "image/png"

    @staticmethod
    def build_css() -> str:
        return """
body {
    font-family: serif;
    line-height: 1.45;
    margin: 0;
    padding: 0;
}

h1 {
    font-size: 1.7em;
    line-height: 1.25;
    margin-top: 1.2em;
    margin-bottom: 0.8em;
    text-align: center;
    page-break-after: avoid;
}

h2 {
    font-size: 1.35em;
    line-height: 1.25;
    margin-top: 1.1em;
    margin-bottom: 0.65em;
    page-break-after: avoid;
}

h3 {
    font-size: 1.15em;
    line-height: 1.25;
    margin-top: 1em;
    margin-bottom: 0.5em;
    page-break-after: avoid;
}

p {
    margin-top: 0.35em;
    margin-bottom: 0.7em;
    text-align: justify;
}

pre {
    font-family: monospace;
    font-size: 0.86em;
    line-height: 1.25;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: anywhere;
    background: #f3f3f3;
    border: 1px solid #cccccc;
    padding: 0.75em;
    margin: 1em 0;
}

code {
    font-family: monospace;
}

pre.table-text {
    font-size: 0.85em;
}

figure {
    text-align: center;
    margin: 1em 0;
    page-break-inside: avoid;
}

figcaption {
    font-size: 0.9em;
    margin-top: 0.4em;
    opacity: 0.8;
}

img {
    max-width: 100%;
    height: auto;
}

.pdf-page {
    margin-bottom: 1.2em;
}

.page-marker {
    font-size: 0.75em;
    opacity: 0.55;
    text-align: right;
    margin-bottom: 0.4em;
}

.page-fallback img,
.facsimile-page img {
    width: 100%;
}

.caption {
    font-size: 0.9em;
    text-align: center;
    opacity: 0.85;
}

.hidden-source-marker {
    display: none;
}

.source-toc {
    margin: 1em 0;
}

.toc-list {
    list-style: none;
    padding-left: 0;
    margin-left: 0;
}

.toc-list li {
    display: flex;
    gap: 0.75em;
    align-items: baseline;
    margin: 0.25em 0;
}

.toc-list li::before {
    content: none;
}

.toc-title {
    flex: 1;
}

.toc-page {
    min-width: 3em;
    text-align: right;
    font-variant-numeric: tabular-nums;
}

.toc-level-1 {
    font-weight: bold;
    margin-top: 0.55em;
}

.toc-level-2 {
    padding-left: 1.25em;
}

.toc-level-3 {
    padding-left: 2.25em;
}
""".strip()