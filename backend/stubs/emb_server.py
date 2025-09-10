import asyncio
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Embeddings Stub (in-backend)")

class EmbedRequest(BaseModel):
    # Match app.services.clients.embed_texts contract
    inputs: List[str]

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/embed")
async def embed(req: EmbedRequest):
    # Добавляем задержку 5 секунд
    await asyncio.sleep(5)
    
    def vec_for(_: str):
        # 8-dim demo vector; replace with real model later
        return [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    return {"vectors": [vec_for(x) for x in req.inputs]}
