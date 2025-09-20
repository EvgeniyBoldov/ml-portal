"""
EMB (Embedding Service) - FastAPI приложение
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import asyncio
import json
import time
import logging
from contextlib import asynccontextmanager
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные для backpressure
MAX_INFLIGHT = int(os.getenv("MAX_INFLIGHT", "100"))
# Используем Semaphore для thread-safe backpressure
INFLIGHT_SEMAPHORE = asyncio.Semaphore(MAX_INFLIGHT)

# Модели (заглушка для демонстрации)
EMBEDDING_MODELS = {
    "minilm": {
        "alias": "minilm",
        "hf_id": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "default",
        "dim": 384,
        "normalize": True
    }
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка ресурсов"""
    # Инициализация моделей
    logger.info("Initializing embedding models...")
    # TODO: Загрузить модели
    yield
    # Очистка
    logger.info("Shutting down embedding service...")

app = FastAPI(
    title="EMB Service",
    description="Embedding Service for ML Portal",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:3000", "http://localhost:8080", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class EmbedRequest(BaseModel):
    texts: List[str]
    model: str = "minilm"
    normalize: bool = True
    batch_size: int = 64
    batch_latency_ms: int = 20

class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    dim: int
    took_ms: int

class ModelInfo(BaseModel):
    alias: str
    hf_id: str
    revision: str
    dim: int
    normalize: bool

@app.get("/healthz")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "emb"}

@app.get("/models", response_model=List[ModelInfo])
async def get_models():
    """Получение списка доступных моделей"""
    return [ModelInfo(**model) for model in EMBEDDING_MODELS.values()]

@app.post("/embed", response_model=EmbedResponse)
async def embed_texts(request: EmbedRequest):
    """Получение эмбеддингов для текстов"""
    # Backpressure check с Semaphore
    if INFLIGHT_SEMAPHORE.locked():
        raise HTTPException(
            status_code=429,
            detail="Service overloaded, please retry later",
            headers={"Retry-After": "60"}
        )
    
    async with INFLIGHT_SEMAPHORE:
        start_time = time.time()
        
        try:
            # Проверка модели
            if request.model not in EMBEDDING_MODELS:
                raise HTTPException(status_code=400, detail=f"Model {request.model} not found")
            
            model_info = EMBEDDING_MODELS[request.model]
            
            # Микробатчинг
            embeddings = []
            for i in range(0, len(request.texts), request.batch_size):
                batch_texts = request.texts[i:i + request.batch_size]
                
                # Задержка для накопления батча
                if i > 0 and request.batch_latency_ms > 0:
                    await asyncio.sleep(request.batch_latency_ms / 1000.0)
                
                # Получение эмбеддингов (заглушка)
                batch_embeddings = await _get_embeddings(batch_texts, model_info)
                embeddings.extend(batch_embeddings)
            
            # Нормализация если требуется
            if request.normalize:
                embeddings = _normalize_embeddings(embeddings)
            
            took_ms = int((time.time() - start_time) * 1000)
        
            return EmbedResponse(
                embeddings=embeddings,
                model=request.model,
                dim=model_info["dim"],
                took_ms=took_ms
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

async def _get_embeddings(texts: List[str], model_info: Dict[str, Any]) -> List[List[float]]:
    """Получение эмбеддингов (заглушка)"""
    # TODO: Реализовать реальное получение эмбеддингов
    # Пока возвращаем случайные векторы нужной размерности
    import random
    dim = model_info["dim"]
    return [[random.random() for _ in range(dim)] for _ in texts]

def _normalize_embeddings(embeddings: List[List[float]]) -> List[List[float]]:
    """Нормализация векторов"""
    import math
    
    normalized = []
    for embedding in embeddings:
        # L2 нормализация
        norm = math.sqrt(sum(x * x for x in embedding))
        if norm > 0:
            normalized.append([x / norm for x in embedding])
        else:
            normalized.append(embedding)
    
    return normalized

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)