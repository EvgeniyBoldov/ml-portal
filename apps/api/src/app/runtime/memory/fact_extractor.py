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

import math
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Literal, Optional, Sequence
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
from app.runtime.memory.fact_store import TENANT_AUTHOR_PREFIX
from app.runtime.memory.decisions import JOURNAL_CANDIDATE_IDS, MemoryDecision
from app.services.system_llm_role_service import SystemLLMRoleService

logger = get_logger(__name__)


# --- LLM contract -----------------------------------------------------------


class _LLMFactCandidate(BaseModel):
    """Shape the LLM is asked to produce per extracted fact."""
    scope: str
    subject: str
    value: str
    confidence: float = 1.0
    kind: Literal["fact"] = "fact"
    evidence_source_ids: List[str] = Field(min_length=1, description="Exact IDs of user-message evidence supporting the assertion.")
    evidence_quote: str = Field(min_length=1, description="Verbatim complete assertion, including who it is about.")


class _LLMFactOutput(BaseModel):
    facts: List[_LLMFactCandidate]


# --- Public domain input/output --------------------------------------------


class FactEvidence(BaseModel):
    """A primary source made available to extraction, never an agent summary."""
    source_id: str
    source_type: str  # user_message | tool_result
    source_ref: str
    text: str
    label: Optional[str] = None
    # Stable source identity used for confirmation.
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


@dataclass(frozen=True)
class FactExtractionResult:
    """Internal writeback result; ``extract`` keeps its legacy list API."""
    facts: list[FactDTO]
    decisions: list[MemoryDecision]
    error_code: str | None = None


# --- Extractor --------------------------------------------------------------


MAX_FACTS_PER_TURN = 12
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
        preflight_candidates: Sequence[dict[str, Any]] = (),
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
        return (await self.extract_with_decisions(
            user_message=user_message, evidence=evidence, known_facts=known_facts,
            preflight_candidates=preflight_candidates,
            agent_results=agent_results, user_id=user_id, tenant_id=tenant_id,
            chat_id=chat_id, sandbox_overrides=sandbox_overrides,
            llm_event_sink=llm_event_sink, agent_execution_id=agent_execution_id,
        )).facts

    async def extract_with_decisions(
        self,
        *,
        user_message: str,
        evidence: Sequence[FactEvidence] = (),
        known_facts: Sequence[KnownFactSnippet] = (),
        preflight_candidates: Sequence[dict[str, Any]] = (),
        agent_results: Sequence[AgentResultSnippet] = (),
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        chat_id: Optional[UUID] = None,
        sandbox_overrides: Optional[dict] = None,
        llm_event_sink: Optional[Callable[[RuntimeEvent], Awaitable[None]]] = None,
        agent_execution_id: Optional[str] = None,
    ) -> FactExtractionResult:
        # Compatibility argument ``agent_results`` is deliberately ignored:
        # summaries can never become fact evidence.
        effective_evidence = [item for item in evidence if item.source_type == "user_message"] or ([FactEvidence(
            source_id="user_message", source_type="user_message", source_ref=str(chat_id or "request"), text=user_message,
        )] if user_message.strip() else [])
        payload = {
            # ``evidence`` contains the canonical source text. Do not also
            # send it as ``user_message``: for ordinary turns they are the
            # same document, and duplicating a long paste both wastes context
            # and makes the structured call more likely to be rate-limited.
            "evidence": [item.model_dump() for item in effective_evidence],
            "known_facts": [k.model_dump() for k in known_facts],
            # Hints only: the extractor must still cite and re-validate the
            # primary evidence for every resulting candidate below.
            "preflight_candidates": list(preflight_candidates),
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
            )
        except StructuredCallError as exc:
            logger.warning("FactExtractor structured call failed: %s", exc)
            return FactExtractionResult([], [], "extractor_call_failed")
        except Exception as exc:  # noqa: BLE001 — extractor must never raise
            logger.warning("FactExtractor unexpected error: %s", exc)
            return FactExtractionResult([], [], "extractor_unexpected_error")
        role_extras: dict[str, Any] = {}
        try:
            role_config = await self._role_service.get_role_config(SystemLLMRoleType.FACT_EXTRACTOR)
            maybe_extras = role_config.get("extras")
            if isinstance(maybe_extras, dict):
                role_extras = maybe_extras
        except Exception:
            role_extras = {}
        policy = _resolve_fact_policy(role_extras, sandbox_overrides)
        return self._to_dtos_with_decisions(
            result.value,
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
    def _to_dtos_with_decisions(
        out: _LLMFactOutput,
        *,
        evidence: Sequence[FactEvidence],
        user_id: Optional[UUID],
        tenant_id: Optional[UUID],
        chat_id: Optional[UUID],
        max_facts_per_turn: int = MAX_FACTS_PER_TURN,
        max_subject_len: int = MAX_SUBJECT_LEN,
        max_value_len: int = MAX_VALUE_LEN,
        confidence_min: float = CONFIDENCE_MIN,
        max_value_words: int = MAX_VALUE_WORDS,
    ) -> FactExtractionResult:
        out_list: List[FactDTO] = []
        decisions: list[MemoryDecision] = []
        for index, cand in enumerate(out.facts):
            candidate_id = f"extractor:{index + 1}"
            if index >= max_facts_per_turn:
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "limit_exceeded"))
                continue
            scope_raw = (cand.scope or "").strip().lower()
            try:
                scope = FactScope(scope_raw)
            except ValueError:
                logger.debug("FactExtractor: skip unknown scope %r", scope_raw)
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "unknown_scope"))
                continue

            subject = cand.subject.strip()
            value = cand.value.strip()
            if not subject or not value:
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "empty_content"))
                continue

            if len(subject) > max_subject_len or len(value) > max_value_len:
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "content_too_long"))
                continue

            if scope == FactScope.USER and user_id is None:
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "missing_owner"))
                continue
            if scope == FactScope.TENANT and (tenant_id is None or user_id is None):
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "missing_owner"))
                continue
            kind = (cand.kind or "fact").strip().lower()
            if kind != "fact":
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "unsupported_kind"))
                continue
            confidence = max(0.0, min(1.0, float(cand.confidence)))
            if not math.isfinite(cand.confidence) or confidence < confidence_min:
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "below_confidence"))
                continue
            subject = FactExtractor._normalize_subject(subject)
            if not subject:
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "invalid_subject"))
                continue
            if FactExtractor._looks_ephemeral(subject, value, max_value_words=max_value_words):
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "ephemeral_value"))
                continue

            matched_evidence = FactExtractor._matching_evidence(
                candidate=cand,
                subject=subject,
                value=value,
                scope=scope,
                evidence=evidence,
            )
            if not matched_evidence:
                logger.debug("FactExtractor: skip fact without evidence: %r=%r", subject, value)
                decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "rejected", "evidence_not_matched"))
                continue
            fact = FactDTO(
                    scope=scope,
                    subject=subject,
                    value=value,
                    source=FactSource.USER_UTTERANCE,
                    tenant_id=tenant_id,
                    kind=kind,
                    confidence=confidence,
                    metadata={
                        "evidence": [
                            item.model_dump() | {"text": cand.evidence_quote,
                                **({"support_ref": f"{TENANT_AUTHOR_PREFIX}{user_id}"} if scope == FactScope.TENANT and user_id else {})}
                            for item in matched_evidence
                        ],
                        JOURNAL_CANDIDATE_IDS: [candidate_id],
                    },
                )
            out_list.append(fact)
            decisions.append(MemoryDecision("fact_extractor", "extraction_validation", "accepted", "evidence_validated", (fact,)))
        return FactExtractionResult(out_list, decisions)

    @staticmethod
    def _normalize_subject(subject: str) -> str:
        normalized = " ".join((subject or "").strip().lower().split())
        if not normalized:
            return ""
        if normalized in {"имя", "name", "user name", "имя пользователя", "user.name"}:
            return "name"
        if normalized in {"jira username", "jira account", "jira login", "user.jira.username"}:
            return "user.jira.username"
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
        scope: FactScope,
        evidence: Sequence[FactEvidence],
    ) -> List[FactEvidence]:
        ids = candidate.evidence_source_ids
        sources = {item.source_id: item for item in evidence if item.source_type == "user_message"}
        if not ids or any(ref not in sources for ref in ids):
            return []
        quote = candidate.evidence_quote.strip()
        if not re.search(rf"(?<!\w){re.escape(value)}(?!\w)", quote, re.IGNORECASE):
            return []
        for ref in ids:
            # Inspect the containing sentence as well as the proposed quote.
            # A shortened quote must not hide a question, negation or attribution.
            sentences = re.split(r"(?<=[.!?])\s+|\n", _QUOTED_MATERIAL.sub(" ", sources[ref].text))
            if not any(quote in sentence and _asserts_owned_value(quote, sentence, subject, value, scope)
                       for sentence in sentences):
                return []
        return [sources[ref] for ref in dict.fromkeys(ids)]


_TENANT_MARKER = (
    r"(?:our (?:company|department|organization)|в наше[йм] (?:компании|отделе|организации)"
    r"|у нас в (?:компании|отделе|организации)|наш[а-яё]* (?:компани[яи]|отдел|организаци[яи]))"
)
_QUOTED_MATERIAL = re.compile(
    r'(?m)^[ \t]*>[^\n]*|```[\s\S]*?(?:```|\Z)|«[^»]*»|“[^”]*”|"[^"]*"'
    r"|(?<!\w)'[^']*'(?!\w)",
)
_NON_ASSERTION = re.compile(
    r'[?«»“”`]|(?:^|\s)[>"]|\b(?:не|нет|якобы|если|например|допустим|'
    r'not|never|if|suppose|example)\b',
    re.IGNORECASE,
)
_USER_PREDICATES = {
    "name": r"(?:my name is|меня (?:теперь )?зовут|мо[её] имя\s*[:—-])",
    "user.jira.username": (
        r"(?:my (?:jira (?:username|login|account)|(?:username|login|account) in jira)\s+(?:is\s+)?"
        r"|мой (?:логин|аккаунт) в jira\s*[:—-]?)"
    ),
    "role": r"(?:i am (?:an? )?|я(?: работаю)?\s*[:—-]?)",
    "stack": r"(?:i (?:use|work with)|я (?:использую|работаю с))",
    "department": r"(?:my department is|i work in(?: the)?|мой отдел\s*[:—-]|я работаю в отделе)",
    "отдел": r"(?:мой отдел\s*[:—-]|я работаю в отделе)",
    "email": r"(?:my (?:email|e-mail) is|моя почта\s*[:—-]|мой email\s*[:—-])",
    "language": r"(?:i speak|я говорю на)",
}
_FIELD_SEPARATOR = r"\s*(?:[:=—-]|\bis\b)\s*"


def _asserts_owned_value(quote: str, sentence: str, subject: str, value: str, scope: FactScope) -> bool:
    if _NON_ASSERTION.search(sentence):
        return False
    field = subject.removeprefix("user.").removeprefix("tenant.")
    label = "|".join(dict.fromkeys((re.escape(field), re.escape(field.replace("_", " ").replace(".", " ")))))
    if scope == FactScope.TENANT:
        predicate = rf"{_TENANT_MARKER}\s+(?:{label}){_FIELD_SEPARATOR}"
    else:
        explicit = rf"(?:my|мой|моя|мо[её]|мои|у меня)\s+(?:{label}){_FIELD_SEPARATOR}"
        natural = _USER_PREDICATES.get(subject, _USER_PREDICATES.get(field))
        predicate = rf"(?:{explicit}|{natural}\s+)" if natural else explicit
    if subject == "user.jira.username":
        ending = r"(?![\w-]|\.[\w.-])"
    else:
        ending = r"(?![\w-])"
    transition = r"(?:(?:теперь|now)\s+)?"
    return bool(re.search(rf"\b{predicate}{transition}{re.escape(value)}{ending}", quote, re.IGNORECASE))


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
