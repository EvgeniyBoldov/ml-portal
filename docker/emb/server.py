from typing import List, Union
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Embeddings Stub")

class EmbedRequest(BaseModel):
    input: Union[str, List[str]]

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/embed")
def embed(req: EmbedRequest):
    def vec_for(_: str):
        return [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    if isinstance(req.input, list):
        return {"data": [vec_for(x) for x in req.input]}
    else:
        return {"data": vec_for(req.input)}
