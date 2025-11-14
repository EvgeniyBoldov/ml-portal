"""
Embedding interfaces and implementations
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from uuid import UUID


@dataclass
class EmbeddingModelInfo:
    """Embedding model information"""
    alias: str
    version: str
    dimensions: int
    max_tokens: int
    description: str


class EmbeddingInterface(ABC):
    """Abstract embedding interface"""
    
    @abstractmethod
    def get_model_info(self) -> EmbeddingModelInfo:
        """Get model information"""
        pass
    
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed list of texts"""
        pass
    
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Embed single text"""
        pass


class MockEmbeddingService(EmbeddingInterface):
    """Mock embedding service for development"""
    
    def __init__(self, model_alias: str = "all-MiniLM-L6-v2"):
        self.model_alias = model_alias
        self.dimensions = 384 if "L6" in model_alias else 768
    
    def get_model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            alias=self.model_alias,
            version="1.0",
            dimensions=self.dimensions,
            max_tokens=512,
            description=f"Mock embedding model {self.model_alias}"
        )
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate mock embeddings"""
        import random
        random.seed(42)  # For deterministic results
        
        embeddings = []
        for text in texts:
            # Generate deterministic mock embedding based on text hash
            text_hash = hash(text) % (2**32)
            random.seed(text_hash)
            embedding = [random.uniform(-1, 1) for _ in range(self.dimensions)]
            embeddings.append(embedding)
        
        return embeddings
    
    def embed_text(self, text: str) -> List[float]:
        """Embed single text"""
        return self.embed_texts([text])[0]


class EmbeddingServiceFactory:
    """Factory for embedding services"""
    
    _services = {}
    
    @classmethod
    def get_service(cls, model_alias: str) -> EmbeddingInterface:
        """Get embedding service for model"""
        if model_alias not in cls._services:
            cls._services[model_alias] = MockEmbeddingService(model_alias)
        return cls._services[model_alias]
    
    @classmethod
    def get_available_models(cls) -> List[str]:
        """Get list of available models"""
        return ["all-MiniLM-L6-v2", "all-MiniLM-L12-v2", "all-mpnet-base-v2"]
    
    @classmethod
    def get_model_info(cls, model_alias: str) -> EmbeddingModelInfo:
        """Get model information"""
        service = cls.get_service(model_alias)
        return service.get_model_info()