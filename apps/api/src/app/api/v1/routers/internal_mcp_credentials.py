from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.exceptions import UnauthorizedError
from app.services.mcp_credential_broker_service import MCPCredentialBrokerService

router = APIRouter(prefix="/internal/mcp/credentials", tags=["internal-mcp-credentials"])


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
    db: AsyncSession = Depends(db_session),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing Bearer token for MCP credential resolve")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError("Empty Bearer token for MCP credential resolve")

    broker = MCPCredentialBrokerService(db)
    resolved = await broker.resolve_access_token(token)
    return MCPCredentialResolveResponse(
        credential_id=resolved.credential_id,
        instance_id=resolved.instance_id,
        auth_type=resolved.auth_type,
        owner_type=resolved.owner_type,
        payload=resolved.payload,
        expires_at=resolved.expires_at,
    )
