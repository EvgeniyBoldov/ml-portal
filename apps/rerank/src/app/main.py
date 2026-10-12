"""
Rerank Service - FastAPI service for CrossEncoder operations
"""
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder
import os
import json
import logging
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rerank")

app = FastAPI(title="Rerank Service")

MODEL_PATH = os.getenv("RERANK_MODEL_PATH", "/models_llm/cross-encoder--ms-marco-MiniLM-L-6-v2")
MODEL_ALIAS = os.getenv("RERANK_MODEL_ALIAS", "cross-encoder-ms-marco-MiniLM-L-6-v2")
MODEL_VERSION = os.getenv("RERANK_MODEL_VERSION", "1.0")
MODEL_MAX_TOKENS = int(os.getenv("RERANK_MODEL_MAX_TOKENS", "512"))
MODEL_BATCH_SIZE = max(1, int(os.getenv("RERANK_BATCH_SIZE", "4")))
REQUEST_TIMEOUT_SECONDS = max(1, float(os.getenv("RERANK_REQUEST_TIMEOUT_SECONDS", "120")))
inference_gate = asyncio.Semaphore(1)

model = None
manifest_data: Dict[str, Any] = {}
hf_metadata: Dict[str, Any] = {}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists() and path.is_file():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to read {path.name}: {e}")
    return {}


def _load_hf_metadata(model_path: str) -> Dict[str, Any]:
    path = Path(model_path)
    config = _read_json(path / "config.json")
    tokenizer_config = _read_json(path / "tokenizer_config.json")

    architectures = config.get("architectures")
    if not isinstance(architectures, list):
        architectures = []

    important_params: Dict[str, Any] = {
        "architectures": architectures,
        "model_type": config.get("model_type"),
        "num_labels": config.get("num_labels"),
        "classifier_dropout": config.get("classifier_dropout"),
        "tokenizer_class": tokenizer_config.get("tokenizer_class"),
        "max_position_embeddings": config.get("max_position_embeddings"),
        "model_max_length": tokenizer_config.get("model_max_length"),
    }
    important_params = {k: v for k, v in important_params.items() if v not in (None, "", [], {})}

    max_tokens = config.get("max_position_embeddings") or tokenizer_config.get("model_max_length")
    if not isinstance(max_tokens, (int, float)):
        max_tokens = None

    return {
        "name": str(config.get("_name_or_path") or tokenizer_config.get("name_or_path") or path.name),
        "version": str(config.get("transformers_version") or ""),
        "modality": "reranker",
        "max_tokens": int(max_tokens) if isinstance(max_tokens, (int, float)) else None,
        "important_params": important_params,
    }

@app.on_event("startup")
async def load_model():
    global model, manifest_data, hf_metadata
    try:
        logger.info(f"Loading model from {MODEL_PATH}")
        # Check if path exists
        if not os.path.exists(MODEL_PATH):
            logger.warning(f"Model path {MODEL_PATH} does not exist. Reranker will not work.")
            return
            
        model = CrossEncoder(MODEL_PATH, max_length=MODEL_MAX_TOKENS)
        hf_metadata = _load_hf_metadata(MODEL_PATH)
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
    important_params: Dict[str, Any]

@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest, http_request: Request):
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded or not found")
    
    if not request.documents:
        return {"results": []}

    try:
        try:
            timeout = max(0.001, float(http_request.headers.get("X-Request-Timeout-Seconds", REQUEST_TIMEOUT_SECONDS)))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid request timeout")
        deadline = time.monotonic() + timeout
        pairs = [[request.query, doc] for doc in request.documents]
        # Similar lengths share a batch, reducing padding without dropping
        # candidates. Original indices are restored before ranking the scores.
        order = sorted(range(len(pairs)), key=lambda index: len(request.documents[index]))
        scores = [0.0] * len(pairs)
        async def check_request():
            if await http_request.is_disconnected():
                raise HTTPException(status_code=499, detail="Client disconnected")
            if time.monotonic() >= deadline:
                raise HTTPException(status_code=504, detail="Rerank request timed out")
        # Serialize model inference while leaving the event loop responsive.
        # Cancellation/deadlines are checked between bounded CPU batches.
        await check_request()
        try:
            await asyncio.wait_for(inference_gate.acquire(), timeout=timeout)
        except TimeoutError:
            raise HTTPException(status_code=504, detail="Rerank queue timed out")
        try:
            for start in range(0, len(order), MODEL_BATCH_SIZE):
                await check_request()
                indices = order[start:start + MODEL_BATCH_SIZE]
                batch_scores = await asyncio.to_thread(model.predict,
                    [pairs[index] for index in indices], batch_size=MODEL_BATCH_SIZE, show_progress_bar=False)
                await check_request()
                for index, score in zip(indices, batch_scores):
                    scores[index] = float(score)
        finally:
            inference_gate.release()
        
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
    except HTTPException:
        raise
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
            name=str(hf_metadata.get("name") or manifest_data.get("model") or MODEL_ALIAS),
            alias=MODEL_ALIAS,
            dimensions=0,
            max_tokens=min(int(hf_metadata.get("max_tokens") or MODEL_MAX_TOKENS), MODEL_MAX_TOKENS),
            version=str(hf_metadata.get("version") or manifest_data.get("version") or MODEL_VERSION),
            modality=str(hf_metadata.get("modality") or manifest_data.get("modality") or "rerank"),
            description=str(manifest_data.get("description") or f"Reranker model {MODEL_ALIAS}"),
            important_params=hf_metadata.get("important_params") or {},
        )
    ]


@app.get("/description", response_model=ModelInfo)
async def description():
    models = await list_models()
    if not models:
        raise HTTPException(status_code=503, detail="No models loaded")
    return models[0]
