from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.services.chat_attachment_service import ChatAttachmentService


@dataclass(frozen=True)
class GeneratedFileItem:
    filename: str
    content: str
    content_type: str


@dataclass(frozen=True)
class GeneratedFileResult:
    cleaned_content: str
    attachments: list[dict]


class ChatGeneratedFileService:
    SUPPORTED_EXTENSIONS = {"txt", "md", "csv", "tsv", "json"}
    CONTENT_TYPES = {
        "txt": "text/plain",
        "md": "text/markdown",
        "csv": "text/csv",
        "tsv": "text/tab-separated-values",
        "json": "application/json",
    }
    BLOCK_FILE_RE = re.compile(
        r"```file\s+name=(?P<name>[^\n]+)\n(?P<content>.*?)```",
        flags=re.IGNORECASE | re.DOTALL,
    )
    BLOCK_TYPED_RE = re.compile(
        r"```(?P<lang>csv|tsv|json|txt|md)\s+file=(?P<name>[^\n]+)\n(?P<content>.*?)```",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def __init__(self, attachment_service: ChatAttachmentService):
        self.attachment_service = attachment_service

    async def extract_and_store(
        self,
        *,
        tenant_id: str,
        chat_id: str,
        owner_id: str,
        assistant_text: str,
        max_files: int = 3,
        max_file_bytes: int = 2 * 1024 * 1024,
    ) -> GeneratedFileResult:
        text = assistant_text or ""
        extracted: list[GeneratedFileItem] = []

        def _collect(match: re.Match[str], default_lang: Optional[str] = None) -> str:
            nonlocal extracted
            if len(extracted) >= max_files:
                return ""
            filename = self._sanitize_filename(match.group("name"))
            content = (match.group("content") or "").strip()
            if not filename or not content:
                return ""
            ext = self._extension(filename, default_lang=default_lang)
            if ext not in self.SUPPORTED_EXTENSIONS:
                return ""
            encoded = content.encode("utf-8")
            if len(encoded) > max_file_bytes:
                return ""
            extracted.append(
                GeneratedFileItem(
                    filename=self._ensure_extension(filename, ext),
                    content=content,
                    content_type=self.CONTENT_TYPES[ext],
                )
            )
            return ""

        text = self.BLOCK_FILE_RE.sub(lambda m: _collect(m), text)
        text = self.BLOCK_TYPED_RE.sub(lambda m: _collect(m, default_lang=(m.group("lang") or "").lower()), text)
        cleaned = text.strip()

        attachments: list[dict] = []
        for item in extracted:
            created = await self.attachment_service.create_generated_attachment(
                tenant_id=tenant_id,
                chat_id=chat_id,
                owner_id=owner_id,
                filename=item.filename,
                content=item.content.encode("utf-8"),
                content_type=item.content_type,
            )
            attachments.append(created)

        return GeneratedFileResult(cleaned_content=cleaned, attachments=attachments)

    @staticmethod
    def _sanitize_filename(raw: str) -> str:
        name = (raw or "").strip().strip('"').strip("'")
        name = name.replace("\\", "_").replace("/", "_")
        return name

    @staticmethod
    def _ensure_extension(filename: str, ext: str) -> str:
        if filename.lower().endswith(f".{ext}"):
            return filename
        return f"{filename}.{ext}"

    @staticmethod
    def _extension(filename: str, default_lang: Optional[str] = None) -> str:
        if "." in filename:
            return filename.rsplit(".", 1)[-1].strip().lower()
        return (default_lang or "txt").strip().lower()
