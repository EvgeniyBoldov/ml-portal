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

from typing import List, Optional, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.memory import FactScope, FactSource
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.runtime.memory.dto import FactDTO

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


class FactExtractor:
    """Extracts stable, atomic facts from a finished turn."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
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
    ) -> List[FactDTO]:
        """Run the extractor. On any failure returns [] and logs a warning —
        memory extraction must never break a chat turn.
        """
        payload = {
            "user_message": user_message,
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
                fallback_factory=lambda _raw: _LLMFactOutput(facts=[]),
            )
        except StructuredCallError as exc:
            logger.warning("FactExtractor structured call failed: %s", exc)
            return []
        except Exception as exc:  # noqa: BLE001 — extractor must never raise
            logger.warning("FactExtractor unexpected error: %s", exc)
            return []

        return self._to_dtos(
            result.value,
            user_id=user_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
        )

    # --- mapping -----------------------------------------------------------

    @staticmethod
    def _to_dtos(
        out: _LLMFactOutput,
        *,
        user_id: Optional[UUID],
        tenant_id: Optional[UUID],
        chat_id: Optional[UUID],
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
        for cand in out.facts[:MAX_FACTS_PER_TURN]:
            scope_raw = (cand.scope or "").strip().lower()
            try:
                scope = FactScope(scope_raw)
            except ValueError:
                logger.debug("FactExtractor: skip unknown scope %r", scope_raw)
                continue

            subject = (cand.subject or "").strip()[:MAX_SUBJECT_LEN]
            value = (cand.value or "").strip()[:MAX_VALUE_LEN]
            if not subject or not value:
                continue

            if scope == FactScope.USER and user_id is None:
                continue
            if scope == FactScope.TENANT and tenant_id is None:
                continue
            if scope == FactScope.CHAT and chat_id is None:
                continue

            confidence = max(0.0, min(1.0, float(cand.confidence)))

            out_list.append(
                FactDTO(
                    scope=scope,
                    subject=subject,
                    value=value,
                    source=FactSource.USER_UTTERANCE,
                    user_id=user_id if scope != FactScope.TENANT else None,
                    tenant_id=tenant_id,
                    chat_id=chat_id if scope == FactScope.CHAT else None,
                    confidence=confidence,
                )
            )
        return out_list
