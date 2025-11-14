"""
Universal LLM client for OpenAI-compatible APIs
Supports: OpenAI, Groq, Azure OpenAI, LocalAI, vLLM, Ollama, etc.
"""
from __future__ import annotations
from typing import Any, AsyncIterator, Mapping, Optional
import logging
from openai import AsyncOpenAI
from app.core.config import get_settings

logger = logging.getLogger(__name__)


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
        
        # Use generic LLM_* variables
        self.client = AsyncOpenAI(
            base_url=self.settings.LLM_BASE_URL,
            api_key=self.settings.LLM_API_KEY,
            timeout=self.settings.LLM_TIMEOUT or 30.0
        )
        
        self.default_model = self.settings.LLM_DEFAULT_MODEL
        self.provider = self.settings.LLM_PROVIDER
        
        logger.info(f"Initialized LLM client: provider={self.provider}, base_url={self.settings.LLM_BASE_URL}")
    
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
            
            # Make the request
            response = await self.client.chat.completions.create(**request_params)
            
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
            
            # Make the streaming request
            stream = await self.client.chat.completions.create(**request_params)
            
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
