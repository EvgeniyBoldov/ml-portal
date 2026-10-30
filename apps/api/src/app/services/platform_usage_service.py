"""Usage accounting runs before diagnostic log admission, with a strict origin allowlist."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.model_registry import Model, ModelType
from app.models.agent import Agent
from app.repositories.platform_usage_repository import PlatformUsageRepository

logger = get_logger(__name__)
USAGE_EVENTS = {
    "run_start": "run", "run_end": "run",
    "agent_start": "agent", "agent_end": "agent",
    "llm_request": "llm", "llm_response": "llm",
    "protocol_retry": "llm",
}


async def record_usage(context: Any, event_type: str, payload: dict[str, Any], session_factory: Any) -> None:
    if context.origin not in {"chat", "shadow", "sandbox", "worker"} or context.user_id is None or event_type not in USAGE_EVENTS:
        return
    entity_id = payload.get("entity_id") or (str(context.run_id) if USAGE_EVENTS[event_type] == "run" else None)
    if not entity_id:
        return
    if USAGE_EVENTS[event_type] == "llm":
        entity_id = f"{entity_id}/{payload.get('usage_attempt', payload.get('attempt', payload.get('step', 1)))}"
    # Structured calls can emit an intermediate response and then its validated
    # result. Persist each transport attempt once, never sum repeated projections.
    is_start = event_type.endswith("_start") or event_type == "llm_request"
    now = datetime.now(timezone.utc)
    status = str(payload.get("status") or ("running" if is_start else "completed"))
    if event_type == "protocol_retry":
        status = "waiting_retry"
    usage = payload.get("usage") or {}
    tokens_in = usage.get("prompt_tokens", payload.get("tokens_in"))
    tokens_out = usage.get("completion_tokens", payload.get("tokens_out"))
    values = {
        "kind": USAGE_EVENTS[event_type], "entity_id": str(entity_id),
        "run_id": context.run_id, "origin": context.origin, "user_id": context.user_id,
        "agent_slug": payload.get("agent_slug"), "model_alias": payload.get("model"),
        "started_at": now, "finished_at": None if is_start else now,
        "status": status, "error_code": (str(payload["error_code"])[:120] if payload.get("error_code") else
            f"protocol_{payload.get('reason', 'retry')}"[:120] if event_type == "protocol_retry" else None),
        "duration_ms": payload.get("duration_ms"),
        "tokens_in": max(0, tokens_in) if isinstance(tokens_in, int) else None,
        "tokens_out": max(0, tokens_out) if isinstance(tokens_out, int) else None,
        "token_source": payload.get("token_source") or (
            "provider" if usage else "unknown"
            if USAGE_EVENTS[event_type] == "llm"
            and event_type == "llm_response"
            and bool(payload.get("terminal")) else None
        ),
    }
    try:
        if session_factory is None:
            from app.core.db import get_session_factory
            session_factory = get_session_factory()
        async with session_factory() as session:
            async with session.begin():
                if values["kind"] == "agent" and not await session.scalar(
                    select(Agent.id).where(Agent.slug == values["agent_slug"]).limit(1)
                ):
                    # System memory components use the same lifecycle vocabulary.
                    # They are not catalog agents and must not inflate adoption.
                    return
                if values["kind"] == "llm" and not values["model_alias"] and event_type != "protocol_retry":
                    values["model_alias"] = await session.scalar(select(Model.alias).where(
                        Model.type == ModelType.LLM_CHAT, Model.default_for_type.is_(True),
                        Model.enabled.is_(True), Model.deleted_at.is_(None),
                    ).order_by(Model.created_at).limit(1))
                await PlatformUsageRepository(session).upsert(values, is_start=is_start)
    except Exception:
        # Accounting must not turn a successful user operation into a failure.
        logger.exception("Usage accounting failed kind=%s run_id=%s", values["kind"], context.run_id)
