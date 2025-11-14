"""
LLM client implementation using OpenAI API (supports Groq and other OpenAI-compatible services)
"""
from __future__ import annotations
from typing import Any, AsyncIterator, Mapping, Optional
import asyncio
import logging
from openai import AsyncOpenAI
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM client using OpenAI-compatible API (supports Groq, OpenAI, etc.)"""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = AsyncOpenAI(
            base_url=self.settings.GROQ_BASE_URL,
            api_key=self.settings.GROQ_API_KEY,
            timeout=30.0
        )
        self.default_model = self.settings.GROQ_DEFAULT_MODEL
    
    async def chat(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, params: Optional[dict] = None) -> dict:
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
            
            logger.info(f"Sending chat request with model: {request_params['model']}")
            
            # Make the request
            response = await self.client.chat.completions.create(**request_params)
            
            # Extract the response
            content = response.choices[0].message.content
            usage = response.usage.model_dump() if response.usage else {}
            
            logger.info(f"Received response: {len(content)} characters")
            
            return {
                "content": content,
                "model": response.model,
                "usage": usage,
                "finish_reason": response.choices[0].finish_reason
            }
            
        except Exception as e:
            logger.error(f"Error in chat request: {str(e)}")
            raise
    
    async def chat_stream(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, params: Optional[dict] = None) -> AsyncIterator[str]:
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
            
            logger.info(f"Sending streaming chat request with model: {request_params['model']}")
            
            # Make the streaming request
            stream = await self.client.chat.completions.create(**request_params)
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    logger.debug(f"Received chunk: {len(content)} characters")
                    yield content
                    
        except Exception as e:
            logger.error(f"Error in streaming chat request: {str(e)}")
            raise
    
    async def list_models(self) -> list[dict]:
        """List available models"""
        try:
            # Return hardcoded list of commonly available models
            models = [
                {
                    "id": "llama-3.1-8b-instant",
                    "name": "Llama 3.1 8B Instant",
                    "description": "Fast and efficient model for quick responses",
                    "provider": "groq"
                },
                {
                    "id": "llama-3.1-70b-versatile", 
                    "name": "Llama 3.1 70B Versatile",
                    "description": "More capable model for complex tasks",
                    "provider": "groq"
                },
                {
                    "id": "mixtral-8x7b-32768",
                    "name": "Mixtral 8x7B",
                    "description": "Mixture of experts model",
                    "provider": "groq"
                }
            ]
            
            logger.info(f"Returning {len(models)} models")
            return models
            
        except Exception as e:
            logger.error(f"Error listing models: {str(e)}")
            return []
    
    async def health_check(self) -> dict:
        """Check if LLM service is healthy"""
        try:
            # Simple health check with minimal request
            test_messages = [{"role": "user", "content": "Hello"}]
            response = await self.chat(test_messages, params={"max_tokens": 10})
            
            return {
                "status": "healthy",
                "provider": self.settings.LLM_PROVIDER,
                "model": response.get("model", "unknown")
            }
            
        except Exception as e:
            logger.error(f"LLM health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "provider": self.settings.LLM_PROVIDER,
                "error": str(e)
            }
