from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Iterable

from app.core.config import get_settings
from app.core.exceptions import UploadValidationError
from app.services.extractors.registry import ExtractorRegistry


@dataclass(frozen=True)
class UploadDescriptor:
    filename: str
    extension: str
    content_type: Optional[str]
    size_bytes: int


class UploadIntakePolicy:
    """Central intake policy for user-uploaded files."""

    GENERIC_CONTENT_TYPES = {
        "",
        "application/octet-stream",
        "binary/octet-stream",
    }

    DOCUMENT_CONTENT_TYPES = {
        "pdf": {"application/pdf"},
        "doc": {"application/msword"},
        "docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
        "xls": {"application/vnd.ms-excel"},
        "xlsx": {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        },
        "csv": {
            "text/csv",
            "application/csv",
            "application/vnd.ms-excel",
        },
        "txt": {"text/plain"},
        "log": {"text/plain"},
        "md": {"text/markdown", "text/plain"},
    }

    CHAT_DEFAULT_ALLOWED_EXTENSIONS = {
        "txt",
        "md",
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "csv",
    }

    EXECUTABLE_EXTENSIONS = {
        "exe",
        "dll",
        "so",
        "dylib",
        "msi",
        "apk",
        "app",
        "bat",
        "cmd",
        "com",
        "sh",
        "bash",
        "zsh",
        "fish",
        "ps1",
        "vbs",
        "jar",
        "run",
        "bin",
    }

    EXECUTABLE_CONTENT_TYPES = {
        "application/x-msdownload",
        "application/x-msdos-program",
        "application/x-executable",
        "application/x-sh",
        "application/x-bat",
        "application/x-powershell",
        "application/java-archive",
    }

    CHAT_CONTENT_TYPE_OVERRIDES = {
        "md": {"text/markdown", "text/plain"},
        "txt": {"text/plain"},
        "csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"},
    }

    @classmethod
    def document_allowed_extensions(cls) -> list[str]:
        return sorted({item for item in ExtractorRegistry.supported_extensions() if item})

    @classmethod
    def document_allowed_content_types_by_extension(
        cls,
        allowed_extensions: Optional[Iterable[str]] = None,
    ) -> dict[str, list[str]]:
        extensions = allowed_extensions or cls.document_allowed_extensions()
        result: dict[str, list[str]] = {}
        for raw_ext in extensions:
            ext = (raw_ext or "").strip().lower().lstrip(".")
            if not ext:
                continue
            allowed = cls.DOCUMENT_CONTENT_TYPES.get(ext)
            if allowed:
                result[ext] = sorted(allowed)
        return result

    @classmethod
    def validate_document_upload(
        cls,
        *,
        filename: str,
        content_type: Optional[str],
        size_bytes: int,
    ) -> UploadDescriptor:
        normalized_filename = cls._validate_common(filename=filename, size_bytes=size_bytes)
        ext = cls._detect_extension(normalized_filename)
        if not ext:
            raise UploadValidationError("File extension is required")

        supported_extensions = set(cls.document_allowed_extensions())
        if ext not in supported_extensions:
            allowed = ", ".join(sorted(supported_extensions))
            raise UploadValidationError(
                f"Unsupported file extension '.{ext}'. Allowed extensions: {allowed}"
            )

        cls._validate_content_type(ext=ext, content_type=content_type)
        return UploadDescriptor(
            filename=normalized_filename,
            extension=ext,
            content_type=cls._normalize_content_type(content_type),
            size_bytes=size_bytes,
        )

    @classmethod
    def validate_csv_upload(
        cls,
        *,
        filename: str,
        content_type: Optional[str],
        size_bytes: int,
    ) -> UploadDescriptor:
        descriptor = cls.validate_document_upload(
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        if descriptor.extension != "csv":
            raise UploadValidationError("CSV upload requires a .csv file")
        return descriptor

    @classmethod
    def validate_chat_upload(
        cls,
        *,
        filename: str,
        content_type: Optional[str],
        size_bytes: int,
        max_bytes: int,
        allowed_extensions: Optional[Iterable[str]] = None,
    ) -> UploadDescriptor:
        normalized_filename = cls._validate_common_with_limit(
            filename=filename,
            size_bytes=size_bytes,
            max_bytes=max_bytes,
        )
        ext = cls._detect_extension(normalized_filename)
        if not ext:
            raise UploadValidationError("File extension is required")

        allowed_set = {
            item.strip().lower().lstrip(".")
            for item in (allowed_extensions or cls.CHAT_DEFAULT_ALLOWED_EXTENSIONS)
            if item and item.strip()
        }
        if ext not in allowed_set:
            allowed = ", ".join(sorted(allowed_set))
            raise UploadValidationError(
                f"Unsupported file extension '.{ext}'. Allowed extensions: {allowed}"
            )

        normalized_ct = cls._normalize_content_type(content_type)
        if ext in cls.EXECUTABLE_EXTENSIONS:
            raise UploadValidationError(
                f"Executable files are not allowed ('.{ext}')"
            )
        if normalized_ct and normalized_ct in cls.EXECUTABLE_CONTENT_TYPES:
            raise UploadValidationError(
                f"Executable content type is not allowed ('{normalized_ct}')"
            )
        cls._validate_chat_content_type(ext=ext, content_type=normalized_ct)

        return UploadDescriptor(
            filename=normalized_filename,
            extension=ext,
            content_type=normalized_ct,
            size_bytes=size_bytes,
        )

    @classmethod
    def _validate_common(cls, *, filename: str, size_bytes: int) -> str:
        normalized_filename = (filename or "").strip()
        if not normalized_filename:
            raise UploadValidationError("Filename is required")
        if size_bytes <= 0:
            raise UploadValidationError("Uploaded file is empty")

        settings = get_settings()
        if size_bytes > settings.UPLOAD_MAX_BYTES:
            raise UploadValidationError(
                f"Uploaded file exceeds max size of {settings.UPLOAD_MAX_BYTES} bytes"
            )
        return normalized_filename

    @classmethod
    def _validate_common_with_limit(cls, *, filename: str, size_bytes: int, max_bytes: int) -> str:
        normalized_filename = (filename or "").strip()
        if not normalized_filename:
            raise UploadValidationError("Filename is required")
        if size_bytes <= 0:
            raise UploadValidationError("Uploaded file is empty")
        if size_bytes > max_bytes:
            raise UploadValidationError(
                f"Uploaded file exceeds max size of {max_bytes} bytes"
            )
        return normalized_filename

    @classmethod
    def _validate_content_type(cls, *, ext: str, content_type: Optional[str]) -> None:
        normalized = cls._normalize_content_type(content_type)
        if normalized is None or normalized in cls.GENERIC_CONTENT_TYPES:
            return

        allowed = cls.DOCUMENT_CONTENT_TYPES.get(ext)
        if allowed is None:
            return
        if normalized not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise UploadValidationError(
                f"Content type '{normalized}' does not match '.{ext}' upload. "
                f"Allowed content types: {allowed_text}"
            )

    @classmethod
    def _validate_chat_content_type(cls, *, ext: str, content_type: Optional[str]) -> None:
        if content_type is None or content_type in cls.GENERIC_CONTENT_TYPES:
            return

        allowed = cls.chat_allowed_content_types_by_extension([ext]).get(ext)
        if not allowed:
            return
        if content_type not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise UploadValidationError(
                f"Content type '{content_type}' does not match '.{ext}' upload. "
                f"Allowed content types: {allowed_text}"
            )

    @classmethod
    def chat_allowed_content_types_by_extension(
        cls,
        allowed_extensions: Iterable[str],
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for raw_ext in allowed_extensions:
            ext = (raw_ext or "").strip().lower().lstrip(".")
            if not ext:
                continue
            allowed = cls.CHAT_CONTENT_TYPE_OVERRIDES.get(ext) or cls.DOCUMENT_CONTENT_TYPES.get(ext)
            if allowed:
                result[ext] = sorted(allowed)
        return result

    @staticmethod
    def _normalize_content_type(content_type: Optional[str]) -> Optional[str]:
        if content_type is None:
            return None
        return content_type.split(";", 1)[0].strip().lower()

    @staticmethod
    def _detect_extension(filename: str) -> str:
        if "." not in filename:
            return ""
        return filename.rsplit(".", 1)[-1].strip().lower()
