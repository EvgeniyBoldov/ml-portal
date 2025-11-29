# Local Services (OCR, ASR, Reranker, Vision)

Этот документ описывает локальные сервисы, которые НЕ хранятся в таблице `models`, а конфигурируются через `settings.py`.

## Философия

- **В таблице models:** только LLM и Embedding (часто меняются, разные провайдеры)
- **Локальные контейнеры:** OCR, ASR, Reranker, Vision (стабильные, редко меняются)

Локальные сервисы реализуют **OpenAI-compatible API** для единообразия.

---

## 1. Reranker Service

### Назначение

Переранжирование результатов поиска по релевантности к запросу.  
Использует cross-encoder модели (BERT-based).

### API Endpoint

```
POST /v1/rerank
Content-Type: application/json

{
  "query": "What is machine learning?",
  "documents": [
    "Machine learning is a subset of AI...",
    "Python is a programming language...",
    "Deep learning uses neural networks..."
  ],
  "top_k": 10,  // optional
  "model": "cross-encoder/ms-marco-MiniLM-L-6-v2"  // optional
}
```

### Response

```json
{
  "results": [
    {
      "index": 0,
      "score": 0.95,
      "text": "Machine learning is a subset of AI...",
      "relevance_score": 0.95
    },
    {
      "index": 2,
      "score": 0.78,
      "text": "Deep learning uses neural networks...",
      "relevance_score": 0.78
    }
  ],
  "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
  "usage": {
    "total_tokens": 150
  }
}
```

### Примеры моделей

- `cross-encoder/ms-marco-MiniLM-L-6-v2` (fast, 80MB)
- `cross-encoder/ms-marco-MiniLM-L-12-v2` (better, 130MB)
- `BAAI/bge-reranker-base` (multilingual)
- `BAAI/bge-reranker-large` (best quality, slow)

### Docker Container

```dockerfile
# Dockerfile для reranker service
FROM python:3.11-slim

RUN pip install fastapi uvicorn sentence-transformers

WORKDIR /app
COPY reranker_service.py .

CMD ["uvicorn", "reranker_service:app", "--host", "0.0.0.0", "--port", "8002"]
```

### Python Implementation (reranker_service.py)

```python
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import CrossEncoder
from typing import List, Optional

app = FastAPI()

# Load model at startup
model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

class RerankRequest(BaseModel):
    query: str
    documents: List[str]
    top_k: Optional[int] = None
    model: Optional[str] = None

class RerankResult(BaseModel):
    index: int
    score: float
    text: str
    relevance_score: float

@app.post("/v1/rerank")
async def rerank(request: RerankRequest):
    # Create query-document pairs
    pairs = [[request.query, doc] for doc in request.documents]
    
    # Get scores
    scores = model.predict(pairs)
    
    # Sort by score (descending)
    results = [
        {"index": i, "score": float(score), "text": doc, "relevance_score": float(score)}
        for i, (doc, score) in enumerate(zip(request.documents, scores))
    ]
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # Apply top_k filter
    if request.top_k:
        results = results[:request.top_k]
    
    return {
        "results": results,
        "model": request.model or "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "usage": {"total_tokens": len(request.query.split()) + sum(len(d.split()) for d in request.documents)}
    }

@app.get("/health")
async def health():
    return {"status": "ok"}
```

### Configuration (settings.py)

```python
# Reranker service
RERANK_SERVICE_URL: str = Field(default="http://reranker:8002")
RERANK_MODEL: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_ENABLED: bool = Field(default=True)
```

### Usage in Code

```python
from app.providers.rerank_provider import get_rerank_provider
from app.core.config import get_settings

settings = get_settings()

reranker = get_rerank_provider(
    provider="local",
    base_url=settings.RERANK_SERVICE_URL,
    model=settings.RERANK_MODEL
)

# Rerank search results
ranked = await reranker.rerank(
    query="machine learning basics",
    documents=search_results,
    top_k=10
)

# Use ranked results
for doc in ranked:
    print(f"[{doc.score:.2f}] {doc.text[:100]}...")
```

---

## 2. OCR Service (Future)

```
POST /v1/ocr
Content-Type: multipart/form-data

file: <image/pdf>
language: en  // optional
```

Response:
```json
{
  "text": "Extracted text...",
  "blocks": [...],
  "confidence": 0.95
}
```

---

## 3. ASR Service (Future)

```
POST /v1/transcribe
Content-Type: multipart/form-data

file: <audio>
language: en  // optional
```

Response:
```json
{
  "text": "Transcribed text...",
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "Hello world"}
  ]
}
```

---

## Deployment (docker-compose.yml)

```yaml
services:
  reranker:
    build: ./infra/docker/reranker
    ports:
      - "8002:8002"
    environment:
      - MODEL_NAME=cross-encoder/ms-marco-MiniLM-L-6-v2
      - CACHE_DIR=/models
    volumes:
      - ./models_llm/reranker:/models
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## Health Checks

Все локальные сервисы должны иметь `/health` endpoint:

```
GET /health

Response:
{
  "status": "ok",
  "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
  "version": "1.0.0"
}
```

Backend периодически проверяет доступность (раз в 5 минут через Celery beat task).
