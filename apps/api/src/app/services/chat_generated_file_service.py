from __future__ import annotations

from dataclasses import dataclass



@dataclass(frozen=True)
class GeneratedFileItem:
    filename: str
    content: str
    content_type: str


@dataclass(frozen=True)
class GeneratedFileResult:
    cleaned_content: str
    attachments: list[dict]

