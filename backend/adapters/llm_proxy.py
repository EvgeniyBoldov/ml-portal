"""
LLM Proxy - заглушка для тестирования
Имитирует работу реального LLM сервиса
"""
import os
import time
import random
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="LLM Proxy", version="0.1.0")

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 1000

class ChatResponse(BaseModel):
    content: str
    usage: Dict[str, int]

# Заглушка для ответов
MOCK_RESPONSES = [
    "Привет! Как дела? Чем могу помочь?",
    "Интересный вопрос! Давайте разберем его подробнее.",
    "Понимаю вашу проблему. Вот что я думаю по этому поводу...",
    "Отличная идея! Это действительно может сработать.",
    "Хм, это сложный вопрос. Нужно подумать...",
    "Я готов помочь вам с этим вопросом!",
    "Спасибо за вопрос! Вот мой ответ...",
    "Это очень важная тема. Давайте обсудим её детально.",
]

def generate_mock_response(messages: List[ChatMessage]) -> str:
    """Генерирует заглушку ответа на основе сообщений"""
    if not messages:
        return "Привет! Как дела?"
    
    last_message = messages[-1].content.lower()
    
    # Простые паттерны для более реалистичных ответов
    if "привет" in last_message or "hello" in last_message:
        return "Привет! Как дела? Чем могу помочь?"
    elif "как дела" in last_message:
        return "У меня все отлично! А у вас как дела?"
    elif "спасибо" in last_message:
        return "Пожалуйста! Рад был помочь!"
    elif "?" in last_message:
        return "Интересный вопрос! Вот что я думаю по этому поводу..."
    else:
        return random.choice(MOCK_RESPONSES)

@app.get("/healthz")
async def healthz():
    """Health check endpoint"""
    return {"status": "ok", "mode": "mock", "target": "localhost"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint - заглушка"""
    try:
        # Имитируем задержку обработки
        delay = random.uniform(0.5, 2.0)
        time.sleep(delay)
        
        # Генерируем ответ
        content = generate_mock_response(request.messages)
        
        # Имитируем токены
        token_count = len(content.split()) + random.randint(10, 50)
        
        return ChatResponse(
            content=content,
            usage={
                "prompt_tokens": sum(len(msg.content.split()) for msg in request.messages),
                "completion_tokens": token_count,
                "total_tokens": token_count + sum(len(msg.content.split()) for msg in request.messages)
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mock LLM error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
