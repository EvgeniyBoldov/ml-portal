import asyncio
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

app = FastAPI(title="LLM Stub (in-backend)")

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = None
    use_rag: Optional[bool] = False

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/v1/chat/completions")
async def chat(req: ChatRequest):
    # Добавляем задержку 5 секунд
    await asyncio.sleep(5)
    
    last_user = next((m.get("content","") for m in reversed(req.messages) if m.get("role") == "user"), "")
    
    # Создаем JSON с информацией о запросе
    request_info = {
        "user_message": last_user,
        "use_rag": req.use_rag,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "messages_count": len(req.messages)
    }
    
    response_text = f"Это тестовый ответ на ваш запрос \"{last_user}\", вот полный json запроса: {json.dumps(request_info, ensure_ascii=False, indent=2)}"
    
    # Разбиваем ответ на части для потоковой передачи
    chunks = [response_text[i:i+50] for i in range(0, len(response_text), 50)]
    
    async def generate():
        for i, chunk in enumerate(chunks):
            chunk_data = {
                "id": f"chatcmpl-{i}",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": "gpt-3.5-turbo",
                "choices": [{
                    "index": 0,
                    "delta": {"content": chunk},
                    "finish_reason": None
                }]
            }
            
            # Добавляем финальный чанк
            if i == len(chunks) - 1:
                chunk_data["choices"][0]["finish_reason"] = "stop"
            
            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.1)  # Небольшая задержка между чанками
        
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(generate(), media_type="text/plain")
