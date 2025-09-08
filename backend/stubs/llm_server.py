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
def chat(req: ChatRequest):
    last_user = next((m.get("content","") for m in reversed(req.messages) if m.get("role") == "user"), "")
    return {"choices":[{"message":{"role":"assistant","content":f"(stub) You said: {last_user}"}}]}
