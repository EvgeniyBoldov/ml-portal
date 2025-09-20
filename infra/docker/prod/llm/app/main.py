"""
LLM (Generation Service) - FastAPI приложение
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import asyncio
import json
import time
import logging
import os
from contextlib import asynccontextmanager

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные для backpressure
MAX_INFLIGHT = int(os.getenv("MAX_INFLIGHT", "50"))
# Используем Semaphore для thread-safe backpressure
INFLIGHT_SEMAPHORE = asyncio.Semaphore(MAX_INFLIGHT)

# Модели (заглушка для демонстрации)
LLM_MODELS = {
    "gpt-3.5-turbo": {
        "alias": "gpt-3.5-turbo",
        "provider": "openai",
        "max_tokens": 4096
    },
    "gpt-4": {
        "alias": "gpt-4",
        "provider": "openai",
        "max_tokens": 8192
    }
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка ресурсов"""
    # Инициализация моделей
    logger.info("Initializing LLM models...")
    # TODO: Загрузить модели
    yield
    # Очистка
    logger.info("Shutting down LLM service...")

app = FastAPI(
    title="LLM Service",
    description="Generation Service for ML Portal",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:3000", "http://localhost:8080", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = "gpt-3.5-turbo"
    system_prompt: Optional[str] = None
    rag_context: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = True

class CompleteRequest(BaseModel):
    prompt: str
    model: str = "gpt-3.5-turbo"
    system_prompt: Optional[str] = None
    rag_context: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None

class ChatResponse(BaseModel):
    content: str
    model: str
    usage: Dict[str, int]

@app.get("/healthz")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "llm"}

@app.get("/models")
async def get_models():
    """Получение списка доступных моделей"""
    return {"models": list(LLM_MODELS.keys())}

@app.post("/chat")
async def chat(request: ChatRequest):
    """Чат с LLM (поддержка стриминга)"""
    # Backpressure check с Semaphore
    if INFLIGHT_SEMAPHORE.locked():
        raise HTTPException(
            status_code=429,
            detail="Service overloaded, please retry later",
            headers={"Retry-After": "60"}
        )
    
    async with INFLIGHT_SEMAPHORE:
        try:
            # Проверка модели
            if request.model not in LLM_MODELS:
                raise HTTPException(status_code=400, detail=f"Model {request.model} not found")
            
            if request.stream:
                return StreamingResponse(
                    _stream_chat_response(request),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    }
                )
            else:
                # Синхронный ответ
                response = await _generate_chat_response(request)
                return response
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/complete", response_model=ChatResponse)
async def complete(request: CompleteRequest):
    """Завершение текста (не стриминг)"""
    # Backpressure check с Semaphore
    if INFLIGHT_SEMAPHORE.locked():
        raise HTTPException(
            status_code=429,
            detail="Service overloaded, please retry later",
            headers={"Retry-After": "60"}
        )
    
    async with INFLIGHT_SEMAPHORE:
        try:
            # Проверка модели
            if request.model not in LLM_MODELS:
                raise HTTPException(status_code=400, detail=f"Model {request.model} not found")
            
            # Генерация ответа
            response = await _generate_completion(request)
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Completion failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

async def _stream_chat_response(request: ChatRequest):
    """SSE стриминг ответа чата"""
    try:
        # Подготавливаем промпт
        prompt = _prepare_chat_prompt(request)
        
        # Генерируем ответ по частям
        full_response = ""
        async for chunk in _generate_text_chunks(prompt, request.model):
            full_response += chunk
            
            # Отправляем SSE chunk
            sse_data = {
                "content": chunk,
                "role": "assistant",
                "delta": True
            }
            yield f"data: {json.dumps(sse_data)}\n\n"
            await asyncio.sleep(0.01)  # Небольшая задержка для реалистичности
        
        # Финальный chunk
        final_data = {
            "content": "",
            "role": "assistant",
            "delta": False,
            "done": True
        }
        yield f"data: {json.dumps(final_data)}\n\n"
        
    except Exception as e:
        error_data = {
            "error": str(e),
            "done": True
        }
        yield f"data: {json.dumps(error_data)}\n\n"

async def _generate_chat_response(request: ChatRequest) -> ChatResponse:
    """Синхронный ответ чата"""
    prompt = _prepare_chat_prompt(request)
    response_parts = []
    async for chunk in _generate_text_chunks(prompt, request.model):
        response_parts.append(chunk)
    response_text = "".join(response_parts)
    
    return ChatResponse(
        content=response_text,
        model=request.model,
        usage={"prompt_tokens": len(prompt.split()), "completion_tokens": len(response_text.split())}
    )

async def _generate_completion(request: CompleteRequest) -> ChatResponse:
    """Генерация завершения текста"""
    prompt = _prepare_completion_prompt(request)
    response_parts = []
    async for chunk in _generate_text_chunks(prompt, request.model):
        response_parts.append(chunk)
    response_text = "".join(response_parts)
    
    return ChatResponse(
        content=response_text,
        model=request.model,
        usage={"prompt_tokens": len(prompt.split()), "completion_tokens": len(response_text.split())}
    )

def _prepare_chat_prompt(request: ChatRequest) -> str:
    """Подготовка промпта для чата"""
    prompt_parts = []
    
    if request.system_prompt:
        prompt_parts.append(f"System: {request.system_prompt}")
    
    if request.rag_context:
        prompt_parts.append(f"Context: {request.rag_context}")
    
    for message in request.messages:
        prompt_parts.append(f"{message.role.capitalize()}: {message.content}")
    
    return "\n\n".join(prompt_parts)

def _prepare_completion_prompt(request: CompleteRequest) -> str:
    """Подготовка промпта для завершения"""
    prompt_parts = []
    
    if request.system_prompt:
        prompt_parts.append(f"System: {request.system_prompt}")
    
    if request.rag_context:
        prompt_parts.append(f"Context: {request.rag_context}")
    
    prompt_parts.append(request.prompt)
    
    return "\n\n".join(prompt_parts)

async def _generate_text_chunks(prompt: str, model: str):
    """Генерация текста по частям (заглушка)"""
    # TODO: Реализовать реальную генерацию через OpenAI API или локальную модель
    sample_response = f"Это ответ от модели {model} на запрос: '{prompt[:50]}...'"
    
    # Имитируем стриминг
    words = sample_response.split()
    for i, word in enumerate(words):
        yield (word if i == 0 else " " + word)
        await asyncio.sleep(0.05)  # Асинхронная задержка для имитации генерации

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)