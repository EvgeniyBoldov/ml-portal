from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any

app = FastAPI(title="LLM Stub (in-backend)")

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/chat")
def chat(req: ChatRequest):
    last_user = next((m.get("content","") for m in reversed(req.messages) if m.get("role") == "user"), "")
    return {"choices":[{"message":{"role":"assistant","content":f"(stub) You said: {last_user}"}}]}
