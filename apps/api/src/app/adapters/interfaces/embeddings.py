"""
Embedding interfaces.
"""
from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass


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
