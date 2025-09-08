import os
from typing import List, Dict, Any
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

REAL_URL = os.getenv("REAL_LLM_URL", "").rstrip("/")

app = FastAPI(title="LLM Proxy")

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]

@app.get("/healthz")
def healthz():
    return {"status": "ok", "mode": "proxy", "target": REAL_URL}

@app.post("/chat")
async def chat(req: ChatRequest):
    if not REAL_URL:
        raise HTTPException(500, "REAL_LLM_URL is not set")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{REAL_URL}/chat", json=req.model_dump())
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Upstream error: {e}")
