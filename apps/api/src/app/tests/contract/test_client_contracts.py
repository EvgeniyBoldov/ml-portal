"""
Contract tests for LLM/EMB client interfaces
"""
from __future__ import annotations
from typing import List, Literal, Union, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, ValidationError
import pytest
from unittest.mock import Mock, AsyncMock

from app.schemas.chat_messages import ChatMessage
from app.core.di import LLMClientProtocol, EmbClientProtocol, HTTPLLMClient, HTTPEmbClient


class LLMGenerateRequest(BaseModel):
    """LLM generate request contract"""
    model_config = ConfigDict(extra='forbid')
    
    messages: List[ChatMessage] = Field(..., description="Chat messages")
    model: str = Field(default="default", description="Model name")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature")
    max_tokens: Optional[int] = Field(None, gt=0, description="Max tokens")
    timeout: Optional[int] = Field(None, gt=0, description="Request timeout")
    retries: Optional[int] = Field(None, ge=0, le=5, description="Retry count")


class LLMGenerateResponse(BaseModel):
    """LLM generate response contract"""
    model_config = ConfigDict(extra='forbid')
    
    text: str = Field(..., description="Generated text")
    model: str = Field(..., description="Model used")
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage")


class LLMChatRequest(BaseModel):
    """LLM chat request contract"""
    model_config = ConfigDict(extra='forbid')
    
    messages: List[ChatMessage] = Field(..., description="Chat messages")
    model: str = Field(default="default", description="Model name")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature")
    max_tokens: Optional[int] = Field(None, gt=0, description="Max tokens")
    stream: Optional[bool] = Field(False, description="Stream response")
    timeout: Optional[int] = Field(None, gt=0, description="Request timeout")
    retries: Optional[int] = Field(None, ge=0, le=5, description="Retry count")


class LLMChatResponse(BaseModel):
    """LLM chat response contract"""
    model_config = ConfigDict(extra='forbid')
    
    message: ChatMessage = Field(..., description="Response message")
    model: str = Field(..., description="Model used")
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage")
    finish_reason: Optional[str] = Field(None, description="Finish reason")


class EmbEmbedRequest(BaseModel):
    """Embedding request contract"""
    model_config = ConfigDict(extra='forbid')
    
    texts: List[str] = Field(..., min_length=1, description="Texts to embed")
    model: str = Field(default="default", description="Model name")
    timeout: Optional[int] = Field(None, gt=0, description="Request timeout")
    retries: Optional[int] = Field(None, ge=0, le=5, description="Retry count")


class EmbEmbedResponse(BaseModel):
    """Embedding response contract"""
    model_config = ConfigDict(extra='forbid')
    
    embeddings: List[List[float]] = Field(..., description="Embedding vectors")
    model: str = Field(..., description="Model used")
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage")


class EmbQueryRequest(BaseModel):
    """Embedding query request contract"""
    model_config = ConfigDict(extra='forbid')
    
    query: str = Field(..., min_length=1, description="Query text")
    model: str = Field(default="default", description="Model name")
    timeout: Optional[int] = Field(None, gt=0, description="Request timeout")
    retries: Optional[int] = Field(None, ge=0, le=5, description="Retry count")


class EmbQueryResponse(BaseModel):
    """Embedding query response contract"""
    model_config = ConfigDict(extra='forbid')
    
    embedding: List[float] = Field(..., description="Query embedding vector")
    model: str = Field(..., description="Model used")
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage")


class ContractLLMClient(LLMClientProtocol):
    """Contract-compliant LLM client implementation"""
    
    async def generate(self, messages: List[ChatMessage], model: str = "default", **kwargs) -> str:
        """Generate text from messages - contract compliant"""
        # Validate request
        request = LLMGenerateRequest(messages=messages, model=model, **kwargs)
        
        # Mock implementation
        return "Generated response"
    
    async def chat(self, messages: List[ChatMessage], model: str = "default", **kwargs) -> Dict[str, Any]:
        """Chat completion - contract compliant"""
        # Validate request
        request = LLMChatRequest(messages=messages, model=model, **kwargs)
        
        # Mock implementation
        return {
            "message": ChatMessage(role="assistant", content="Chat response"),
            "model": model,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "finish_reason": "stop"
        }


class ContractEmbClient(EmbClientProtocol):
    """Contract-compliant Embedding client implementation"""
    
    async def embed_texts(self, texts: List[str], model: str = "default") -> List[List[float]]:
        """Embed texts into vectors - contract compliant"""
        # Validate request
        request = EmbEmbedRequest(texts=texts, model=model)
        
        # Mock implementation
        return [[0.1, 0.2, 0.3] for _ in texts]
    
    async def embed_query(self, query: str, model: str = "default") -> List[float]:
        """Embed single query - contract compliant"""
        # Validate request
        request = EmbQueryRequest(query=query, model=model)
        
        # Mock implementation
        return [0.1, 0.2, 0.3]


class TestChatMessageContract:
    """Test ChatMessage contract compliance"""
    
    def test_valid_user_message(self):
        """Test valid user message creation"""
        msg = ChatMessage.create_user_message("Hello, World!")
        assert msg.role == "user"
        assert msg.content == "Hello, World!"
    
    def test_valid_system_message(self):
        """Test valid system message creation"""
        msg = ChatMessage.create_system_message("You are a helpful assistant.")
        assert msg.role == "system"
        assert msg.content == "You are a helpful assistant."
    
    def test_valid_assistant_message(self):
        """Test valid assistant message creation"""
        msg = ChatMessage.create_assistant_message("Hello! How can I help you?")
        assert msg.role == "assistant"
        assert msg.content == "Hello! How can I help you?"
    
    def test_valid_tool_message(self):
        """Test valid tool message creation"""
        msg = ChatMessage.create_tool_message("call_123", "Tool result")
        assert msg.role == "tool"
        assert isinstance(msg.content, dict)
        assert msg.content["tool_call_id"] == "call_123"
        assert msg.content["content"] == "Tool result"
    
    def test_invalid_role(self):
        """Test invalid role validation"""
        with pytest.raises(ValidationError):
            ChatMessage(role="invalid_role", content="Test")
    
    def test_empty_content_string(self):
        """Test empty content validation"""
        with pytest.raises(ValidationError):
            ChatMessage(role="user", content="")
    
    def test_empty_content_dict(self):
        """Test empty content dict validation"""
        with pytest.raises(ValidationError):
            ChatMessage(role="user", content={})
    
    def test_extra_fields_forbidden(self):
        """Test that extra fields are forbidden"""
        with pytest.raises(ValidationError):
            ChatMessage(role="user", content="Test", extra_field="not_allowed")
    
    def test_serialization_deserialization(self):
        """Test message serialization and deserialization"""
        original = ChatMessage.create_user_message("Hello, World!")
        
        # Serialize
        data = original.model_dump()
        
        # Deserialize
        restored = ChatMessage.model_validate(data)
        
        assert restored.role == original.role
        assert restored.content == original.content
    
    def test_complex_tool_message_serialization(self):
        """Test complex tool message serialization"""
        complex_content = {
            "type": "tool",
            "data": {
                "function": "search",
                "parameters": {"query": "test", "limit": 10},
                "result": {"items": [{"title": "Test", "url": "http://test.com"}]}
            }
        }
        
        msg = ChatMessage(role="tool", content=complex_content)
        
        # Serialize and deserialize
        data = msg.model_dump()
        restored = ChatMessage.model_validate(data)
        
        assert restored.role == "tool"
        assert restored.content == complex_content


class TestLLMClientContract:
    """Test LLM client contract compliance"""
    
    @pytest.mark.asyncio
    async def test_generate_valid_request(self):
        """Test valid generate request"""
        client = ContractLLMClient()
        messages = [ChatMessage.create_user_message("Hello")]
        
        result = await client.generate(messages, model="test-model")
        assert isinstance(result, str)
        assert result == "Generated response"
    
    @pytest.mark.asyncio
    async def test_generate_with_kwargs(self):
        """Test generate with valid kwargs"""
        client = ContractLLMClient()
        messages = [ChatMessage.create_user_message("Hello")]
        
        result = await client.generate(
            messages, 
            model="test-model",
            temperature=0.7,
            max_tokens=100,
            timeout=30,
            retries=3
        )
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_generate_invalid_kwargs(self):
        """Test generate with invalid kwargs"""
        client = ContractLLMClient()
        messages = [ChatMessage.create_user_message("Hello")]
        
        with pytest.raises(ValidationError):
            await client.generate(messages, model="test-model", invalid_param="not_allowed")
    
    @pytest.mark.asyncio
    async def test_generate_invalid_temperature(self):
        """Test generate with invalid temperature"""
        client = ContractLLMClient()
        messages = [ChatMessage.create_user_message("Hello")]
        
        with pytest.raises(ValidationError):
            await client.generate(messages, model="test-model", temperature=3.0)
    
    @pytest.mark.asyncio
    async def test_generate_invalid_max_tokens(self):
        """Test generate with invalid max_tokens"""
        client = ContractLLMClient()
        messages = [ChatMessage.create_user_message("Hello")]
        
        with pytest.raises(ValidationError):
            await client.generate(messages, model="test-model", max_tokens=0)
    
    @pytest.mark.asyncio
    async def test_chat_valid_request(self):
        """Test valid chat request"""
        client = ContractLLMClient()
        messages = [ChatMessage.create_user_message("Hello")]
        
        result = await client.chat(messages, model="test-model")
        assert isinstance(result, dict)
        assert "message" in result
        assert "model" in result
    
    @pytest.mark.asyncio
    async def test_chat_with_stream(self):
        """Test chat with streaming"""
        client = ContractLLMClient()
        messages = [ChatMessage.create_user_message("Hello")]
        
        result = await client.chat(messages, model="test-model", stream=True)
        assert isinstance(result, dict)


class TestEmbClientContract:
    """Test Embedding client contract compliance"""
    
    @pytest.mark.asyncio
    async def test_embed_texts_valid_request(self):
        """Test valid embed_texts request"""
        client = ContractEmbClient()
        texts = ["Hello", "World"]
        
        result = await client.embed_texts(texts, model="test-model")
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(emb, list) for emb in result)
        assert all(isinstance(val, float) for emb in result for val in emb)
    
    @pytest.mark.asyncio
    async def test_embed_texts_empty_list(self):
        """Test embed_texts with empty list"""
        client = ContractEmbClient()
        
        with pytest.raises(ValidationError):
            await client.embed_texts([], model="test-model")
    
    @pytest.mark.asyncio
    async def test_embed_texts_invalid_kwargs(self):
        """Test embed_texts with invalid kwargs"""
        client = ContractEmbClient()
        texts = ["Hello"]
        
        with pytest.raises(ValidationError):
            await client.embed_texts(texts, model="test-model", invalid_param="not_allowed")
    
    @pytest.mark.asyncio
    async def test_embed_query_valid_request(self):
        """Test valid embed_query request"""
        client = ContractEmbClient()
        
        result = await client.embed_query("Hello", model="test-model")
        assert isinstance(result, list)
        assert all(isinstance(val, float) for val in result)
    
    @pytest.mark.asyncio
    async def test_embed_query_empty_string(self):
        """Test embed_query with empty string"""
        client = ContractEmbClient()
        
        with pytest.raises(ValidationError):
            await client.embed_query("", model="test-model")
    
    @pytest.mark.asyncio
    async def test_embed_query_invalid_kwargs(self):
        """Test embed_query with invalid kwargs"""
        client = ContractEmbClient()
        
        with pytest.raises(ValidationError):
            await client.embed_query("Hello", model="test-model", invalid_param="not_allowed")


class TestContractIntegration:
    """Test contract integration with real clients"""
    
    def test_http_llm_client_implements_protocol(self):
        """Test that HTTPLLMClient implements LLMClientProtocol"""
        client = HTTPLLMClient("http://test", timeout=5)
        assert isinstance(client, LLMClientProtocol)
    
    def test_http_emb_client_implements_protocol(self):
        """Test that HTTPEmbClient implements EmbClientProtocol"""
        client = HTTPEmbClient("http://test", timeout=5)
        assert isinstance(client, EmbClientProtocol)
    
    def test_contract_client_implements_protocol(self):
        """Test that contract clients implement protocols"""
        llm_client = ContractLLMClient()
        emb_client = ContractEmbClient()
        
        assert isinstance(llm_client, LLMClientProtocol)
        assert isinstance(emb_client, EmbClientProtocol)
    
    def test_message_types_consistency(self):
        """Test that message types are consistent across contracts"""
        # Test that ChatMessage can be used in all contexts
        user_msg = ChatMessage.create_user_message("Hello")
        system_msg = ChatMessage.create_system_message("System prompt")
        assistant_msg = ChatMessage.create_assistant_message("Response")
        tool_msg = ChatMessage.create_tool_message("call_123", "Tool result")
        
        # All should be valid ChatMessage instances
        assert isinstance(user_msg, ChatMessage)
        assert isinstance(system_msg, ChatMessage)
        assert isinstance(assistant_msg, ChatMessage)
        assert isinstance(tool_msg, ChatMessage)
        
        # All should be serializable
        for msg in [user_msg, system_msg, assistant_msg, tool_msg]:
            data = msg.model_dump()
            restored = ChatMessage.model_validate(data)
            assert restored.role == msg.role
            assert restored.content == msg.content
