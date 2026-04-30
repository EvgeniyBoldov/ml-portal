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
        self._client_cache: dict[tuple[str, Optional[str]], AsyncOpenAI] = {}
        self.client: Optional[AsyncOpenAI] = None
        self.provider = "connector"
        logger.info("Initialized LLM client via connector chain")

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

    async def _resolve_model_connection(self, model_name: Optional[str]) -> tuple[str, Optional[str], str]:
        try:
            from sqlalchemy import or_, select
            from app.core.db import get_session_factory
            from app.models.model_registry import Model, ModelType
            from app.services.credential_service import CredentialService

            session_factory = get_session_factory()
            async with session_factory() as session:
                stmt = (
                    select(Model)
                    .where(
                        Model.type == ModelType.LLM_CHAT,
                        Model.deleted_at.is_(None),
                        Model.enabled == True,  # noqa: E712
                    )
                    .order_by(Model.default_for_type.desc(), Model.updated_at.desc())
                    .limit(1)
                )
                if model_name:
                    stmt = (
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
                result = await session.execute(stmt)
                model = result.scalar_one_or_none()

                if model is None:
                    raise ValueError(
                        f"LLM model is not configured in registry for selector '{model_name or 'default'}'"
                    )

                resolved_base_url = (
                    model.base_url
                    or (model.instance.url if model.instance else None)
                    or ((model.extra_config or {}).get("base_url"))
                )
                if not resolved_base_url:
                    raise ValueError(
                        f"Model '{model.alias}' has no connector/base_url configured"
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

                return resolved_base_url, resolved_api_key, str(model.provider_model_name or model.alias)
        except Exception as exc:
            logger.error(
                "Failed to resolve runtime LLM connection for model '%s': %s",
                model_name,
                exc,
            )
            raise
    
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
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1000,
            }
            
            # Override with custom params if provided
            if params:
                request_params.update(params)
            
            logger.info(f"Sending chat request: provider={self.provider}, model={request_params['model']}")

            runtime_base_url, runtime_api_key, resolved_model_name = await self._resolve_model_connection(
                request_params.get("model")
            )
            request_params["model"] = resolved_model_name
            client = self._get_or_create_client(
                base_url=runtime_base_url,
                api_key=runtime_api_key,
            )

            # Make the request
            try:
                response = await client.chat.completions.create(**request_params)
            except Exception:
                raise
            
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
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1000,
                "stream": True,
            }
            
            # Override with custom params if provided
            if params:
                request_params.update(params)
            
            logger.info(f"Sending streaming chat request: provider={self.provider}, model={request_params['model']}")

            runtime_base_url, runtime_api_key, resolved_model_name = await self._resolve_model_connection(
                request_params.get("model")
            )
            request_params["model"] = resolved_model_name
            client = self._get_or_create_client(
                base_url=runtime_base_url,
                api_key=runtime_api_key,
            )

            # Make the streaming request
            try:
                stream = await client.chat.completions.create(**request_params)
            except Exception:
                raise
            
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
            await client.close()
        self._client_cache.clear()
