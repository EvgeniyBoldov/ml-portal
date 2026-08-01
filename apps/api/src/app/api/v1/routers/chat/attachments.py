"""Chat artifact upload and metadata endpoints."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ChatContext, db_session, get_current_user, resolve_chat_context
from app.core.security import UserCtx
from app.schemas.chats import ChatAttachmentUploadResponse, ChatUploadPolicyResponse
from app.core.exceptions import UploadValidationError
from app.services.chat_attachment_service import ChatAttachmentService

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
