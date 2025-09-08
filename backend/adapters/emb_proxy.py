import os
from typing import List, Union
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

REAL_URL = os.getenv("REAL_EMBEDDINGS_URL", "").rstrip("/")

app = FastAPI(title="Embeddings Proxy")

class EmbedRequest(BaseModel):
    input: Union[str, List[str]]

@app.get("/healthz")
def healthz():
    return {"status": "ok", "mode": "proxy", "target": REAL_URL}

@app.post("/embed")
async def embed(req: EmbedRequest):
    if not REAL_URL:
        raise HTTPException(500, "REAL_EMBEDDINGS_URL is not set")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{REAL_URL}/embed", json=req.model_dump())
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Upstream error: {e}")
