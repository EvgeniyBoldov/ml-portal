"""
Planner — mini-LLM wrapper that returns strict NextAction JSON.

Responsibilities:
- Build compact prompt from RunContextCompact + AvailableActions
- Call LLM and parse response as NextAction
- Validate action ∈ AvailableActions
- Retry once on invalid output, then fallback to ask_user
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import ValidationError

from app.agents.contracts import (
    ActionType,
    AskUserPayload,
    AvailableActions,
    NextAction,
)
from app.agents.json_utils import extract_json_from_text
from app.agents.run_context_compact import RunContextCompact
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 1
MAX_CHAT_HISTORY_MESSAGES = 20

PLANNER_SYSTEM_PROMPT = """You are a planning agent. Your job is to decide the SINGLE next action.

RULES:
- Return ONLY valid JSON matching the NextAction schema below.
- Choose ONLY from the available_operations list provided in the input.
- Do NOT invent operation_slug or op values.
- If the user's goal can be answered directly WITHOUT tools (greetings, simple questions, conversation), use "final" immediately with a helpful answer.
- Use "operation_call" ONLY when you need external data or must perform an action.
- Use "ask_user" ONLY when the request is genuinely ambiguous and you cannot proceed.
- IMPORTANT: If you can make a reasonable assumption and still provide a helpful answer, DO NOT ask the user. Prefer "final".
- IMPORTANT: If the user asks a general question or a question about the conversation itself, answer with "final".
- IMPORTANT: If you choose "ask_user", the question MUST be in the user's language.
- If the latest user messages contain Cyrillic, ask in Russian.
- Otherwise ask in English.
- If all needed facts are already in the context, use "final".
- Never return multiple actions. One action per response.

NextAction schema:
{
  "type": "operation_call" | "ask_user" | "final",
  "operation": {"intent": {"operation_slug": "...", "op": "..."}, "input": {...}},
  "ask_user": {"question": "..."},
  "final": {"answer": "..."},
  "meta": {"why": "short reason"}
}

- For "operation_call": fill "operation" field only.
- For "ask_user": fill "ask_user" field only.
- For "final": fill "final" field only. The answer should be a complete, helpful response in the user's language.
- "meta.why" is optional but helpful for debugging.

Return ONLY the JSON object. No markdown, no explanation, no extra text."""


def _build_planner_messages(
    context: RunContextCompact,
    available_actions: AvailableActions,
    chat_history: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Build messages array for planner LLM call."""
    planner_input = context.to_planner_input(available_actions)
    if chat_history:
        planner_input["chat_history"] = chat_history[-MAX_CHAT_HISTORY_MESSAGES:]
    
    # Log the planner input for debugging
    logger.debug(f"Planner input goal: {planner_input.get('goal', 'N/A')}")
    logger.debug(f"Planner input facts count: {len(planner_input.get('facts', []))}")
    logger.debug(f"Planner input chat_history count: {len(planner_input.get('chat_history', []))}")
    
    user_content = json.dumps(planner_input, ensure_ascii=False, indent=2)

    return [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _build_retry_messages(
    original_messages: List[Dict[str, Any]],
    error_text: str,
) -> List[Dict[str, Any]]:
    """Append error feedback for retry attempt."""
    return original_messages + [
        {
            "role": "user",
            "content": (
                f"Your previous response was invalid: {error_text}\n"
                "Please return a valid NextAction JSON. "
                "Choose ONLY from the available_operations list."
            ),
        }
    ]


def _extract_json(text: str) -> Optional[str]:
    """Extract first JSON object from text (handles markdown fences)."""
    return extract_json_from_text(text)


def _build_whitelist(available_actions: AvailableActions) -> Set[Tuple[str, str]]:
    """Build set of (operation_slug, op) for fast membership check."""
    return {(t.operation_slug, t.op) for t in available_actions.operations}


def validate_next_action(
    action: NextAction,
    available_actions: AvailableActions,
) -> Optional[str]:
    """Validate NextAction against whitelist. Returns error string or None."""
    if action.type == ActionType.OPERATION_CALL:
        if not action.operation:
            return "type=operation_call but 'operation' field is missing"
        whitelist = _build_whitelist(available_actions)
        key = (action.operation.intent.operation_slug, action.operation.intent.op)
        if key not in whitelist:
            allowed = ", ".join(f"{s}.{o}" for s, o in sorted(whitelist))
            return (
                f"operation '{key[0]}.{key[1]}' is not in available actions. "
                f"Allowed: [{allowed}]"
            )
    elif action.type == ActionType.AGENT_CALL:
        if not action.agent:
            return "type=agent_call but 'agent' field is missing"
        agent_slugs = {a.agent_slug for a in available_actions.agents}
        if action.agent.agent_slug not in agent_slugs:
            allowed = ", ".join(sorted(agent_slugs))
            return (
                f"agent '{action.agent.agent_slug}' is not in available agents. "
                f"Allowed: [{allowed}]"
            )
    elif action.type == ActionType.ASK_USER:
        if not action.ask_user:
            return "type=ask_user but 'ask_user' field is missing"
    elif action.type == ActionType.FINAL:
        if not action.final:
            return "type=final but 'final' field is missing"
    return None


def _fallback_ask_user() -> NextAction:
    """Safe fallback when planner fails to produce valid output."""
    return NextAction(
        type=ActionType.ASK_USER,
        ask_user=AskUserPayload(
            question="Я не смог определить следующий шаг. Уточните, пожалуйста, что именно вам нужно?"
        ),
    )


class Planner:
    """Mini-LLM planner that produces strict NextAction JSON.

    DEPRECATED: This class is no longer used by the production runtime.
    The active planner is `app.runtime.planner.planner.Planner` which loads
    its system prompt from the DB (SystemLLMRoleType.PLANNER) and supports
    structured output + retry. Do not instantiate this class for new code.

    `validate_next_action` below is still actively used by policy_engine.
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        planner_model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> None:
        self.llm_client = llm_client
        self.planner_model = planner_model
        self.temperature = temperature

    async def plan(
        self,
        context: RunContextCompact,
        available_actions: AvailableActions,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> NextAction:
        """
        Plan next action using LLM.
        
        On invalid output: retry once with error feedback.
        On second failure: return fallback ask_user.
        """
        # Log available actions for debugging
        logger.info(f"Planner plan called with {len(available_actions.operations)} operations available")
        if available_actions.operations:
            operation_list = ", ".join(
                f"{t.operation_slug}.{t.op}" for t in available_actions.operations[:5]
            )
            logger.info(f"Available operations (first 5): {operation_list}")
        
        messages = _build_planner_messages(context, available_actions, chat_history)
        logger.debug(f"Planner messages built: {len(messages)} messages")

        for attempt in range(1 + MAX_RETRIES):
            logger.debug(f"Planner attempt {attempt + 1}/{MAX_RETRIES + 1}")
            raw_response = await self._call_llm(messages, model=self.planner_model, temperature=self.temperature)
            logger.debug(f"Planner raw response: {raw_response[:200]}...")

            action, error = self._parse_and_validate(raw_response, available_actions)
            if action is not None:
                logger.info(
                    f"Planner produced action: type={action.type.value}, "
                    f"attempt={attempt + 1}"
                )
                return action

            logger.warning(
                f"Planner output invalid (attempt {attempt + 1}): {error}"
            )

            if attempt < MAX_RETRIES:
                messages = _build_retry_messages(messages, error or "unknown error")

        logger.error("Planner failed after retries, using fallback ask_user")
        return _fallback_ask_user()

    async def _call_llm(self, messages: List[Dict[str, Any]], model: Optional[str] = None, temperature: float = 0.3) -> str:
        """Call LLM via provider-agnostic client."""
        logger.debug(f"Planner LLM call with {len(messages)} messages, model={model}")
        try:
            response = await self.llm_client.chat(
                messages=messages,
                model=model,
                params={"temperature": temperature}
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Planner LLM call failed: {e}")
            return ""

    def _parse_and_validate(
        self,
        raw: str,
        available_actions: AvailableActions,
    ) -> Tuple[Optional[NextAction], Optional[str]]:
        """Parse raw LLM output into NextAction. Returns (action, error)."""
        if not raw.strip():
            return None, "empty response"

        json_str = _extract_json(raw)
        if not json_str:
            return None, f"no JSON found in response: {raw[:200]}"

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return None, f"invalid JSON: {e}"

        try:
            action = NextAction.model_validate(data)
        except ValidationError as e:
            return None, f"schema validation failed: {e}"

        whitelist_error = validate_next_action(action, available_actions)
        if whitelist_error:
            return None, whitelist_error

        return action, None
