"""Attachment endpoints: upload policy, upload, download, file-id."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ChatContext, db_session, get_current_user, resolve_chat_context
from app.core.security import UserCtx
from app.schemas.chats import ChatAttachmentDownloadResponse, ChatAttachmentUploadResponse, ChatUploadPolicyResponse
from app.core.exceptions import UploadValidationError
from app.services.chat_attachment_service import ChatAttachmentService
from app.services.file_delivery_service import FileDeliveryService

router = APIRouter()


@router.get("/uploads/policy", response_model=ChatUploadPolicyResponse)
async def get_chat_upload_policy(
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(get_current_user),
):
    service = ChatAttachmentService(session)
    policy = await service.get_upload_policy()
    return ChatUploadPolicyResponse(
        max_bytes=policy.max_bytes,
        allowed_extensions=policy.allowed_extensions,
        allowed_content_types_by_extension=policy.allowed_content_types_by_extension,
    )


@router.post("/{chat_id}/uploads", response_model=ChatAttachmentUploadResponse)
async def upload_chat_attachment(
    chat_id: str,
    file: UploadFile = File(...),
    chat_ctx: ChatContext = Depends(resolve_chat_context),
    session: AsyncSession = Depends(db_session),
):
    if not file:
        raise HTTPException(status_code=400, detail="File is required")

    service = ChatAttachmentService(session)
    try:
        uploaded = await service.upload_attachment(
            tenant_id=chat_ctx.tenant_id,
            chat_id=chat_ctx.chat_id,
            owner_id=chat_ctx.user_id,
            file=file,
        )
        await session.commit()
        return ChatAttachmentUploadResponse(**uploaded)
    except UploadValidationError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        await session.rollback()
        raise


@router.get("/attachments/{attachment_id}/download", response_model=ChatAttachmentDownloadResponse)
async def download_chat_attachment(
    attachment_id: str,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
):
    service = ChatAttachmentService(session)
    tenant_ids = current_user.tenant_ids or []
    if not tenant_ids:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")
    download_info = await service.get_download_link(
        tenant_id=str(tenant_ids[0]),
        owner_id=str(current_user.id),
        attachment_id=attachment_id,
    )
    return ChatAttachmentDownloadResponse(**download_info)


@router.get("/attachments/{attachment_id}/file-id")
async def get_chat_attachment_file_id(
    attachment_id: str,
    _: UserCtx = Depends(get_current_user),
):
    return {"file_id": FileDeliveryService.make_chat_attachment_file_id(attachment_id)}
