"""
LLM Service - Development Version
Заглушка для разработки без ML зависимостей
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LLM Service (Dev)",
    description="Заглушка для разработки без ML зависимостей",
    version="0.1.0"
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: Optional[int] = None

class ChatResponse(BaseModel):
    message: ChatMessage
    model: str
    usage: dict

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "service": "llm-dev"}

@app.post("/chat", response_model=ChatResponse)
async def chat_completion(request: ChatRequest):
    """Завершение чата (заглушка)"""
    logger.info(f"Processing chat with {len(request.messages)} messages")
    
    # Заглушка - возвращаем простой ответ
    last_message = request.messages[-1].content if request.messages else "Hello!"
    
    response_content = f"[DEV RESPONSE] I received your message: '{last_message}'. This is a development stub response."
    
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            content=response_content
        ),
        model=request.model,
        usage={
            "prompt_tokens": sum(len(msg.content) for msg in request.messages),
            "completion_tokens": len(response_content.split()),
            "total_tokens": sum(len(msg.content) for msg in request.messages) + len(response_content.split())
        }
    )

@app.get("/models")
async def list_models():
    """Список доступных моделей"""
    return {
        "models": [
            {
                "name": "gpt-3.5-turbo",
                "type": "chat",
                "max_tokens": 4096
            },
            {
                "name": "gpt-4",
                "type": "chat", 
                "max_tokens": 8192
            }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
