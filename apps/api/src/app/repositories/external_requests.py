from uuid import UUID

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_turn import ChatTurn
from app.models.durable_runtime import (
    DurableRuntimeCommand,
    DurableRuntimeEvent,
    DurableRuntimePause,
    DurableRuntimeRun,
    DurableRuntimeSegment,
)
from app.models.user import Users
from app.schemas.admin_external_requests import (
    ExternalRequestDetail,
    ExternalRequestListItem,
    ExternalRequestPage,
    ExternalRequestTimelineItem,
)

_run = DurableRuntimeRun
_source = _run.recipient["assignment"]["source"]
_source_type = _source["type"].astext
_source_id = _source["id"].astext
_external = (_source_type.is_not(None), _source_id.is_not(None))
_request_text = func.coalesce(_run.request_payload["content"].astext, "")
_summary_columns = (
    _run.id.label("run_id"),
    (_source_type + literal(":") + _source_id).label("source"),
    _run.status,
    func.coalesce(func.nullif(Users.full_name, ""), Users.login).label("user_name"),
    _run.created_at,
    _run.updated_at,
)


async def list_external_requests(session: AsyncSession, *, limit: int, offset: int) -> ExternalRequestPage:
    total = await session.scalar(select(func.count()).select_from(_run).where(*_external))
    statement = (
        select(*_summary_columns, func.substr(_request_text, 1, 181).label("text_preview"))
        .join(Users, Users.id == _run.owner_user_id)
        .where(*_external)
        .order_by(_run.created_at.desc(), _run.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(statement)).mappings()
    return ExternalRequestPage(items=[ExternalRequestListItem.model_validate(row) for row in rows], total=total or 0)


async def get_external_request(session: AsyncSession, run_id: UUID) -> ExternalRequestDetail | None:
    statement = (
        select(*_summary_columns, _request_text.label("text"), ChatTurn.completed_at)
        .join(Users, Users.id == _run.owner_user_id)
        .join(ChatTurn, ChatTurn.id == _run.chat_turn_id)
        .where(_run.id == run_id, *_external)
    )
    row = (await session.execute(statement)).mappings().one_or_none()
    if row is None:
        return None
    timeline = await _load_timeline(session, run_id)
    return ExternalRequestDetail(**row, timeline=timeline)


async def _load_timeline(session: AsyncSession, run_id: UUID) -> list[ExternalRequestTimelineItem]:
    events = await session.scalars(
        select(DurableRuntimeEvent)
        .where(DurableRuntimeEvent.run_id == run_id)
        .order_by(DurableRuntimeEvent.sequence)
    )
    pauses = await session.scalars(
        select(DurableRuntimePause)
        .where(DurableRuntimePause.run_id == run_id)
        .order_by(DurableRuntimePause.created_at, DurableRuntimePause.id)
    )
    answers = await session.scalars(
        select(DurableRuntimeCommand)
        .where(DurableRuntimeCommand.run_id == run_id, DurableRuntimeCommand.kind == "answer")
        .order_by(DurableRuntimeCommand.created_at, DurableRuntimeCommand.id)
    )
    timer_resumes = await session.scalars(
        select(DurableRuntimeSegment)
        .where(DurableRuntimeSegment.run_id == run_id, DurableRuntimeSegment.reason == "timer_elapsed")
        .order_by(DurableRuntimeSegment.sequence)
    )

    silent_pauses = {str(pause.id): pause for pause in pauses}
    timeline = []
    for event in events:
        pause = silent_pauses.pop(str(event.payload.get("pause_id")), None)
        text = event.payload.get("content") or event.payload.get("text") or event.payload.get("error")
        timeline.append(ExternalRequestTimelineItem(
            id=event.id,
            kind=event.kind,
            occurred_at=event.created_at,
            text=text if isinstance(text, str) else None,
            wake_at=pause.wake_at if pause else None,
            resolved_at=pause.resolved_at if pause else None,
            delivery_status=event.status,
            delivered_at=event.delivered_at,
            delivery_attempts=event.attempts,
        ))

    timeline.extend(ExternalRequestTimelineItem(
        id=pause.id,
        kind=pause.kind,
        occurred_at=pause.created_at,
        wake_at=pause.wake_at,
        resolved_at=pause.resolved_at,
    ) for pause in silent_pauses.values())
    timeline.extend(ExternalRequestTimelineItem(
        id=answer.id,
        kind="answer",
        occurred_at=answer.created_at,
        answer=answer.payload.get("response"),
    ) for answer in answers)
    timeline.extend(ExternalRequestTimelineItem(
        id=segment.id,
        kind="timer_elapsed",
        occurred_at=segment.created_at,
    ) for segment in timer_resumes)
    return sorted(timeline, key=lambda item: item.occurred_at)
