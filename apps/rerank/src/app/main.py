"""
Rerank Service - FastAPI service for CrossEncoder operations
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder
import os
import json
import logging
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rerank")

app = FastAPI(title="Rerank Service")

MODEL_PATH = os.getenv("RERANK_MODEL_PATH", "/models_llm/cross-encoder--ms-marco-MiniLM-L-6-v2")
MODEL_ALIAS = os.getenv("RERANK_MODEL_ALIAS", "cross-encoder-ms-marco-MiniLM-L-6-v2")
MODEL_VERSION = os.getenv("RERANK_MODEL_VERSION", "1.0")
MODEL_MAX_TOKENS = int(os.getenv("RERANK_MODEL_MAX_TOKENS", "512"))

model = None
manifest_data: Dict[str, Any] = {}

@app.on_event("startup")
async def load_model():
    global model, manifest_data
    try:
        logger.info(f"Loading model from {MODEL_PATH}")
        # Check if path exists
        if not os.path.exists(MODEL_PATH):
            logger.warning(f"Model path {MODEL_PATH} does not exist. Reranker will not work.")
            return
            
        model = CrossEncoder(MODEL_PATH)
        manifest_path = os.path.join(MODEL_PATH, "manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f) or {}
            except Exception as manifest_error:
                logger.warning(f"Failed to read manifest: {manifest_error}")
        logger.info("Model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        model = None

class RerankRequest(BaseModel):
    query: str
    documents: List[str]
    top_k: int = Field(default=5, ge=1)

class RerankResult(BaseModel):
    index: int
    score: float
    document: str

class RerankResponse(BaseModel):
    results: List[RerankResult]


class ModelInfo(BaseModel):
    name: str
    alias: str
    dimensions: int
    max_tokens: int
    version: str
    modality: str
    description: str

@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded or not found")
    
    if not request.documents:
        return {"results": []}

    try:
        pairs = [[request.query, doc] for doc in request.documents]
        scores = model.predict(pairs)
        
        # Combine with indices
        results = []
        for i, score in enumerate(scores):
            results.append({
                "index": i,
                "score": float(score),
                "document": request.documents[i]
            })
        
        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        
        # Top K
        results = results[:request.top_k]
        
        return {"results": results}
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.get("/models", response_model=List[ModelInfo])
async def list_models():
    return [
        ModelInfo(
            name=str(manifest_data.get("model") or MODEL_ALIAS),
            alias=MODEL_ALIAS,
            dimensions=0,
            max_tokens=MODEL_MAX_TOKENS,
            version=str(manifest_data.get("version") or MODEL_VERSION),
            modality=str(manifest_data.get("modality") or "rerank"),
            description=str(manifest_data.get("description") or f"Reranker model {MODEL_ALIAS}"),
        )
    ]
