from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FileFormat:
    """Normalized format metadata shared by readers and writers."""

    name: str
    extension: str
    content_type: str


@dataclass(frozen=True)
class EncodedFile:
    content: bytes
    filename: str
    format: FileFormat

    @property
    def content_type(self) -> str:
        return self.format.content_type


class FileCodec(Protocol):
    format: FileFormat

    def encode(self, content: str, filename: str) -> EncodedFile:
        """Serialize an LLM-facing content string into a downloadable file."""

