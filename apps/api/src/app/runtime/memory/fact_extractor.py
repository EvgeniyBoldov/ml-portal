"""FactExtractor — turns one turn's raw material into typed FactDTOs.

Called by `MemoryWriter.finalize` at turn end. One LLM call per turn.
The heavy lifting (prompt assembly, JSON extraction, retries, role
config lookup) is delegated to `StructuredLLMCall`; this class only
owns:
    * the input/output Pydantic schemas
    * post-validation (subject sanity, value length, cap on count)
    * mapping raw LLM dicts into `FactDTO`s with the right ownership ids
"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, List, Optional, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.memory import FactScope, FactSource
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.runtime.memory.dto import FactDTO
from app.services.system_llm_role_service import SystemLLMRoleService

logger = get_logger(__name__)


# --- LLM contract -----------------------------------------------------------


class _LLMFactCandidate(BaseModel):
    """Shape the LLM is asked to produce per extracted fact."""
    scope: str
    subject: str
    value: str
    confidence: float = 1.0


class _LLMFactOutput(BaseModel):
    facts: List[_LLMFactCandidate] = Field(default_factory=list)


# --- Public domain input/output --------------------------------------------


class AgentResultSnippet(BaseModel):
    """Trimmed summary of an agent run, passed to the extractor."""
    agent: str
    summary: str
    success: bool = True


class KnownFactSnippet(BaseModel):
    subject: str
    value: str


# --- Extractor --------------------------------------------------------------


MAX_FACTS_PER_TURN = 8
MAX_SUBJECT_LEN = 200
MAX_VALUE_LEN = 500  # persisted as TEXT; cap so rogue outputs don't blow prompts later
CONFIDENCE_MIN = 0.6
MAX_VALUE_WORDS = 24

_EPHEMERAL_COUNT_SUBJECT_HINTS = (
    "count",
    "количество",
    "сколько",
    "total",
    "число",
)


class FactExtractor:
    """Extracts stable, atomic facts from a finished turn."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self._role_service = SystemLLMRoleService(session)
        self._structured = StructuredLLMCall(
            session=session, llm_client=llm_client
        )

    async def extract(
        self,
        *,
        user_message: str,
        agent_results: Sequence[AgentResultSnippet],
        known_facts: Sequence[KnownFactSnippet],
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        chat_id: Optional[UUID] = None,
        sandbox_overrides: Optional[dict] = None,
        llm_event_callback: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    ) -> List[FactDTO]:
        """Run the extractor. On any failure returns [] and logs a warning —
        memory extraction must never break a chat turn.
        """
        payload = {
            "user_message": (user_message or "").strip(),
            "agent_results": [r.model_dump() for r in agent_results],
            "known_facts": [k.model_dump() for k in known_facts],
        }

        try:
            result = await self._structured.invoke(
                role=SystemLLMRoleType.FACT_EXTRACTOR,
                payload=payload,
                schema=_LLMFactOutput,
                chat_id=chat_id,
                tenant_id=tenant_id,
                user_id=user_id,
                sandbox_overrides=sandbox_overrides,
                fallback_factory=lambda _raw: _LLMFactOutput(facts=[]),
            )
        except StructuredCallError as exc:
            logger.warning("FactExtractor structured call failed: %s", exc)
            return []
        except Exception as exc:  # noqa: BLE001 — extractor must never raise
            logger.warning("FactExtractor unexpected error: %s", exc)
            return []
        if llm_event_callback is not None:
            try:
                await llm_event_callback(
                    {
                        "role": SystemLLMRoleType.FACT_EXTRACTOR.value,
                        "model": result.model,
                        "messages": result.request_messages,
                        "params": result.request_params,
                        "response": result.raw_response,
                        "duration_ms": result.duration_ms,
                    }
                )
            except Exception:
                logger.debug("FactExtractor llm_event_callback failed", exc_info=True)

        role_extras: dict[str, Any] = {}
        try:
            role_config = await self._role_service.get_role_config(SystemLLMRoleType.FACT_EXTRACTOR)
            maybe_extras = role_config.get("extras")
            if isinstance(maybe_extras, dict):
                role_extras = maybe_extras
        except Exception:
            role_extras = {}
        policy = _resolve_fact_policy(role_extras, sandbox_overrides)
        return self._to_dtos(
            result.value,
            user_message=user_message,
            agent_summaries=[r.summary for r in agent_results],
            user_id=user_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
            max_facts_per_turn=policy["max_facts_per_turn"],
            max_subject_len=policy["max_subject_len"],
            max_value_len=policy["max_value_len"],
            confidence_min=policy["confidence_min"],
            max_value_words=policy["max_value_words"],
        )

    # --- mapping -----------------------------------------------------------

    @staticmethod
    def _to_dtos(
        out: _LLMFactOutput,
        *,
        user_message: str,
        agent_summaries: Sequence[str],
        user_id: Optional[UUID],
        tenant_id: Optional[UUID],
        chat_id: Optional[UUID],
        max_facts_per_turn: int = MAX_FACTS_PER_TURN,
        max_subject_len: int = MAX_SUBJECT_LEN,
        max_value_len: int = MAX_VALUE_LEN,
        confidence_min: float = CONFIDENCE_MIN,
        max_value_words: int = MAX_VALUE_WORDS,
    ) -> List[FactDTO]:
        """Validate + map LLM candidates to FactDTOs.

        * Drop unknown scopes.
        * Drop candidates missing scope-required owner id (e.g. a
          `scope=user` fact when we don't have a user_id for this turn
          would be nonsense to persist).
        * Clip too-long subjects/values.
        * Cap count at MAX_FACTS_PER_TURN.
        """
        out_list: List[FactDTO] = []
        for cand in out.facts[:max_facts_per_turn]:
            scope_raw = (cand.scope or "").strip().lower()
            try:
                scope = FactScope(scope_raw)
            except ValueError:
                logger.debug("FactExtractor: skip unknown scope %r", scope_raw)
                continue

            subject = (cand.subject or "").strip()[:max_subject_len]
            value = (cand.value or "").strip()[:max_value_len]
            if not subject or not value:
                continue

            if scope == FactScope.USER and user_id is None:
                continue
            if scope == FactScope.TENANT and tenant_id is None:
                continue
            if scope == FactScope.CHAT and chat_id is None:
                continue

            confidence = max(0.0, min(1.0, float(cand.confidence)))
            if confidence < confidence_min:
                continue
            subject = FactExtractor._normalize_subject(subject)
            if not subject:
                continue
            if FactExtractor._looks_ephemeral(subject, value, max_value_words=max_value_words):
                continue

            # Evidence validation: fact must be traceable to source text
            if not FactExtractor._has_evidence(subject, value, user_message, agent_summaries):
                logger.debug("FactExtractor: skip fact without evidence: %r=%r", subject, value)
                continue

            out_list.append(
                FactDTO(
                    scope=scope,
                    subject=subject,
                    value=value,
                    source=FactExtractor._infer_source(
                        subject=subject,
                        value=value,
                        user_message=user_message,
                        agent_summaries=agent_summaries,
                    ),
                    user_id=user_id if scope != FactScope.TENANT else None,
                    tenant_id=tenant_id,
                    chat_id=chat_id if scope == FactScope.CHAT else None,
                    confidence=confidence,
                )
            )
        return out_list

    @staticmethod
    def _normalize_subject(subject: str) -> str:
        normalized = " ".join((subject or "").strip().lower().split())
        if not normalized:
            return ""
        if normalized in {"имя", "name", "user name", "username", "имя пользователя"}:
            return "name"
        if normalized in {"email", "почта", "e-mail", "mail"}:
            return "email"
        if normalized in {"язык", "language", "lang"}:
            return "language"
        return normalized

    @staticmethod
    def _looks_ephemeral(subject: str, value: str, *, max_value_words: int = MAX_VALUE_WORDS) -> bool:
        stripped = (value or "").strip()
        if not stripped:
            return True
        if "\n" in stripped:
            return True
        if len(stripped.split()) > max_value_words:
            return True
        if re.search(r"^\d+$", stripped) and any(h in subject for h in _EPHEMERAL_COUNT_SUBJECT_HINTS):
            return True
        return False

    @staticmethod
    def _has_evidence(
        subject: str,
        value: str,
        user_message: str,
        agent_summaries: Sequence[str],
    ) -> bool:
        """Check if fact has evidence in source texts (anti-hallucination guard).
        
        Returns True if subject or value appears in user_message or agent_summaries.
        This prevents LLM from inventing facts that weren't in the conversation.
        """
        if not subject or not value:
            return False
        
        hay_user = (user_message or "").lower()
        hay_agents = "\n".join([s for s in (agent_summaries or []) if s]).lower()
        
        # Check for subject or value in source texts
        subj_lower = subject.lower()
        val_lower = value.lower()
        
        # Exact substring match (lenient) or word match
        if subj_lower in hay_user or val_lower in hay_user:
            return True
        if subj_lower in hay_agents or val_lower in hay_agents:
            return True
        
        # For multi-word values, check if any significant part matches
        val_words = val_lower.split()
        if len(val_words) > 1:
            # Check if majority of words appear in source
            user_matches = sum(1 for w in val_words if w in hay_user)
            agent_matches = sum(1 for w in val_words if w in hay_agents)
            if user_matches >= len(val_words) * 0.5 or agent_matches >= len(val_words) * 0.5:
                return True
        
        return False

    @staticmethod
    def _infer_source(
        *,
        subject: str,
        value: str,
        user_message: str,
        agent_summaries: Sequence[str],
    ) -> FactSource:
        hay_user = (user_message or "").lower()
        hay_agents = "\n".join([s for s in (agent_summaries or []) if s]).lower()
        needles = [subject.lower(), value.lower()]
        if any(n and n in hay_user for n in needles):
            return FactSource.USER_UTTERANCE
        if any(n and n in hay_agents for n in needles):
            return FactSource.AGENT_RESULT
        if hay_agents and not hay_user.strip():
            return FactSource.AGENT_RESULT
        return FactSource.USER_UTTERANCE


def _resolve_fact_policy(role_extras: Optional[dict], sandbox_overrides: Optional[dict]) -> dict[str, Any]:
    cfg = dict(
        max_facts_per_turn=MAX_FACTS_PER_TURN,
        max_subject_len=MAX_SUBJECT_LEN,
        max_value_len=MAX_VALUE_LEN,
        confidence_min=CONFIDENCE_MIN,
        max_value_words=MAX_VALUE_WORDS,
    )
    overrides = sandbox_overrides or {}
    memory = overrides.get("memory") if isinstance(overrides, dict) else None
    fact_cfg = overrides.get("fact_extractor") if isinstance(overrides, dict) else None
    for source in (role_extras, memory, fact_cfg):
        if not isinstance(source, dict):
            continue
        for key in ("max_facts_per_turn", "max_subject_len", "max_value_len", "max_value_words"):
            val = source.get(key)
            if isinstance(val, int) and val > 0:
                cfg[key] = val
        val = source.get("confidence_min")
        if isinstance(val, (int, float)):
            cfg["confidence_min"] = max(0.0, min(1.0, float(val)))
    return cfg
