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
from app.runtime.events import RuntimeEvent
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
    kind: str = "fact"  # fact | glossary
    project_key: Optional[str] = None
    project_aliases: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    evidence_source_ids: List[str] = Field(default_factory=list)


class _LLMFactOutput(BaseModel):
    facts: List[_LLMFactCandidate] = Field(default_factory=list)


# --- Public domain input/output --------------------------------------------


class FactEvidence(BaseModel):
    """A primary source made available to extraction, never an agent summary."""
    source_id: str
    source_type: str  # user_message | tool_result
    source_ref: str
    text: str
    label: Optional[str] = None
    # Stable source identity used for confirmation.  A runtime tool-call ID is
    # suitable for provenance, but repeated retrieval of the same document
    # must not count as independent glossary support.
    support_ref: Optional[str] = None


class AgentResultSnippet(BaseModel):
    """Runtime result transport; deliberately not accepted as fact evidence."""
    agent: str
    summary: str
    success: bool = True
    artifacts: List[dict[str, Any]] = Field(default_factory=list)


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
        evidence: Sequence[FactEvidence] = (),
        known_facts: Sequence[KnownFactSnippet] = (),
        agent_results: Sequence[AgentResultSnippet] = (),
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        chat_id: Optional[UUID] = None,
        sandbox_overrides: Optional[dict] = None,
        llm_event_sink: Optional[Callable[[RuntimeEvent], Awaitable[None]]] = None,
        agent_execution_id: Optional[str] = None,
    ) -> List[FactDTO]:
        """Run the extractor. On any failure returns [] and logs a warning —
        memory extraction must never break a chat turn.
        """
        # Compatibility argument ``agent_results`` is deliberately ignored:
        # summaries can never become fact evidence.
        effective_evidence = list(evidence) or ([FactEvidence(
            source_id="user_message", source_type="user_message", source_ref=str(chat_id or "request"), text=user_message,
        )] if user_message.strip() else [])
        payload = {
            "user_message": (user_message or "").strip(),
            "evidence": [item.model_dump() for item in effective_evidence],
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
                event_sink=llm_event_sink,
                agent_execution_id=agent_execution_id,
                fallback_factory=lambda _raw: _LLMFactOutput(facts=[]),
            )
        except StructuredCallError as exc:
            logger.warning("FactExtractor structured call failed: %s", exc)
            return []
        except Exception as exc:  # noqa: BLE001 — extractor must never raise
            logger.warning("FactExtractor unexpected error: %s", exc)
            return []
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
            evidence=effective_evidence,
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
        evidence: Sequence[FactEvidence],
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
            kind = (cand.kind or "fact").strip().lower()
            if kind not in {"fact", "glossary"}:
                continue
            if kind == "glossary" and scope not in {FactScope.USER, FactScope.TENANT}:
                continue
            confidence = max(0.0, min(1.0, float(cand.confidence)))
            if confidence < confidence_min:
                continue
            subject = FactExtractor._normalize_subject(subject)
            if not subject:
                continue
            if FactExtractor._looks_ephemeral(subject, value, max_value_words=max_value_words):
                continue

            matched_evidence = FactExtractor._matching_evidence(
                candidate=cand,
                subject=subject,
                value=value,
                user_message=user_message,
                evidence=evidence,
            )
            if not matched_evidence:
                logger.debug("FactExtractor: skip fact without evidence: %r=%r", subject, value)
                continue
            if scope == FactScope.USER and not any(item.source_type == "user_message" for item in matched_evidence):
                continue
            # Project knowledge is accepted only from explicit in-run markers;
            # this extractor owns user/tenant facts and terminology.
            if scope == FactScope.PROJECT:
                continue

            glossary_scope = None
            if kind == "glossary" and _has_grounded_glossary_evidence(matched_evidence):
                glossary_scope = "global"

            out_list.append(
                FactDTO(
                    scope=scope,
                    subject=subject,
                    value=value,
                    source=(FactSource.USER_UTTERANCE if matched_evidence[0].source_type == "user_message" else FactSource.TOOL_RESULT),
                    tenant_id=tenant_id,
                    kind=kind,
                    confidence=confidence,
                    metadata={
                        "project_key": (cand.project_key or "").strip().lower() or None,
                        "project_aliases": _normalize_project_aliases(cand.project_aliases),
                        "aliases": _normalize_project_aliases(cand.aliases),
                        "evidence": [item.model_dump() for item in matched_evidence],
                        "glossary_scope": glossary_scope,
                    },
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
    def _matching_evidence(
        *,
        candidate: _LLMFactCandidate,
        subject: str,
        value: str,
        user_message: str,
        evidence: Sequence[FactEvidence],
    ) -> List[FactEvidence]:
        requested = {item.strip() for item in candidate.evidence_source_ids if item.strip()}
        pool = [item for item in evidence if not requested or item.source_id in requested]
        value_words = [word for word in value.lower().split() if len(word) > 2]
        matched: List[FactEvidence] = []
        for item in pool:
            haystack = item.text.lower()
            if value.lower() in haystack or subject.lower() in haystack:
                matched.append(item)
                continue
            if value_words and sum(word in haystack for word in value_words) >= max(1, len(value_words) // 2):
                matched.append(item)
        if matched:
            return matched
        if user_message and (value.lower() in user_message.lower() or subject.lower() in user_message.lower()):
            return [item for item in evidence if item.source_type == "user_message"][:1]
        return []


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


def _normalize_project_aliases(raw: Sequence[str]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in raw[:8]:
        alias = " ".join(str(value or "").strip().split())[:120]
        key = alias.casefold()
        if not alias or key in seen:
            continue
        seen.add(key)
        aliases.append(alias)
    return aliases


def _has_grounded_glossary_evidence(evidence: Sequence[FactEvidence]) -> bool:
    """Whether a candidate comes from a verified knowledge retrieval result."""
    return any(
        item.source_type == "tool_result"
        and str(item.label or "").strip() in {
            "collection.document.search",
            "collection.table.search",
        }
        and bool(str(item.support_ref or item.source_ref or "").strip())
        for item in evidence
    )
