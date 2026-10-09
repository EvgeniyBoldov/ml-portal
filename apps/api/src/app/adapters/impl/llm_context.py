"""Token allocation at the outbound LLM boundary, independent of actor budgets."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

import tiktoken

from app.adapters.interfaces.llm import LLMErrorCode, LLMProviderError

DEFAULT_CONTEXT_WINDOW = 16_384
INPUT_SAFETY_FACTOR = 1.10
MIN_OUTPUT_FRACTION = 0.10


@lru_cache(maxsize=16)
def _encoding(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class ContextAllocation:
    context_window: int
    estimated_input_tokens: int
    reserved_input_tokens: int
    minimum_output_tokens: int
    max_output_tokens: int


def allocate_context(request: Mapping[str, Any], context_window: int) -> ContextAllocation:
    """Count all textual input, including tool definitions and response schemas.

    JSON framing is included as a conservative approximation of chat templates.
    This is an estimate for non-OpenAI tokenizers; the connector handles an
    explicit provider correction without modifying or truncating the input.
    """
    input_payload = {key: request[key] for key in (
        "messages", "tools", "tool_choice", "functions", "function_call", "response_format",
    ) if key in request}
    serialized = json.dumps(input_payload, ensure_ascii=False, separators=(",", ":"))
    estimated = len(_encoding(str(request.get("model") or "")).encode(serialized, disallowed_special=()))
    reserved = math.ceil(estimated * INPUT_SAFETY_FACTOR)
    minimum = math.ceil(context_window * MIN_OUTPUT_FRACTION)
    available = context_window - reserved
    if available < minimum:
        raise context_exhausted()
    return ContextAllocation(context_window, estimated, reserved, minimum, available)


def context_exhausted() -> LLMProviderError:
    return LLMProviderError(
        code=LLMErrorCode.CONTEXT_WINDOW_EXCEEDED,
        safe_message="Не хватает контекстного окна модели для решения вопроса.",
        retryable=False,
    )
