from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.execution_limits_service import ExecutionLimitsPayload


class LLMLimitErrorCode:
    INPUT_EXCEEDED = "llm_input_limit_exceeded"
    OUTPUT_EXCEEDED = "llm_output_limit_exceeded"
    CONTEXT_WINDOW_EXCEEDED = "llm_context_window_exceeded"


class LLMLimitExceededError(RuntimeError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def estimate_tokens(text: str) -> int:
    raw = (text or "").strip()
    if not raw:
        return 0
    return max(1, len(raw) // 4)


@dataclass(frozen=True)
class LLMBoundary:
    input_tokens: int
    output_tokens: Optional[int]


def apply_llm_limits(
    *,
    limits: ExecutionLimitsPayload,
    input_tokens: int,
    requested_output_tokens: Optional[int],
) -> LLMBoundary:
    output_cap = requested_output_tokens
    if limits.llm_output_tokens_max is not None:
        if output_cap is None:
            output_cap = int(limits.llm_output_tokens_max)
        else:
            output_cap = min(int(output_cap), int(limits.llm_output_tokens_max))

    if limits.llm_input_tokens_max is not None and input_tokens > int(limits.llm_input_tokens_max):
        raise LLMLimitExceededError(
            code=LLMLimitErrorCode.INPUT_EXCEEDED,
            message=(
                f"LLM input token limit exceeded: used={input_tokens}, "
                f"limit={int(limits.llm_input_tokens_max)}"
            ),
        )

    if (
        limits.llm_context_window_max is not None
        and output_cap is not None
        and (input_tokens + int(output_cap)) > int(limits.llm_context_window_max)
    ):
        raise LLMLimitExceededError(
            code=LLMLimitErrorCode.CONTEXT_WINDOW_EXCEEDED,
            message=(
                f"LLM context window exceeded: used={input_tokens + int(output_cap)}, "
                f"limit={int(limits.llm_context_window_max)}"
            ),
        )

    if (
        limits.llm_output_tokens_max is not None
        and requested_output_tokens is not None
        and int(requested_output_tokens) > int(limits.llm_output_tokens_max)
    ):
        # Not fatal since we clamp, but expose explicit signal for debugging callsites.
        output_cap = int(limits.llm_output_tokens_max)

    return LLMBoundary(input_tokens=input_tokens, output_tokens=output_cap)
