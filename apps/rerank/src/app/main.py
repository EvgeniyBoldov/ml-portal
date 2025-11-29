"""
Rerank Service - FastAPI service for CrossEncoder operations
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder
import os
import logging
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rerank")

app = FastAPI(title="Rerank Service")

MODEL_PATH = os.getenv("RERANK_MODEL_PATH", "/models_llm/cross-encoder--ms-marco-MiniLM-L-6-v2")

model = None

@app.on_event("startup")
async def load_model():
    global model
    try:
        logger.info(f"Loading model from {MODEL_PATH}")
        # Check if path exists
        if not os.path.exists(MODEL_PATH):
            logger.warning(f"Model path {MODEL_PATH} does not exist. Reranker will not work.")
            return
            
        model = CrossEncoder(MODEL_PATH)
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
