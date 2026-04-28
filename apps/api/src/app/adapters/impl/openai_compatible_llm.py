"""
Universal LLM client for OpenAI-compatible APIs
Supports: OpenAI, Groq, Azure OpenAI, LocalAI, vLLM, Ollama, etc.
"""
from __future__ import annotations
from typing import Any, AsyncIterator, Mapping, Optional
import os
from app.core.logging import get_logger
from openai import AsyncOpenAI
from app.core.config import get_settings

logger = get_logger(__name__)


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
    
    def __init__(self):
        self.settings = get_settings()
        self._default_base_url = self.settings.LLM_BASE_URL
        self._default_api_key = self.settings.LLM_API_KEY
        self._client_cache: dict[tuple[str, Optional[str]], AsyncOpenAI] = {}
        self.client = self._get_or_create_client(
            base_url=self._default_base_url,
            api_key=self._default_api_key,
        )
        
        self.default_model = self.settings.LLM_DEFAULT_MODEL
        self.provider = self.settings.LLM_PROVIDER
        
        logger.info(f"Initialized LLM client: provider={self.provider}, base_url={self.settings.LLM_BASE_URL}")

    def _get_or_create_client(self, *, base_url: str, api_key: Optional[str]) -> AsyncOpenAI:
        cache_key = (base_url.rstrip("/"), api_key)
        client = self._client_cache.get(cache_key)
        if client is not None:
            return client

        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=self.settings.LLM_TIMEOUT or 30.0,
        )
        self._client_cache[cache_key] = client
        return client

    @staticmethod
    def _extract_secret(payload: dict, auth_type: str) -> Optional[str]:
        if auth_type == "api_key":
            return payload.get("api_key")
        if auth_type == "token":
            return payload.get("token")
        if auth_type == "basic":
            return payload.get("password")
        return None

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        text = str(exc).lower()
        auth_markers = (
            "invalid_api_key",
            "invalid api key",
            "error code: 401",
            "401 unauthorized",
            "unauthorized",
            "authenticationerror",
        )
        return any(marker in text for marker in auth_markers)

    def _should_retry_with_default_connection(
        self,
        *,
        runtime_base_url: str,
        runtime_api_key: Optional[str],
        exc: Exception,
    ) -> bool:
        if not self._is_auth_error(exc):
            return False
        return (
            runtime_base_url.rstrip("/") != str(self._default_base_url or "").rstrip("/")
            or runtime_api_key != self._default_api_key
        )

    async def _resolve_model_connection(self, model_name: Optional[str]) -> tuple[str, Optional[str]]:
        base_url = self._default_base_url
        api_key = self._default_api_key

        if not model_name:
            return base_url, api_key

        try:
            from sqlalchemy import or_, select
            from app.core.db import get_session_factory
            from app.models.model_registry import Model, ModelType
            from app.services.credential_service import CredentialService

            session_factory = get_session_factory()
            async with session_factory() as session:
                result = await session.execute(
                    select(Model)
                    .where(
                        Model.type == ModelType.LLM_CHAT,
                        Model.deleted_at.is_(None),
                        Model.enabled == True,  # noqa: E712
                        or_(
                            Model.alias == model_name,
                            Model.provider_model_name == model_name,
                        ),
                    )
                    .order_by(Model.default_for_type.desc(), Model.updated_at.desc())
                    .limit(1)
                )
                model = result.scalar_one_or_none()

                if model is None:
                    return base_url, api_key

                resolved_base_url = (
                    model.base_url
                    or (model.instance.url if model.instance else None)
                    or ((model.extra_config or {}).get("base_url"))
                    or base_url
                )

                resolved_api_key: Optional[str] = None
                if model.instance_id:
                    decrypted = await CredentialService(session).resolve_credentials(
                        instance_id=model.instance_id,
                        strategy="PLATFORM_FIRST",
                    )
                    if decrypted:
                        resolved_api_key = self._extract_secret(
                            decrypted.payload or {},
                            decrypted.auth_type,
                        )

                if (
                    not resolved_api_key
                    and model.instance
                    and isinstance(model.instance.config, dict)
                ):
                    resolved_api_key = model.instance.config.get("api_key")
                    if not resolved_api_key:
                        api_key_ref = model.instance.config.get("api_key_ref")
                        if api_key_ref:
                            resolved_api_key = os.getenv(api_key_ref)

                return resolved_base_url, resolved_api_key or api_key
        except Exception as exc:
            logger.warning(
                "Failed to resolve runtime LLM connection for model '%s': %s",
                model_name,
                exc,
            )
            return base_url, api_key
    
    async def chat(
        self, 
        messages: list[Mapping[str, str]], 
        *, 
        model: Optional[str] = None, 
        params: Optional[dict] = None
    ) -> dict:
        """Send chat completion request"""
        try:
            # Prepare request parameters
            request_params = {
                "model": model or self.default_model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1000,
            }
            
            # Override with custom params if provided
            if params:
                request_params.update(params)
            
            logger.info(f"Sending chat request: provider={self.provider}, model={request_params['model']}")

            runtime_base_url, runtime_api_key = await self._resolve_model_connection(
                request_params.get("model")
            )
            client = self._get_or_create_client(
                base_url=runtime_base_url,
                api_key=runtime_api_key,
            )

            # Make the request
            try:
                response = await client.chat.completions.create(**request_params)
            except Exception as exc:
                if not self._should_retry_with_default_connection(
                    runtime_base_url=runtime_base_url,
                    runtime_api_key=runtime_api_key,
                    exc=exc,
                ):
                    raise
                logger.warning(
                    "Runtime model credentials failed auth; retrying with default LLM connection (model=%s)",
                    request_params.get("model"),
                )
                fallback_client = self._get_or_create_client(
                    base_url=self._default_base_url,
                    api_key=self._default_api_key,
                )
                response = await fallback_client.chat.completions.create(**request_params)
            
            # Extract the response
            content = response.choices[0].message.content
            usage = response.usage.model_dump() if response.usage else {}
            
            logger.info(f"Received response: {len(content)} characters, tokens={usage.get('total_tokens', 0)}")
            
            return {
                "content": content,
                "model": response.model,
                "usage": usage,
                "finish_reason": response.choices[0].finish_reason
            }
            
        except Exception as e:
            logger.error(f"Error in chat request: {str(e)}", exc_info=True)
            raise
    
    async def chat_stream(
        self, 
        messages: list[Mapping[str, str]], 
        *, 
        model: Optional[str] = None, 
        params: Optional[dict] = None
    ) -> AsyncIterator[str]:
        """Send streaming chat completion request"""
        try:
            # Prepare request parameters
            request_params = {
                "model": model or self.default_model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1000,
                "stream": True,
            }
            
            # Override with custom params if provided
            if params:
                request_params.update(params)
            
            logger.info(f"Sending streaming chat request: provider={self.provider}, model={request_params['model']}")

            runtime_base_url, runtime_api_key = await self._resolve_model_connection(
                request_params.get("model")
            )
            client = self._get_or_create_client(
                base_url=runtime_base_url,
                api_key=runtime_api_key,
            )

            # Make the streaming request
            try:
                stream = await client.chat.completions.create(**request_params)
            except Exception as exc:
                if not self._should_retry_with_default_connection(
                    runtime_base_url=runtime_base_url,
                    runtime_api_key=runtime_api_key,
                    exc=exc,
                ):
                    raise
                logger.warning(
                    "Runtime model credentials failed auth for stream; retrying with default LLM connection (model=%s)",
                    request_params.get("model"),
                )
                fallback_client = self._get_or_create_client(
                    base_url=self._default_base_url,
                    api_key=self._default_api_key,
                )
                stream = await fallback_client.chat.completions.create(**request_params)
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    yield content
                    
        except Exception as e:
            logger.error(f"Error in streaming chat request: {str(e)}", exc_info=True)
            raise
    
    async def list_models(self) -> list[dict]:
        """
        List available models.
        
        Note: Some providers (like Groq) don't support /v1/models endpoint,
        so we return a configured list from settings or hardcoded defaults.
        """
        try:
            # Try to fetch from API first
            try:
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
                logger.warning(f"Could not fetch models from API: {api_error}, using defaults")
                
                # Fallback to provider-specific defaults
                return self._get_default_models()
            
        except Exception as e:
            logger.error(f"Error listing models: {str(e)}")
            return []
    
    def _get_default_models(self) -> list[dict]:
        """Get default models based on provider"""
        
        # Provider-specific model lists
        models_by_provider = {
            "groq": [
                {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant"},
                {"id": "llama-3.1-70b-versatile", "name": "Llama 3.1 70B Versatile"},
                {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B"},
                {"id": "gemma2-9b-it", "name": "Gemma 2 9B"},
                {"id": "compound-beta", "name": "Compound Beta"},
            ],
            "openai": [
                {"id": "gpt-4-turbo-preview", "name": "GPT-4 Turbo"},
                {"id": "gpt-4", "name": "GPT-4"},
                {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo"},
            ],
            "azure": [
                {"id": "gpt-4", "name": "GPT-4 (Azure)"},
                {"id": "gpt-35-turbo", "name": "GPT-3.5 Turbo (Azure)"},
            ],
            "local": [
                {"id": self.default_model, "name": f"Local Model ({self.default_model})"},
            ]
        }
        
        # Get models for current provider or use default
        provider_models = models_by_provider.get(
            self.provider.lower(), 
            [{"id": self.default_model, "name": self.default_model}]
        )
        
        # Add provider info to each model
        return [
            {**model, "provider": self.provider}
            for model in provider_models
        ]
    
    async def health_check(self) -> dict:
        """Check if LLM service is healthy"""
        try:
            # Simple health check with minimal request
            test_messages = [{"role": "user", "content": "test"}]
            response = await self.chat(test_messages, params={"max_tokens": 5})
            
            return {
                "status": "healthy",
                "provider": self.provider,
                "base_url": self.settings.LLM_BASE_URL,
                "model": response.get("model", "unknown")
            }
            
        except Exception as e:
            logger.error(f"LLM health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "provider": self.provider,
                "base_url": self.settings.LLM_BASE_URL,
                "error": str(e)
            }

    async def aclose(self) -> None:
        for client in self._client_cache.values():
            await client.close()
        self._client_cache.clear()
