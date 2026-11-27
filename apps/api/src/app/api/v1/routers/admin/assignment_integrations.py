from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, require_admin
from app.models.assignment_integration import AssignmentIntegration
from app.services.assignment_integrations import AssignmentIntegrationsService, DuplicateIntegrationSource

router = APIRouter(prefix="/integrations", tags=["integrations"], dependencies=[Depends(require_admin)])
Session = Annotated[AsyncSession, Depends(db_uow)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class IntegrationUpdate(BaseModel):
    name: Name
    connector_id: UUID
    is_active: bool = True


class IntegrationCreate(IntegrationUpdate):
    source: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}:[a-z0-9][a-z0-9_-]{0,47}$")


class IntegrationView(IntegrationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class TokenCreate(BaseModel):
    name: Name
    expires_days: int | None = Field(default=None, ge=1, le=3650)


class TokenView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    token_prefix: str
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class TokenIssued(TokenView):
    token: str


async def _integration(integration_id: UUID, session: Session) -> AssignmentIntegration:
    row = await session.get(AssignmentIntegration, integration_id)
    if row is None:
        raise HTTPException(404, "Интеграция не найдена")
    return row


Integration = Annotated[AssignmentIntegration, Depends(_integration)]


async def _save(session: AsyncSession, row: AssignmentIntegration, data: IntegrationUpdate) -> AssignmentIntegration:
    try:
        return await AssignmentIntegrationsService(session).save(
            row, name=data.name, connector_id=data.connector_id, is_active=data.is_active,
        )
    except DuplicateIntegrationSource as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("", response_model=list[IntegrationView])
async def list_integrations(session: Session):
    return await AssignmentIntegrationsService(session).repo.list_integrations()


@router.post("", response_model=IntegrationView, status_code=201)
async def create_integration(data: IntegrationCreate, session: Session):
    return await _save(session, AssignmentIntegration(source=data.source), data)


@router.get("/{integration_id}", response_model=IntegrationView)
async def get_integration(row: Integration):
    return row


@router.put("/{integration_id}", response_model=IntegrationView)
async def update_integration(data: IntegrationUpdate, row: Integration, session: Session):
    return await _save(session, row, data)


@router.get("/{integration_id}/tokens", response_model=list[TokenView])
async def list_tokens(row: Integration, session: Session):
    return await AssignmentIntegrationsService(session).repo.list_tokens(row.id)


@router.post("/{integration_id}/tokens", response_model=TokenIssued, status_code=201)
async def issue_token(data: TokenCreate, row: Integration, session: Session, response: Response):
    token, raw = await AssignmentIntegrationsService(session).issue(row.id, data.name, data.expires_days)
    response.headers["Cache-Control"] = "no-store"
    return TokenIssued(token=raw, **TokenView.model_validate(token).model_dump())


@router.delete("/{integration_id}/tokens/{token_id}", status_code=204)
async def revoke_token(token_id: UUID, row: Integration, session: Session) -> Response:
    service = AssignmentIntegrationsService(session)
    token = await service.repo.token(row.id, token_id)
    if token is None:
        raise HTTPException(404, "Токен не найден")
    await service.revoke(token)
    return Response(status_code=204)
