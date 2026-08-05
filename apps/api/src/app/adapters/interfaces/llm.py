"""Provider-neutral LLM transport contracts and safe failure taxonomy."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, AsyncIterator, Mapping, Optional, Protocol


class LLMErrorCode(StrEnum):
    TIMEOUT = "llm_timeout"
    CANCELLED = "llm_cancelled"
    CONNECTION = "llm_connection_error"
    AUTHENTICATION = "llm_authentication_error"
    AUTHORIZATION = "llm_authorization_error"
    MODEL_NOT_FOUND = "llm_model_not_found"
    RATE_LIMITED = "llm_rate_limited"
    REQUEST_TOO_LARGE = "llm_request_too_large"
    INVALID_REQUEST = "llm_invalid_request"
    UPSTREAM = "llm_upstream_error"
    TOOL_CALLING_UNSUPPORTED = "llm_tool_calling_unsupported"
    STRUCTURED_OUTPUT_UNSUPPORTED = "llm_structured_output_unsupported"
    UNKNOWN = "llm_unknown_error"


@dataclass(frozen=True)
class LLMProviderError(RuntimeError):
    """Normalized, safe provider failure returned by the adapter boundary."""

    code: LLMErrorCode
    safe_message: str
    retryable: bool
    status_code: Optional[int] = None
    provider_type: Optional[str] = None
    provider_code: Optional[str] = None
    retry_after_ms: Optional[int] = None

    def __str__(self) -> str:
        return self.safe_message


@dataclass(frozen=True)
class LLMCallOptions:
    """Transport-only options, kept separate from provider request params."""

    timeout_s: Optional[float] = None


@dataclass(frozen=True)
class ResolvedLLMConnection:
    """Resolved registry/credential state consumed by a provider adapter."""

    model_alias: str
    provider_model_name: str
    base_url: str
    connector: Optional[str]
    api_key: Optional[str]
    extra_config: dict[str, Any]


class LLMConnectionResolver(Protocol):
    async def resolve(self, model_selector: Optional[str]) -> ResolvedLLMConnection: ...


class LLMClient(Protocol):
    async def chat(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> dict: ...

    async def chat_stream(
        self,
        messages: list[Mapping[str, str]],
        *,
        model: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> AsyncIterator[str]: ...
