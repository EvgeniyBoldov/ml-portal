"""
Mock LLM Server для E2E тестов
Имитирует ответы LLM для детерминированного тестирования
"""
import json
import time
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn

app = FastAPI(title="Mock LLM Server")

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = "test-model"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000

class ToolCall(BaseModel):
    id: str
    tool: str
    arguments: Dict[str, Any]

class ChatResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    error: Optional[str] = None

def determine_response(messages: List[ChatMessage]) -> ChatResponse:
    """Определяет ответ на основе последнего сообщения"""
    if not messages:
        return ChatResponse(content="Hello! How can I help you?")
    
    last_message = messages[-1].content.lower()
    
    # Tool execution scenarios
    if "search" in last_message or "find" in last_message or "найди" in last_message:
        return ChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id=f"call_{int(time.time())}",
                    tool="rag.search",
                    arguments={"query": messages[-1].content}
                )
            ]
        )
    
    # Multiple tools scenario
    if "search for ai and then ml" in last_message or "найди ai и ml" in last_message:
        return ChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id=f"call_{int(time.time())}_1",
                    tool="rag.search",
                    arguments={"query": "artificial intelligence"}
                )
            ]
        )
    
    # Error scenario
    if "error" in last_message or "ошибка" in last_message:
        return ChatResponse(error="Mock LLM error for testing")
    
    # Complex query scenario (multiple steps)
    if "comprehensive" in last_message or "полный" in last_message:
        return ChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id=f"call_{int(time.time())}",
                    tool="rag.search",
                    arguments={"query": "comprehensive analysis"}
                )
            ]
        )
    
    # Default response
    return ChatResponse(content="This is a mock response from the LLM for testing purposes.")

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """Основной endpoint для chat completions"""
    response = determine_response(request.messages)
    
    # Add small delay to simulate real LLM
    await asyncio.sleep(0.01)
    
    return response.model_dump()

@app.post("/v1/chat/completions/stream")
async def chat_completions_stream(request: ChatRequest):
    """Streaming endpoint для chat completions"""
    response = determine_response(request.messages)
    
    async def generate_stream():
        # Simulate streaming chunks
        if response.content:
            words = response.content.split()
            for i, word in enumerate(words):
                chunk = {
                    "choices": [{
                        "delta": {"content": word + (" " if i < len(words) - 1 else "")}
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0.01)
        elif response.tool_calls:
            chunk = {
                "choices": [{
                    "delta": {
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "tool": tc.tool,
                                "arguments": json.dumps(tc.arguments)
                            }
                            for tc in response.tool_calls
                        ]
                    }
                }]
            }
            yield f"data: {json.dumps(chunk)}\n\n"
        elif response.error:
            chunk = {
                "choices": [{
                    "delta": {"content": f"Error: {response.error}"}
                }]
            }
            yield f"data: {json.dumps(chunk)}\n\n"
        
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(generate_stream(), media_type="text/plain")

@app.get("/v1/models")
async def list_models():
    """Список доступных моделей"""
    return {
        "data": [
            {"id": "test-model", "object": "model"},
            {"id": "fast-model", "object": "model"},
            {"id": "slow-model", "object": "model"}
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "mock-llm"}

if __name__ == "__main__":
    import asyncio
    uvicorn.run(app, host="0.0.0.0", port=8000)
