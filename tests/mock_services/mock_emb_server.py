"""
Mock Embedding Server для E2E тестов
Имитирует ответы embedding сервиса
"""
import json
import time
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
import uvicorn

app = FastAPI(title="Mock Embedding Server")

class EmbeddingRequest(BaseModel):
    texts: List[str]
    model: str = "all-MiniLM-L6-v2"

class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    dimensions: int

def generate_mock_embedding(text: str, dimensions: int = 384) -> List[float]:
    """Генерирует детерминированное embedding на основе текста"""
    # Используем hash текста для детерминированности
    seed = sum(ord(c) for c in text) % 1000
    np.random.seed(seed)
    
    # Генерируем нормализованный вектор
    embedding = np.random.normal(0, 1, dimensions)
    embedding = embedding / np.linalg.norm(embedding)
    
    return embedding.tolist()

@app.post("/embed")
async def embed_texts(request: EmbeddingRequest):
    """Основной endpoint для получения embeddings"""
    embeddings = []
    dimensions = 384  # Default для MiniLM
    
    if "multilingual" in request.model:
        dimensions = 768
    elif "bge-large" in request.model:
        dimensions = 1024
    
    for text in request.texts:
        embedding = generate_mock_embedding(text, dimensions)
        embeddings.append(embedding)
    
    # Small delay to simulate processing
    await asyncio.sleep(0.005)
    
    return EmbeddingResponse(
        embeddings=embeddings,
        model=request.model,
        dimensions=dimensions
    ).model_dump()

@app.post("/embed/batch")
async def embed_batch(request: EmbeddingRequest):
    """Batch embedding endpoint"""
    return await embed_texts(request)

@app.get("/models")
async def list_models():
    """Список доступных моделей"""
    return {
        "models": [
            {
                "id": "all-MiniLM-L6-v2",
                "dimensions": 384,
                "max_length": 512
            },
            {
                "id": "multilingual-e5-small",
                "dimensions": 768,
                "max_length": 512
            },
            {
                "id": "bge-large-en",
                "dimensions": 1024,
                "max_length": 512
            }
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "mock-emb"}

if __name__ == "__main__":
    import asyncio
    uvicorn.run(app, host="0.0.0.0", port=8001)
