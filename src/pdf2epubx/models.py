from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


BlockKind = Literal["text", "image"]
ClassifiedKind = Literal[
    "heading",
    "paragraph",
    "code",
    "table",
    "image",
    "caption",
    "header",
    "footer",
    "unknown",
]


@dataclass(frozen=True)
class TextSpan:
    text: str
    font: str
    size: float
    flags: int
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class TextLine:
    spans: list[TextSpan]
    bbox: tuple[float, float, float, float]


@dataclass
class RawBlock:
    kind: BlockKind
    bbox: tuple[float, float, float, float]
    lines: list[TextLine] = field(default_factory=list)
    image_bytes: bytes | None = None
    image_ext: str = "png"


@dataclass
class PageContent:
    page_number: int
    width: float
    height: float
    blocks: list[RawBlock]


@dataclass
class ClassifiedBlock:
    raw: RawBlock
    kind: ClassifiedKind
    level: int = 0
    reason: str = ""