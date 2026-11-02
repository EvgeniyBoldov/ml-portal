from __future__ import annotations

import logging
import re
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.exceptions import UnauthorizedError
from app.services.mcp_credential_broker_service import MCPCredentialBrokerService

router = APIRouter(prefix="/internal/mcp/credentials", tags=["internal-mcp-credentials"])
logger = logging.getLogger(__name__)


def _request_id(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate if re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", candidate) else "-"


class MCPCredentialResolveResponse(BaseModel):
    credential_id: UUID
    instance_id: UUID
    auth_type: str
    owner_type: str
    payload: Dict[str, Any]
    expires_at: int


@router.post("/resolve", response_model=MCPCredentialResolveResponse)
async def resolve_mcp_credential(
    authorization: str | None = Header(default=None, alias="Authorization"),
    portal_request_id: str | None = Header(default=None, alias="x-portal-request-id"),
    db: AsyncSession = Depends(db_session),
):
    request_id = _request_id(portal_request_id)
    logger.info(
        "mcp_credential_broker_started request_id=%s authorization_present=%s",
        request_id,
        bool(authorization),
    )
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning(
            "mcp_credential_broker_failed request_id=%s stage=authorization error_type=MissingBearer",
            request_id,
        )
        raise UnauthorizedError("Missing Bearer token for MCP credential resolve")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        logger.warning(
            "mcp_credential_broker_failed request_id=%s stage=authorization error_type=EmptyBearer",
            request_id,
        )
        raise UnauthorizedError("Empty Bearer token for MCP credential resolve")

    broker = MCPCredentialBrokerService(db)
    try:
        resolved = await broker.resolve_access_token(token)
    except Exception as exc:
        logger.warning(
            "mcp_credential_broker_failed request_id=%s stage=resolve_access_token error_type=%s http_status=%s",
            request_id,
            type(exc).__name__,
            getattr(exc, "status_code", "-"),
        )
        raise
    logger.info(
        "mcp_credential_broker_completed request_id=%s credential_id=%s data_instance_id=%s "
        "auth_type=%s owner_type=%s",
        request_id,
        resolved.credential_id,
        resolved.instance_id,
        resolved.auth_type,
        resolved.owner_type,
    )
    return MCPCredentialResolveResponse(
        credential_id=resolved.credential_id,
        instance_id=resolved.instance_id,
        auth_type=resolved.auth_type,
        owner_type=resolved.owner_type,
        payload=resolved.payload,
        expires_at=resolved.expires_at,
    )
