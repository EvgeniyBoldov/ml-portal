from __future__ import annotations

import io
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional

from botocore.exceptions import ClientError
from fastapi import UploadFile
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import PresignOptions, s3_manager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.chat_attachment import ChatAttachment
from app.models.platform_settings import PlatformSettings
from app.services.file_delivery_service import FileDeliveryService
from app.core.exceptions import ChatAttachmentNotFoundError
from app.services.upload_intake_policy import UploadIntakePolicy
from app.storage.paths import calculate_file_checksum

logger = get_logger(__name__)

DEFAULT_CHAT_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_CHAT_UPLOAD_ALLOWED_EXTENSIONS = "txt,md,pdf,doc,docx,xls,xlsx,csv"


@dataclass(frozen=True)
class ChatUploadPolicy:
    max_bytes: int
    allowed_extensions: List[str]
    allowed_content_types_by_extension: dict[str, list[str]]


class ChatAttachmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def get_upload_policy(self) -> ChatUploadPolicy:
        row = await self._get_platform_settings_row()
        max_bytes = row.chat_upload_max_bytes if row and row.chat_upload_max_bytes else DEFAULT_CHAT_UPLOAD_MAX_BYTES
        allowed_csv = (
            row.chat_upload_allowed_extensions
            if row and row.chat_upload_allowed_extensions
            else DEFAULT_CHAT_UPLOAD_ALLOWED_EXTENSIONS
        )
        allowed_extensions = [
            item.strip().lower().lstrip(".")
            for item in allowed_csv.split(",")
            if item.strip()
        ]
        if not allowed_extensions:
            allowed_extensions = sorted(UploadIntakePolicy.CHAT_DEFAULT_ALLOWED_EXTENSIONS)
        allowed_content_types_by_extension = UploadIntakePolicy.chat_allowed_content_types_by_extension(
            allowed_extensions
        )
        return ChatUploadPolicy(
            max_bytes=max_bytes,
            allowed_extensions=allowed_extensions,
            allowed_content_types_by_extension=allowed_content_types_by_extension,
        )

    async def upload_attachment(
        self,
        *,
        tenant_id: str,
        chat_id: str,
        owner_id: str,
        file: UploadFile,
    ) -> dict[str, Any]:
        content = await file.read()
        policy = await self.get_upload_policy()
        descriptor = UploadIntakePolicy.validate_chat_upload(
            filename=file.filename or f"upload_{uuid.uuid4()}",
            content_type=file.content_type,
            size_bytes=len(content),
            max_bytes=policy.max_bytes,
            allowed_extensions=policy.allowed_extensions,
        )

        attachment_id = uuid.uuid4()
        checksum = calculate_file_checksum(content)
        safe_name = self._sanitize_filename(descriptor.filename)
        key = (
            f"tenants/{tenant_id}/chats/{chat_id}/attachments/{attachment_id}/"
            f"{checksum}_{safe_name}"
        )
        bucket = self.settings.S3_BUCKET_CHAT_UPLOADS
        await self._ensure_bucket(bucket)

        uploaded = await s3_manager.upload_fileobj(
            bucket=bucket,
            key=key,
            file_obj=io.BytesIO(content),
            metadata={"chat_id": chat_id, "owner_id": owner_id, "checksum": checksum},
        )
        if not uploaded:
            raise RuntimeError(f"Failed to upload file to s3://{bucket}/{key}")

        row = await self._create_attachment_row(
            attachment_id=attachment_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
            owner_id=owner_id,
            file_name=descriptor.filename,
            file_ext=descriptor.extension,
            content_type=descriptor.content_type,
            size_bytes=descriptor.size_bytes,
            checksum=checksum,
            bucket=bucket,
            key=key,
            status="uploaded",
        )
        return self._serialize_attachment(row)

    async def create_generated_attachment(
        self,
        *,
        tenant_id: str,
        chat_id: str,
        owner_id: str,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> dict[str, Any]:
        safe_name = self._sanitize_filename(filename)
        extension = safe_name.rsplit(".", 1)[-1].strip().lower() if "." in safe_name else "txt"
        attachment_id = uuid.uuid4()
        checksum = calculate_file_checksum(content)
        key = (
            f"tenants/{tenant_id}/chats/{chat_id}/generated/{attachment_id}/"
            f"{checksum}_{safe_name}"
        )
        bucket = self.settings.S3_BUCKET_CHAT_UPLOADS
        await self._ensure_bucket(bucket)
        uploaded = await s3_manager.upload_fileobj(
            bucket=bucket,
            key=key,
            file_obj=io.BytesIO(content),
            metadata={"chat_id": chat_id, "owner_id": owner_id, "checksum": checksum, "generated": "true"},
        )
        if not uploaded:
            raise RuntimeError(f"Failed to upload generated file to s3://{bucket}/{key}")

        row = await self._create_attachment_row(
            attachment_id=attachment_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
            owner_id=owner_id,
            file_name=safe_name,
            file_ext=extension,
            content_type=content_type,
            size_bytes=len(content),
            checksum=checksum,
            bucket=bucket,
            key=key,
            status="generated",
        )
        return self._serialize_attachment(row)

    async def get_owned_attachments(
        self,
        *,
        tenant_id: str,
        chat_id: str,
        owner_id: str,
        attachment_ids: Iterable[str],
    ) -> list[ChatAttachment]:
        normalized: list[uuid.UUID] = []
        for raw in attachment_ids:
            try:
                normalized.append(uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                raise ChatAttachmentNotFoundError(f"Invalid attachment id: {raw}")
        if not normalized:
            return []

        rows = await self._fetch_rows(
            select(ChatAttachment).where(
                and_(
                    ChatAttachment.id.in_(normalized),
                    ChatAttachment.tenant_id == uuid.UUID(tenant_id),
                    ChatAttachment.chat_id == uuid.UUID(chat_id),
                    ChatAttachment.owner_id == uuid.UUID(owner_id),
                )
            )
        )
        if len(rows) != len(set(normalized)):
            raise ChatAttachmentNotFoundError("Some attachments were not found or not accessible")
        return rows

    async def get_owned_attachments_any_chat(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        attachment_ids: Iterable[str],
    ) -> list[ChatAttachment]:
        normalized: list[uuid.UUID] = []
        for raw in attachment_ids:
            try:
                normalized.append(uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                raise ChatAttachmentNotFoundError(f"Invalid attachment id: {raw}")
        if not normalized:
            return []

        rows = await self._fetch_rows(
            select(ChatAttachment).where(
                and_(
                    ChatAttachment.id.in_(normalized),
                    ChatAttachment.tenant_id == uuid.UUID(tenant_id),
                    ChatAttachment.owner_id == uuid.UUID(owner_id),
                )
            )
        )
        if len(rows) != len(set(normalized)):
            raise ChatAttachmentNotFoundError("Some attachments were not found or not accessible")
        return rows

    async def bind_to_message(
        self,
        *,
        tenant_id: str,
        chat_id: str,
        owner_id: str,
        attachment_ids: Iterable[str],
        message_id: str,
    ) -> list[ChatAttachment]:
        rows = await self.get_owned_attachments(
            tenant_id=tenant_id,
            chat_id=chat_id,
            owner_id=owner_id,
            attachment_ids=attachment_ids,
        )
        linked_at = datetime.now(timezone.utc)
        target_message_id = uuid.UUID(message_id)
        for row in rows:
            row.message_id = target_message_id
            row.linked_at = linked_at
        await self.session.flush()
        return rows

    async def get_download_link(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        attachment_id: str,
        expires_in: int = 3600,
    ) -> dict[str, Any]:
        try:
            att_id = uuid.UUID(attachment_id)
        except (TypeError, ValueError):
            raise ChatAttachmentNotFoundError(f"Invalid attachment id: {attachment_id}")

        rows = await self._fetch_rows(
            select(ChatAttachment).where(
                and_(
                    ChatAttachment.id == att_id,
                    ChatAttachment.tenant_id == uuid.UUID(tenant_id),
                    ChatAttachment.owner_id == uuid.UUID(owner_id),
                )
            )
        )
        if not rows:
            raise ChatAttachmentNotFoundError("Attachment not found")
        row = rows[0]

        url = await s3_manager.generate_presigned_url(
            bucket=row.storage_bucket,
            key=row.storage_key,
            options=PresignOptions(
                expires_in=expires_in,
                method="GET",
                response_headers={
                    "ResponseContentDisposition": f'attachment; filename="{row.file_name}"',
                    "ResponseContentType": row.content_type or "application/octet-stream",
                },
            ),
        )
        return {
            "id": str(row.id),
            "file_name": row.file_name,
            "content_type": row.content_type,
            "size_bytes": row.size_bytes,
            "url": url,
            "expires_in": expires_in,
        }

    @staticmethod
    def to_meta(attachments: list[ChatAttachment]) -> list[dict[str, Any]]:
        return [ChatAttachmentService._serialize_attachment(item) for item in attachments]

    @staticmethod
    def _serialize_attachment(row: ChatAttachment) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "file_id": FileDeliveryService.make_chat_attachment_file_id(str(row.id)),
            "file_name": row.file_name,
            "file_ext": row.file_ext,
            "content_type": row.content_type,
            "size_bytes": row.size_bytes,
            "status": row.status,
        }

    async def build_prompt_context(
        self,
        *,
        attachments: list[ChatAttachment],
        max_chars_per_file: int = 12000,
    ) -> str:
        if not attachments:
            return ""
        lines: list[str] = [
            "User attached files. Use them as primary context when relevant.",
        ]
        for item in attachments:
            file_id = FileDeliveryService.make_chat_attachment_file_id(str(item.id))
            lines.append(
                f"- file_id={file_id}; name={item.file_name}; type={item.content_type or 'unknown'}; size={item.size_bytes}"
            )
            text_snippet = await self._load_text_content(item, max_chars=max_chars_per_file)
            if text_snippet:
                lines.append(f"```file name={item.file_name}")
                lines.append(text_snippet)
                lines.append("```")
            else:
                lines.append(
                    "(binary or unsupported text extraction; if needed, ask user to provide text or supported format)"
                )
        return "\n".join(lines)

    async def _load_text_content(self, row: ChatAttachment, *, max_chars: int) -> Optional[str]:
        text_extensions = {"txt", "md", "csv", "tsv", "json", "yaml", "yml", "log", "sql", "xml", "html"}
        ext = (row.file_ext or "").strip().lower()
        if ext not in text_extensions:
            return None
        payload = await s3_manager.get_object(row.storage_bucket, row.storage_key)
        if not payload:
            return None
        decoded = payload.decode("utf-8", errors="replace")
        if len(decoded) <= max_chars:
            return decoded
        return f"{decoded[:max_chars]}\n...[truncated]"

    async def _get_platform_settings_row(self) -> PlatformSettings | None:
        result = await self.session.execute(select(PlatformSettings).limit(1))
        return result.scalar_one_or_none()

    async def _fetch_rows(self, stmt: Select[tuple[ChatAttachment]]) -> list[ChatAttachment]:
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _create_attachment_row(
        self,
        *,
        attachment_id: uuid.UUID,
        tenant_id: str,
        chat_id: str,
        owner_id: str,
        file_name: str,
        file_ext: str,
        content_type: Optional[str],
        size_bytes: int,
        checksum: str,
        bucket: str,
        key: str,
        status: str,
    ) -> ChatAttachment:
        row = ChatAttachment(
            id=attachment_id,
            tenant_id=uuid.UUID(tenant_id),
            chat_id=uuid.UUID(chat_id),
            owner_id=uuid.UUID(owner_id),
            file_name=file_name,
            file_ext=file_ext,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum=checksum,
            storage_bucket=bucket,
            storage_key=key,
            status=status,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def _ensure_bucket(self, bucket: str) -> None:
        client = s3_manager._get_client()
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError:
            try:
                client.create_bucket(Bucket=bucket)
                logger.info("Created S3 bucket for chat uploads: %s", bucket)
            except Exception as exc:
                logger.warning("Failed to create S3 bucket %s: %s", bucket, exc)

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        base = os.path.basename(name).strip()
        if not base:
            return "file"
        return base.replace("/", "_").replace("\\", "_")
