"""
Universal LLM client for OpenAI-compatible APIs
Supports: OpenAI, Groq, Azure OpenAI, LocalAI, vLLM, Ollama, etc.
"""
from __future__ import annotations
import asyncio
import hashlib
import time
from typing import Any, AsyncIterator, Mapping, Optional
import httpx
from app.core.logging import get_logger
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.core.http.tls import outbound_http_verify
from app.services.model_connector_profiles import build_model_auth_headers
from app.adapters.interfaces.llm import LLMCallOptions, LLMConnectionResolver, LLMErrorCode, LLMProviderError
from app.services.llm_connection_resolver import RegistryLLMConnectionResolver

logger = get_logger(__name__)


class ProfiledAsyncOpenAI(AsyncOpenAI):
    def __init__(self, *args: Any, auth_headers_override: Optional[dict[str, str]] = None, **kwargs: Any) -> None:
        self._auth_headers_override = auth_headers_override or {}
        super().__init__(*args, **kwargs)

    @property
    def auth_headers(self) -> dict[str, str]:
        if self._auth_headers_override:
            return dict(self._auth_headers_override)
        return super().auth_headers


class OpenAICompatibleLLM:
    """
    Universal LLM client for any OpenAI-compatible API.
    
    Supports providers:
    - OpenAI
    - Groq
    - Azure OpenAI
    - LocalAI
    - vLLM
    - Ollama (with OpenAI compatibility mode)
    - Any other OpenAI-compatible service
    """
    
    def __init__(self, *, connection_resolver: Optional[LLMConnectionResolver] = None):
        self.settings = get_settings()
        self._connection_resolver = connection_resolver or RegistryLLMConnectionResolver()
        self._client_cache: dict[tuple[str, str], AsyncOpenAI] = {}
        self.client: Optional[AsyncOpenAI] = None
        self.provider = "connector"
        logger.info("Initialized LLM client via connector chain")

    def _get_or_create_client(
        self,
        *,
        base_url: str,
        api_key: Optional[str],
        connector: Optional[str],
        extra_config: Optional[dict[str, Any]],
    ) -> AsyncOpenAI:
        default_headers = build_model_auth_headers(connector, api_key, extra_config=extra_config)
        secret_fingerprint = hashlib.sha256(
            "\n".join(f"{key}:{value}" for key, value in sorted(default_headers.items())).encode()
        ).hexdigest()
        cache_key = (base_url.rstrip("/"), secret_fingerprint)
        client = self._client_cache.get(cache_key)
        if client is not None:
            return client

        auth_headers_override = default_headers or None
        openai_api_key = api_key
        if default_headers and "Authorization" not in default_headers:
            openai_api_key = None

        client_timeout_s = self.settings.LLM_TIMEOUT or 30.0
        # Per-call limits are passed to ``create(timeout=...)`` below.  The
        # cached client only needs a safe transport default. Semantic retries
        # belong to the runtime; SDK retries would hide attempts from budgets
        # and the sandbox journal.
        client = ProfiledAsyncOpenAI(
            base_url=base_url,
            api_key=openai_api_key,
            timeout=client_timeout_s,
            http_client=httpx.AsyncClient(
                timeout=client_timeout_s,
                verify=outbound_http_verify(),
            ),
            default_headers=None,
            auth_headers_override=auth_headers_override,
            _enforce_credentials=False,
            max_retries=0,
        )
        logger.info(
            "OpenAI-compatible LLM client created connector=%s timeout_s=%s "
            "sdk_max_retries=0",
            connector,
            client_timeout_s,
        )
        self._client_cache[cache_key] = client
        return client

    def clear_client_cache(self) -> None:
        """Clear cached AsyncOpenAI clients. Needed for Celery fork workers where each
        task gets a new event loop and cached clients become bound to a dead loop."""
        self._client_cache.clear()

    async def chat(
        self, 
        messages: list[Mapping[str, str]], 
        *, 
        model: Optional[str] = None, 
        params: Optional[dict] = None,
        options: Optional[LLMCallOptions] = None,
    ) -> dict:
        """Send chat completion request"""
        request_started = time.monotonic()
        request_model = model
        connector = "unknown"
        try:
            normalized_model = model.strip() if isinstance(model, str) else model
            # Prepare request parameters
            request_params = {
                "model": normalized_model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": int(getattr(self.settings, "LLM_DEFAULT_MAX_TOKENS", 1000) or 1000),
            }
            
            # Override with custom params if provided
            request_options = dict(params or {})
            effective_timeout_s = self._take_timeout(request_options, options=options)
            request_params.update(request_options)
            
            logger.info(
                "Sending chat request provider=%s requested_model=%s timeout_s=%s",
                self.provider,
                request_params["model"],
                effective_timeout_s,
            )

            connection = await self._connection_resolver.resolve(request_params.get("model"))
            connector = str(connection.connector or "openai_compatible")
            request_params["model"] = connection.provider_model_name
            request_model = connection.provider_model_name
            client = self._get_or_create_client(
                base_url=connection.base_url,
                api_key=connection.api_key,
                connector=connection.connector,
                extra_config=connection.extra_config,
            )

            # Make the request
            response = await client.chat.completions.create(
                **request_params,
                timeout=effective_timeout_s,
            )
            
            # Extract the response
            message = response.choices[0].message
            content = message.content or ""
            tool_calls = [
                call.model_dump(exclude_none=True)
                for call in (message.tool_calls or [])
            ]
            usage = response.usage.model_dump() if response.usage else {}
            
            duration_ms = int((time.monotonic() - request_started) * 1000)
            self._record_call(
                connector=connector, call_kind="chat", outcome="success",
                duration_ms=duration_ms, usage=usage,
            )
            logger.info(
                "LLM chat request completed connector=%s model=%s timeout_s=%s duration_ms=%s tokens=%s",
                connector, request_model, effective_timeout_s, duration_ms, usage.get("total_tokens", 0),
            )
            
            return {
                "content": content,
                "model": response.model,
                "usage": usage,
                "finish_reason": response.choices[0].finish_reason,
                "tool_calls": tool_calls,
                # Keep the OpenAI/LiteLLM response shape for native tool
                # parsing while retaining the legacy flattened fields above.
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    },
                    "finish_reason": response.choices[0].finish_reason,
                }],
            }
            
        except asyncio.CancelledError:
            duration_ms = int((time.monotonic() - request_started) * 1000)
            self._record_call(connector=connector, call_kind="chat", outcome="cancelled", duration_ms=duration_ms,
                              error_code=LLMErrorCode.CANCELLED.value)
            logger.warning(
                "LLM chat request cancelled model=%s elapsed_ms=%s",
                request_model,
                duration_ms,
            )
            raise
        except Exception as e:
            normalized = self._normalize_error(e)
            duration_ms = int((time.monotonic() - request_started) * 1000)
            self._record_call(connector=connector, call_kind="chat", outcome="error", duration_ms=duration_ms,
                              error_code=normalized.code.value)
            logger.warning(
                "LLM chat request failed connector=%s model=%s timeout_s=%s error_code=%s "
                "status_code=%s provider_code=%s retry_after_ms=%s elapsed_ms=%s",
                connector, request_model, effective_timeout_s, normalized.code.value,
                normalized.status_code, normalized.provider_code, normalized.retry_after_ms, duration_ms,
            )
            raise normalized from e
    
    async def chat_stream(
        self, 
        messages: list[Mapping[str, str]], 
        *, 
        model: Optional[str] = None, 
        params: Optional[dict] = None,
        options: Optional[LLMCallOptions] = None,
    ) -> AsyncIterator[str]:
        """Send streaming chat completion request"""
        request_started = time.monotonic()
        request_model = model
        connector = "unknown"
        usage: dict[str, Any] = {}
        try:
            normalized_model = model.strip() if isinstance(model, str) else model
            # Prepare request parameters
            request_params = {
                "model": normalized_model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": int(getattr(self.settings, "LLM_DEFAULT_MAX_TOKENS", 1000) or 1000),
                "stream": True,
            }
            
            # Override with custom params if provided
            request_options = dict(params or {})
            effective_timeout_s = self._take_timeout(request_options, options=options)
            request_params.update(request_options)
            
            logger.info(f"Sending streaming chat request: provider={self.provider}, model={request_params['model']}")

            connection = await self._connection_resolver.resolve(request_params.get("model"))
            connector = str(connection.connector or "openai_compatible")
            request_params["model"] = connection.provider_model_name
            request_model = connection.provider_model_name
            client = self._get_or_create_client(
                base_url=connection.base_url,
                api_key=connection.api_key,
                connector=connection.connector,
                extra_config=connection.extra_config,
            )

            # Make the streaming request
            stream = await client.chat.completions.create(
                **request_params,
                timeout=effective_timeout_s,
            )
            
            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = chunk.usage.model_dump()
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    yield content
            self._record_call(
                connector=connector, call_kind="stream", outcome="success",
                duration_ms=int((time.monotonic() - request_started) * 1000), usage=usage,
            )
                    
        except asyncio.CancelledError:
            duration_ms = int((time.monotonic() - request_started) * 1000)
            self._record_call(connector=connector, call_kind="stream", outcome="cancelled", duration_ms=duration_ms,
                              error_code=LLMErrorCode.CANCELLED.value)
            logger.warning(
                "LLM streaming request cancelled model=%s elapsed_ms=%s",
                request_model,
                duration_ms,
            )
            raise
        except Exception as e:
            normalized = self._normalize_error(e)
            duration_ms = int((time.monotonic() - request_started) * 1000)
            self._record_call(connector=connector, call_kind="stream", outcome="error", duration_ms=duration_ms,
                              error_code=normalized.code.value)
            logger.warning(
                "LLM streaming request failed connector=%s model=%s error_code=%s status_code=%s elapsed_ms=%s",
                connector, request_model, normalized.code.value, normalized.status_code, duration_ms,
            )
            raise normalized from e

    def _take_timeout(self, params: Optional[dict], *, options: Optional[LLMCallOptions] = None) -> float:
        """Resolve adapter timeout without leaking transport data to providers."""
        if options and options.timeout_s is not None:
            try:
                return max(0.1, float(options.timeout_s))
            except (TypeError, ValueError):
                pass
        return float(self.settings.LLM_TIMEOUT or 30.0)

    @staticmethod
    def _normalize_error(exc: Exception) -> LLMProviderError:
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if not isinstance(status_code, int):
            status_code = getattr(response, "status_code", None)
        body = getattr(exc, "body", None)
        error_body = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
        provider_code = str(error_body.get("code") or error_body.get("type") or "").strip() or None
        provider_message = str(error_body.get("message") or "")
        text = f"{exc} {provider_code or ''} {provider_message}".lower()
        headers = getattr(response, "headers", None) if response is not None else None
        retry_after_ms: Optional[int] = None
        retry_after = headers.get("retry-after") if headers is not None else None
        if retry_after:
            try:
                retry_after_ms = max(0, int(float(retry_after) * 1000))
            except (TypeError, ValueError):
                retry_after_ms = None
        if isinstance(exc, asyncio.TimeoutError) or "timeout" in text:
            code, safe, retryable = LLMErrorCode.TIMEOUT, "LLM provider timed out", True
        elif status_code == 401:
            code, safe, retryable = LLMErrorCode.AUTHENTICATION, "LLM authentication failed", False
        elif status_code == 403:
            code, safe, retryable = LLMErrorCode.AUTHORIZATION, "LLM access was denied", False
        elif status_code == 404:
            code, safe, retryable = LLMErrorCode.MODEL_NOT_FOUND, "LLM model was not found", False
        elif status_code == 429:
            code, safe, retryable = LLMErrorCode.RATE_LIMITED, "LLM provider rate limit reached", True
        elif status_code == 413 or any(marker in text for marker in ("context_length_exceeded", "maximum context length", "request too large")):
            code, safe, retryable = LLMErrorCode.REQUEST_TOO_LARGE, "LLM request exceeds provider limits", False
        elif "tool" in text and ("not support" in text or "unsupported" in text or "tool_use_failed" in text):
            code, safe, retryable = LLMErrorCode.TOOL_CALLING_UNSUPPORTED, "LLM does not support native tool calling", False
        elif "response_format" in text or "json_schema" in text:
            code, safe, retryable = LLMErrorCode.STRUCTURED_OUTPUT_UNSUPPORTED, "LLM does not support structured output", False
        elif status_code is not None and 400 <= status_code < 500:
            code, safe, retryable = LLMErrorCode.INVALID_REQUEST, "LLM rejected the request", False
        elif status_code is not None and status_code >= 500:
            code, safe, retryable = LLMErrorCode.UPSTREAM, "LLM provider is unavailable", True
        elif "connection" in text or "connect" in text or "reset" in text:
            code, safe, retryable = LLMErrorCode.CONNECTION, "LLM provider connection failed", True
        else:
            code, safe, retryable = LLMErrorCode.UNKNOWN, "LLM request failed", True
        return LLMProviderError(code=code, safe_message=safe, retryable=retryable,
                                status_code=status_code, provider_type=type(exc).__name__,
                                provider_code=provider_code, retry_after_ms=retry_after_ms)

    @staticmethod
    def _record_call(*, connector: str, call_kind: str, outcome: str, duration_ms: int,
                     error_code: str = "", usage: Optional[dict] = None) -> None:
        try:
            from app.core.prometheus_metrics import record_llm_adapter_call
            record_llm_adapter_call(
                connector=connector, call_kind=call_kind, outcome=outcome,
                error_code=error_code, duration_ms=duration_ms, usage=usage,
            )
        except Exception:
            pass
    
    async def list_models(self) -> list[dict]:
        """
        List available models.
        
        Note: Some providers (like Groq) don't support /v1/models endpoint,
        so we return a configured list from settings or hardcoded defaults.
        """
        try:
            # Try to fetch from resolved endpoint first.
            try:
                if self.client is None:
                    return []
                models_response = await self.client.models.list()
                return [
                    {
                        "id": model.id,
                        "name": model.id,
                        "provider": self.provider,
                        "created": getattr(model, 'created', None)
                    }
                    for model in models_response.data
                ]
            except Exception as api_error:
                logger.warning(f"Could not fetch models from API: {api_error}")
                return []
            
        except Exception as e:
            logger.error(f"Error listing models: {str(e)}")
            return []
    
    async def health_check(self) -> dict:
        """Check if LLM service is healthy"""
        try:
            # Simple health check with minimal request
            test_messages = [{"role": "user", "content": "test"}]
            response = await self.chat(test_messages, params={"max_tokens": 5})
            
            return {
                "status": "healthy",
                "provider": self.provider,
                "base_url": "resolved_via_connector",
                "model": response.get("model", "unknown")
            }
            
        except Exception as e:
            logger.error(f"LLM health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "provider": self.provider,
                "base_url": "resolved_via_connector",
                "error": str(e)
            }

    async def aclose(self) -> None:
        for client in self._client_cache.values():
            try:
                await client.close()
            except RuntimeError as exc:
                if "Event loop is closed" in str(exc):
                    logger.debug("Skipping LLM client close during loop shutdown: %s", exc)
                    continue
                raise
        self._client_cache.clear()
