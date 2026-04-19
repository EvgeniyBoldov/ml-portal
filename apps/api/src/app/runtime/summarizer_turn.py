"""
TurnSummarizer — generate a compact dialogue summary at the end of each turn.

Runs as the last stage of `RuntimePipeline._finalize`. It:
  * Fetches the SUMMARY role configuration from the `system_llm_roles` table
    (prompt lives in the DB, not in code).
  * Calls the LLM with the previous summary + user message + assistant final
    answer + a short tail of recent messages.
  * Writes the new summary into two places:
        1. `execution_memories.dialogue_summary` (v3 working memory)
        2. `chat_summaries` (legacy, still consumed by
           `ChatContextService.load_chat_context_with_summary`)

Design notes:
  * Text output (no JSON schema), so we call the LLM client directly instead
    of going through `StructuredLLMCall`.
  * Failures never abort the turn — the pipeline has already emitted FINAL.
    We log and swallow so the user-facing stream is not disturbed.
  * For sandbox runs (chat_id is None) we only update the in-memory snapshot
    — there is no chat to bind a summary to.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.memory.working_memory import WorkingMemory
from app.services.chat_summary_service import ChatSummaryService
from app.services.system_llm_role_service import SystemLLMRoleService

logger = get_logger(__name__)


_DEFAULT_TIMEOUT_S = 20
_MAX_SUMMARY_CHARS = 2000


class TurnSummarizer:
    """Produces and persists a rolling dialogue summary after each turn."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.role_service = SystemLLMRoleService(session)
        self.summary_service = ChatSummaryService(session)

    async def run(
        self,
        *,
        memory: WorkingMemory,
        user_message: str,
        assistant_answer: str,
        recent_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """Generate a new summary and persist it. Returns the new summary text
        or None on failure."""
        try:
            role_config = await self.role_service.get_role_config(SystemLLMRoleType.SUMMARY)
        except Exception as exc:
            logger.warning("TurnSummarizer: SUMMARY role not configured: %s", exc)
            return None

        payload = {
            "previous_summary": memory.dialogue_summary or "",
            "current_user_message": user_message,
            "current_agent_response": assistant_answer,
            "recent_messages": (recent_messages or [])[-12:],
            "session_state": {
                "chat_id": str(memory.chat_id) if memory.chat_id else None,
                "run_id": str(memory.run_id),
                "goal": memory.goal,
            },
        }

        system_prompt = role_config.get("prompt") or ""
        model = role_config.get("model")
        timeout_s = int(role_config.get("timeout_s") or _DEFAULT_TIMEOUT_S)
        temperature = role_config.get("temperature")
        max_tokens = role_config.get("max_tokens") or 600

        params: Dict[str, Any] = {"max_tokens": max_tokens}
        if temperature is not None:
            params["temperature"] = temperature

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]

        try:
            response = await asyncio.wait_for(
                self.llm_client.chat(messages, model=model, params=params),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning("TurnSummarizer timeout after %ss", timeout_s)
            return None
        except Exception as exc:
            logger.warning("TurnSummarizer LLM call failed: %s", exc)
            return None

        new_summary = self._extract_text(response).strip()
        if not new_summary:
            logger.info("TurnSummarizer: empty summary returned, keeping previous")
            return None

        new_summary = new_summary[:_MAX_SUMMARY_CHARS]
        memory.dialogue_summary = new_summary

        # Persist to chat_summaries for legacy readers (ChatContextService).
        if memory.chat_id is not None:
            try:
                await self.summary_service.create_or_update_summary(
                    chat_id=memory.chat_id,
                    summary_text=new_summary,
                    message_count=len(memory.recent_messages) + 2,  # +user +assistant
                    last_message_id=None,
                    tenant_id=memory.tenant_id,
                    summary_metadata={
                        "run_id": str(memory.run_id),
                        "goal": memory.goal,
                    },
                )
            except Exception as exc:
                logger.warning("TurnSummarizer: failed to persist chat summary: %s", exc)

        return new_summary

    # --------------------------------------------------------------------- helpers --

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Best-effort extract plain text from common LLM response shapes."""
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            # OpenAI-compatible shape.
            choices = response.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content")
                if isinstance(content, str):
                    return content
            content = response.get("content")
            if isinstance(content, str):
                return content
            text = response.get("text")
            if isinstance(text, str):
                return text
        return str(response)
