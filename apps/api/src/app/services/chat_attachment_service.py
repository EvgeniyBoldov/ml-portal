from __future__ import annotations

import io
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional

from botocore.exceptions import ClientError
from fastapi import UploadFile
from sqlalchemy import Select, and_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.chat_attachment import ChatAttachment
from app.models.platform_settings import PlatformSettings
from app.core.exceptions import ChatAttachmentNotFoundError
from app.runtime.contracts import AttachmentContext, AttachmentRef
from app.services.upload_intake_policy import UploadIntakePolicy
from app.services.chat_artifact_reference_service import (
    ArtifactTarget,
    ChatArtifactReferenceNotFound,
    ChatArtifactReferenceService,
)
from app.models.chat_artifact_reference import ChatArtifactReference
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
            f"chats/{chat_id}/attachments/{attachment_id}/"
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
        reference = await ChatArtifactReferenceService(self.session).register(
            chat_id=chat_id,
            owner_id=owner_id,
            target=ArtifactTarget(
                kind="chat_attachment",
                target_id=str(row.id),
                display_name=row.file_name,
                content_type=row.content_type,
                size_bytes=row.size_bytes,
                metadata={"status": row.status},
            ),
        )
        return self._artifact_metadata(reference)

    async def create_generated_attachment(
        self,
        *,
        chat_id: Optional[str],
        owner_id: str,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        safe_name = self._sanitize_filename(filename)
        extension = safe_name.rsplit(".", 1)[-1].strip().lower() if "." in safe_name else "txt"
        attachment_id = uuid.uuid4()
        checksum = calculate_file_checksum(content)
        if chat_id:
            key = (
                f"chats/{chat_id}/generated/{attachment_id}/"
                f"{checksum}_{safe_name}"
            )
        else:
            key = (
                f"artifacts/generated/{owner_id}/{attachment_id}/"
                f"{checksum}_{safe_name}"
            )
        bucket = self.settings.S3_BUCKET_CHAT_UPLOADS
        await self._ensure_bucket(bucket)
        supplied_metadata = dict(metadata or {})
        metadata = {"owner_id": owner_id, "checksum": checksum, "generated": "true"}
        if chat_id:
            metadata["chat_id"] = chat_id
        uploaded = await s3_manager.upload_fileobj(
            bucket=bucket,
            key=key,
            file_obj=io.BytesIO(content),
            metadata=metadata,
        )
        if not uploaded:
            raise RuntimeError(f"Failed to upload generated file to s3://{bucket}/{key}")

        row = None
        try:
            row = await self._create_attachment_row(
                attachment_id=attachment_id,
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
            if chat_id:
                reference = await ChatArtifactReferenceService(self.session).register(
                    chat_id=chat_id,
                    owner_id=owner_id,
                    target=ArtifactTarget(
                        kind="chat_attachment",
                        target_id=str(row.id),
                        display_name=row.file_name,
                        content_type=row.content_type,
                        size_bytes=row.size_bytes,
                        metadata={"status": row.status, **supplied_metadata},
                    ),
                )
                return self._artifact_metadata(reference)
            raise RuntimeError("Generated artifacts require a chat-scoped artifact reference")
        except Exception:
            # A generated file is only valid once both storage and the
            # chat-scoped artifact reference exist. Remove partial state and
            # let the caller retry safely.
            if row is not None:
                try:
                    await self.session.delete(row)
                    await self.session.flush()
                except Exception:
                    logger.exception("Failed to rollback generated attachment row %s", row.id)
            try:
                await s3_manager.delete_object(bucket, key)
            except Exception:
                logger.exception("Failed to rollback generated object s3://%s/%s", bucket, key)
            raise

    async def get_owned_attachments(
        self,
        *,
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
                    ChatAttachment.owner_id == uuid.UUID(owner_id),
                )
            )
        )
        if len(rows) != len(set(normalized)):
            raise ChatAttachmentNotFoundError("Some attachments were not found or not accessible")
        return rows

    async def list_owned_attachments_for_chat(
        self,
        *,
        chat_id: str,
        owner_id: str,
        statuses: Optional[Iterable[str]] = None,
    ) -> list[ChatAttachment]:
        conditions = [
            ChatAttachment.chat_id == uuid.UUID(chat_id),
            ChatAttachment.owner_id == uuid.UUID(owner_id),
        ]
        normalized_statuses = [str(item).strip() for item in (statuses or []) if str(item).strip()]
        if normalized_statuses:
            conditions.append(ChatAttachment.status.in_(normalized_statuses))
        return await self._fetch_rows(
            select(ChatAttachment)
            .where(and_(*conditions))
            .order_by(ChatAttachment.created_at.asc())
        )

    async def bind_to_message(
        self,
        *,
        chat_id: str,
        owner_id: str,
        attachment_ids: Iterable[str],
        message_id: str,
    ) -> list[ChatAttachment]:
        rows = await self.get_owned_attachments(
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

    async def bind_artifacts_to_message(
        self,
        *,
        chat_id: str,
        owner_id: str,
        artifact_ids: Iterable[str],
        message_id: str,
    ) -> list[ChatAttachment]:
        references = ChatArtifactReferenceService(self.session)
        attachment_ids: list[str] = []
        for artifact_id in artifact_ids:
            reference = await references.get_reference(
                artifact_id=str(artifact_id), chat_id=chat_id, owner_id=owner_id,
            )
            if reference.target_kind == "chat_attachment":
                attachment_ids.append(reference.target_id)
        return await self.bind_to_message(
            chat_id=chat_id,
            owner_id=owner_id,
            attachment_ids=attachment_ids,
            message_id=message_id,
        )

    async def artifact_metadata(
        self,
        *,
        artifact_ids: Iterable[str],
        chat_id: str,
        owner_id: str,
    ) -> list[dict[str, Any]]:
        """Return the only file metadata shape allowed outside artifact adapters."""
        references = ChatArtifactReferenceService(self.session)
        result: list[dict[str, Any]] = []
        for raw_id in artifact_ids:
            try:
                reference = await references.get_reference(
                    artifact_id=str(raw_id), chat_id=chat_id, owner_id=owner_id,
                )
            except ChatArtifactReferenceNotFound as exc:
                raise ChatAttachmentNotFoundError(str(exc)) from exc
            result.append({
                "artifact_id": str(reference.id),
                "file_name": reference.display_name or "artifact",
                "file_ext": self._extension(reference.display_name),
                "content_type": reference.content_type,
                "size_bytes": reference.size_bytes,
                "status": str((reference.metadata_snapshot or {}).get("status") or "ready"),
            })
        return result

    async def build_runtime_artifact_contexts(
        self,
        *,
        artifact_ids: Iterable[str],
        chat_id: str,
        owner_id: str,
        max_chars_per_file: int = 12000,
    ) -> list[AttachmentContext]:
        """Resolve opaque artifacts into bounded runtime contexts.

        Source identifiers and storage coordinates stay behind this boundary.
        """
        references = ChatArtifactReferenceService(self.session)
        contexts: list[AttachmentContext] = []
        seen: set[str] = set()
        for raw_id in artifact_ids:
            artifact_id = str(raw_id).strip()
            if not artifact_id or artifact_id in seen:
                continue
            seen.add(artifact_id)
            try:
                reference = await references.get_reference(
                    artifact_id=artifact_id, chat_id=chat_id, owner_id=owner_id,
                )
            except ChatArtifactReferenceNotFound as exc:
                raise ChatAttachmentNotFoundError(str(exc)) from exc
            snippet = ""
            snippet_status = "missing"
            readable = False
            truncated = False
            if reference.target_kind == "chat_attachment":
                try:
                    target_id = uuid.UUID(reference.target_id)
                except (TypeError, ValueError):
                    raise ChatAttachmentNotFoundError("Artifact attachment target is invalid")
                row = await self.session.get(ChatAttachment, target_id)
                if row is None or str(row.chat_id) != str(chat_id) or str(row.owner_id) != str(owner_id):
                    raise ChatAttachmentNotFoundError("Artifact attachment was not found or access denied")
                snippet = await self._load_text_content(row, max_chars=max_chars_per_file) or ""
                readable = bool(snippet)
                truncated = snippet.endswith("\n...[truncated]")
                if readable:
                    snippet_status = "truncated" if truncated else "ready"
                else:
                    payload = await s3_manager.get_object(row.storage_bucket, row.storage_key)
                    snippet_status = "unreadable" if payload else "missing"
            contexts.append(
                AttachmentContext(
                    ref=AttachmentRef(
                        artifact_id=str(reference.id),
                        file_name=reference.display_name or "artifact",
                        file_ext=self._extension(reference.display_name),
                        content_type=reference.content_type,
                        size_bytes=reference.size_bytes,
                        status=str((reference.metadata_snapshot or {}).get("status") or "ready"),
                    ),
                    snippet=snippet,
                    snippet_status=snippet_status,
                    readable=readable,
                    truncated=truncated,
                )
            )
        return contexts

    @staticmethod
    def _artifact_metadata(reference: ChatArtifactReference) -> dict[str, Any]:
        return {
            "artifact_id": str(reference.id),
            "file_name": reference.display_name or "artifact",
            "file_ext": ChatAttachmentService._extension(reference.display_name) or "",
            "content_type": reference.content_type,
            "size_bytes": reference.size_bytes or 0,
            "status": str((reference.metadata_snapshot or {}).get("status") or "ready"),
        }

    @staticmethod
    def _extension(file_name: Optional[str]) -> Optional[str]:
        name = str(file_name or "").strip()
        return name.rsplit(".", 1)[-1].lower() if "." in name else None


    async def delete_chat_attachments(
        self,
        *,
        chat_id: str,
        owner_id: str,
    ) -> int:
        rows = await self.list_owned_attachments_for_chat(chat_id=chat_id, owner_id=owner_id)
        for row in rows:
            try:
                await s3_manager.delete_object(row.storage_bucket, row.storage_key)
            except Exception as exc:
                logger.warning(
                    "Failed to delete chat attachment object %s: %s",
                    row.storage_key,
                    exc,
                )
        result = await self.session.execute(
            delete(ChatAttachment).where(
                and_(
                    ChatAttachment.chat_id == uuid.UUID(chat_id),
                    ChatAttachment.owner_id == uuid.UUID(owner_id),
                )
            )
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def cleanup_expired_detached_attachments(
        self,
        *,
        older_than: datetime,
    ) -> int:
        rows = await self._fetch_rows(
            select(ChatAttachment).where(
                and_(
                    ChatAttachment.chat_id.is_(None),
                    ChatAttachment.created_at < older_than,
                )
            )
        )
        for row in rows:
            try:
                await s3_manager.delete_object(row.storage_bucket, row.storage_key)
            except Exception as exc:
                logger.warning(
                    "Failed to delete detached attachment object %s: %s",
                    row.storage_key,
                    exc,
                )
        result = await self.session.execute(
            delete(ChatAttachment).where(
                and_(
                    ChatAttachment.chat_id.is_(None),
                    ChatAttachment.created_at < older_than,
                )
            )
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def _load_text_content(self, row: ChatAttachment, *, max_chars: int) -> Optional[str]:
        payload = await s3_manager.get_object(row.storage_bucket, row.storage_key)
        if not payload:
            return None
        from app.services.document_extraction_service import DocumentExtractionService, ExtractionRequest

        result = await DocumentExtractionService().extract(
            ExtractionRequest(
                payload=payload,
                filename=row.file_name or "",
                content_type=row.content_type,
                profile="chat_preview",
                max_chars=max_chars,
            )
        )
        if not result.text:
            return None
        decoded = result.text
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
        chat_id: Optional[str],
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
            chat_id=uuid.UUID(chat_id) if chat_id else None,
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
