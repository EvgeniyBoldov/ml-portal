"""
Embedding Service - Development Version
Заглушка для разработки без ML зависимостей
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Embedding Service (Dev)",
    description="Заглушка для разработки без ML зависимостей",
    version="0.1.0"
)

class EmbeddingRequest(BaseModel):
    text: str
    model: str = "sentence-transformers/all-MiniLM-L6-v2"

class EmbeddingResponse(BaseModel):
    embedding: List[float]
    model: str
    dimensions: int

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "service": "embedding-dev"}

@app.post("/embed", response_model=EmbeddingResponse)
async def create_embedding(request: EmbeddingRequest):
    """Создание эмбеддинга (заглушка)"""
    logger.info(f"Creating embedding for text: {request.text[:50]}...")
    
    # Заглушка - возвращаем случайный вектор
    import random
    random.seed(hash(request.text) % 2**32)  # Детерминированный "случайный" вектор
    embedding = [random.random() for _ in range(384)]  # 384 измерения для all-MiniLM-L6-v2
    
    return EmbeddingResponse(
        embedding=embedding,
        model=request.model,
        dimensions=384
    )

@app.get("/models")
async def list_models():
    """Список доступных моделей"""
    return {
        "models": [
            {
                "name": "sentence-transformers/all-MiniLM-L6-v2",
                "dimensions": 384,
                "max_tokens": 256
            }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
