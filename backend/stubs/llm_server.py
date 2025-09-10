import asyncio
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

app = FastAPI(title="LLM Stub (in-backend)")

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = None

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/v1/chat/completions")
async def chat(req: ChatRequest):
    # Добавляем задержку 5 секунд
    await asyncio.sleep(5)
    
    last_user = next((m.get("content","") for m in reversed(req.messages) if m.get("role") == "user"), "")
    return {"choices":[{"message":{"role":"assistant","content":f"(stub) You said: {last_user}"}}]}
