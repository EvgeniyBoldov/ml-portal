"""
Embedding Gateway - FastAPI service for embedding operations
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, validator
import uvicorn
from sentence_transformers import SentenceTransformer
import torch
import numpy as np

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Embedding Gateway",
    description="Gateway service for embedding operations",
    version="1.0.0"
)


class Priority(str, Enum):
    """Request priority"""
    LOW = "low"
    HIGH = "high"


class SingleEmbedRequest(BaseModel):
    """Request for embedding single text"""
    text: str = Field(..., min_length=1, max_length=10000)
    model: str = Field(default="all-MiniLM-L6-v2", description="Model alias")
    priority: Priority = Field(default=Priority.LOW, description="Request priority")


class BatchEmbedRequest(BaseModel):
    """Request for embedding multiple texts"""
    texts: List[str] = Field(..., min_items=1, max_items=1000)
    model: str = Field(default="all-MiniLM-L6-v2", description="Model alias")
    priority: Priority = Field(default=Priority.LOW, description="Request priority")


class QueryRequest(BaseModel):
    """Request for embedding query"""
    query: str = Field(..., min_length=1, max_length=10000)
    model: str = Field(default="default", description="Model alias")
    priority: Priority = Field(default=Priority.LOW, description="Request priority")


class EmbedResponse(BaseModel):
    """Response for embedding texts"""
    vectors: List[List[float]] = Field(..., description="Embedding vectors")
    dim: int = Field(..., description="Vector dimension")
    model_version: str = Field(..., description="Model version")
    usage: Optional[Dict[str, int]] = Field(None, description="Usage statistics")


class QueryResponse(BaseModel):
    """Response for embedding query"""
    vector: List[float] = Field(..., description="Query vector")
    dim: int = Field(..., description="Vector dimension")
    model_version: str = Field(..., description="Model version")
    usage: Optional[Dict[str, int]] = Field(None, description="Usage statistics")


class ModelInfo(BaseModel):
    """Model information"""
    name: str
    alias: str
    dimensions: int
    max_tokens: int
    version: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    models: List[str]


@dataclass
class ModelConfig:
    """Model configuration"""
    alias: str
    dimensions: int
    max_tokens: int
    version: str
    batch_size: int
    max_wait_ms: int
    parallelism: int
    path: str


class EmbeddingEngine:
    """Embedding engine for a specific model"""
    
    def __init__(self, config: ModelConfig):
        self.config = config
        self.batch_queue: List[EmbedRequest] = []
        self.batch_lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(config.parallelism)
        self.metrics = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "batch_size_avg": 0.0,
            "latency_p50": 0.0,
            "latency_p95": 0.0,
        }
        self.model = None
        self._load_model()
    
    async def embed_texts(self, texts: List[str], priority: Priority = Priority.LOW) -> List[List[float]]:
        """Embed texts using this model"""
        async with self.semaphore:
            start_time = time.time()
            
            try:
                # Simulate embedding (in production, call actual model)
                vectors = await self._call_model(texts)
                
                # Update metrics
                latency = time.time() - start_time
                self._update_metrics(latency, len(texts), success=True)
                
                return vectors
                
            except Exception as e:
                self._update_metrics(time.time() - start_time, len(texts), success=False)
                raise e
    
    def _load_model(self):
        """Load the actual model from configured path or alias."""
        try:
            # Prefer explicit configured path
            model_source = self.config.path or self.config.alias
            logger.info(f"Loading model: {model_source}")
            self.model = SentenceTransformer(model_source)
            logger.info(f"Model loaded successfully from {model_source}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            # Fallback to dummy model
            self.model = None
    
    def _get_model_name(self) -> str:
        """Deprecated: kept for compatibility, prefer config.path."""
        return self.config.path or self.config.alias
    
    async def _call_model(self, texts: List[str]) -> List[List[float]]:
        """Call the actual model"""
        if self.model is None:
            # Fallback to dummy vectors if model failed to load
            logger.warning("Model not loaded, returning dummy vectors")
            return [[0.1] * self.config.dimensions for _ in texts]
        
        try:
            # Run model inference in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None, 
                lambda: self.model.encode(texts, convert_to_tensor=False)
            )
            
            # Convert numpy arrays to lists
            return [embedding.tolist() for embedding in embeddings]
            
        except Exception as e:
            logger.error(f"Error in model inference: {e}")
            # Fallback to dummy vectors
            return [[0.1] * self.config.dimensions for _ in texts]
    
    def _update_metrics(self, latency: float, batch_size: int, success: bool):
        """Update metrics"""
        self.metrics["requests_total"] += 1
        if success:
            self.metrics["requests_success"] += 1
        else:
            self.metrics["requests_failed"] += 1
        
        # Update average batch size
        total_requests = self.metrics["requests_total"]
        current_avg = self.metrics["batch_size_avg"]
        self.metrics["batch_size_avg"] = (current_avg * (total_requests - 1) + batch_size) / total_requests
        
        # Update latency percentiles (simplified)
        self.metrics["latency_p50"] = latency
        self.metrics["latency_p95"] = latency * 1.5


class EmbeddingGateway:
    """Main embedding gateway"""
    
    def __init__(self):
        self.models: Dict[str, EmbeddingEngine] = {}
        self._load_models()
    
    def _load_models(self):
        """Load model configurations"""
        # Load from environment variables
        import os
        
        models_str = os.getenv("EMB_MODELS", "all-MiniLM-L6-v2")
        model_aliases = [m.strip() for m in models_str.split(",")]
        
        for alias in model_aliases:
            config = ModelConfig(
                alias=alias,
                dimensions=int(os.getenv(f"EMB_MODEL_{alias.upper().replace('-', '_')}_DIMENSIONS", "384")),
                max_tokens=int(os.getenv(f"EMB_MODEL_{alias.upper().replace('-', '_')}_MAX_TOKENS", "512")),
                version=os.getenv(f"EMB_MODEL_{alias.upper().replace('-', '_')}_VERSION", "1.0"),
                batch_size=int(os.getenv("EMB_BATCH_SIZE", "128")),
                max_wait_ms=int(os.getenv("EMB_MAX_WAIT_MS", "8")),
                parallelism=int(os.getenv(f"EMB_PARALLELISM_{alias.upper().replace('-', '_')}", "2")),
                path=os.getenv(f"EMB_MODEL_{alias.upper().replace('-', '_')}_PATH", f"/models/{alias}")
            )
            
            self.models[alias] = EmbeddingEngine(config)
            logger.info(f"Loaded model: {alias} with {config.dimensions} dimensions")
    
    def get_model(self, alias: str) -> EmbeddingEngine:
        """Get model by alias"""
        if alias not in self.models:
            raise HTTPException(status_code=404, detail=f"Model {alias} not found")
        return self.models[alias]
    
    def list_models(self) -> List[ModelInfo]:
        """List available models"""
        return [
            ModelInfo(
                name=engine.config.alias,
                alias=engine.config.alias,
                dimensions=engine.config.dimensions,
                max_tokens=engine.config.max_tokens,
                version=engine.config.version
            )
            for engine in self.models.values()
        ]


# Global gateway instance
gateway = EmbeddingGateway()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        models=list(gateway.models.keys())
    )


@app.get("/models", response_model=List[ModelInfo])
async def list_models():
    """List available models"""
    return gateway.list_models()


@app.post("/embed", response_model=EmbedResponse)
async def embed_single(request: SingleEmbedRequest):
    """Embed single text"""
    return await _embed_texts([request.text], request.model, request.priority)


@app.post("/embed/batch", response_model=EmbedResponse)
async def embed_batch(request: BatchEmbedRequest):
    """Embed multiple texts"""
    return await _embed_texts(request.texts, request.model, request.priority)


async def _embed_texts(texts: List[str], model_name: str, priority: Priority) -> EmbedResponse:
    """Common function for embedding texts"""
    # Get model
    model = gateway.get_model(model_name)
    
    # Check if texts exceed max tokens
    total_chars = sum(len(text) for text in texts)
    if total_chars > model.config.max_tokens * len(texts):
        raise HTTPException(status_code=400, detail="Texts exceed max tokens")
    
    # Embed texts
    vectors = await model.embed_texts(texts, priority)
    
    return EmbedResponse(
        vectors=vectors,
        dim=model.config.dimensions,
        model_version=model.config.version,
        usage={
            "prompt_tokens": total_chars,
            "total_tokens": total_chars
        }
    )


@app.post("/embed/query", response_model=QueryResponse)
async def embed_query(request: QueryRequest):
    """Embed single query"""
    try:
        # Validate request
        if len(request.query) > 10000:
            raise HTTPException(status_code=400, detail="Query too long (max 10000 chars)")
        
        # Get model
        model = gateway.get_model(request.model)
        
        # Check if query exceeds max tokens
        if len(request.query) > model.config.max_tokens:
            raise HTTPException(status_code=400, detail="Query exceeds max tokens")
        
        # Embed query
        vectors = await model.embed_texts([request.query], request.priority)
        
        return QueryResponse(
            vector=vectors[0],
            dim=model.config.dimensions,
            model_version=model.config.version,
            usage={
                "prompt_tokens": len(request.query),
                "total_tokens": len(request.query)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error embedding query: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/metrics")
async def get_metrics():
    """Get metrics for all models"""
    metrics = {}
    for alias, engine in gateway.models.items():
        metrics[alias] = engine.metrics
    return metrics


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )