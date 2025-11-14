"""
Embedding service factory and implementations
"""
from typing import List, Dict, Any
from dataclasses import dataclass
import os
import logging
from app.adapters.interfaces.embeddings import EmbeddingInterface, EmbeddingModelInfo
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Model information"""
    alias: str
    version: str
    dimensions: int


class LocalSentenceTransformerProvider(EmbeddingInterface):
    """Real embedding service using sentence-transformers"""
    
    def __init__(self, model_alias: str = "all-MiniLM-L6-v2"):
        self._model_alias = model_alias
        self._model = None
        self._model_info = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of the model"""
        if not self._initialized:
            try:
                from sentence_transformers import SentenceTransformer
                
                # Map aliases to actual model names
                model_mapping = {
                    "all-MiniLM-L6-v2": "all-MiniLM-L6-v2",
                    "all-MiniLM-L12-v2": "all-MiniLM-L12-v2", 
                    "all-mpnet-base-v2": "all-mpnet-base-v2"
                }
                
                actual_model_name = model_mapping.get(self._model_alias, self._model_alias)
                logger.info(f"Loading sentence-transformers model: {actual_model_name}")
                
                # Resolve local model path from env or MODELS_ROOT
                settings = get_settings()
                env_key = f"EMB_MODEL_{actual_model_name.replace('-', '_')}_PATH"
                local_model_path = os.getenv(env_key)
                if not local_model_path:
                    models_root = getattr(settings, 'MODELS_ROOT', '/models_llm')
                    local_model_path = f"{models_root}/sentence-transformers--{actual_model_name}"

                # Check if local model exists
                if os.path.exists(local_model_path):
                    logger.info(f"Using local model from: {local_model_path}")
                    self._model = SentenceTransformer(local_model_path)
                else:
                    # Offline mode: do not attempt network downloads
                    if getattr(settings, 'EMB_OFFLINE', True):
                        logger.error(f"Local model not found and offline mode is enabled: {local_model_path}")
                        raise RuntimeError(f"Model path not found in offline mode: {local_model_path}")
                    # Fallback to downloading with cache directory (online only)
                    cache_dir = getattr(settings, 'EMB_CACHE_DIR', '/tmp/sentence_transformers')
                    logger.info(f"Downloading model to cache: {cache_dir}")
                    self._model = SentenceTransformer(actual_model_name, cache_folder=cache_dir)
                
                # Get model info
                self._model_info = EmbeddingModelInfo(
                    alias=self._model_alias,
                    version=getattr(self._model, 'model_version', '1.0'),
                    dimensions=self._model.get_sentence_embedding_dimension(),
                    max_tokens=512,  # Default for MiniLM models
                    description=f"SentenceTransformer model {actual_model_name}"
                )
                
                self._initialized = True
                logger.info(f"Successfully loaded model {self._model_alias} with {self._model_info.dimensions} dimensions")
                
            except ImportError:
                logger.error("sentence-transformers not installed. Please install: pip install sentence-transformers")
                raise RuntimeError("sentence-transformers package is required for LocalSentenceTransformerProvider")
            except Exception as e:
                logger.error(f"Failed to load model {self._model_alias}: {e}")
                raise
    
    def get_model_info(self) -> EmbeddingModelInfo:
        """Get model information"""
        self._ensure_initialized()
        return self._model_info
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed list of texts"""
        self._ensure_initialized()
        
        if not texts:
            return []
        
        try:
            # Use sentence-transformers to encode texts
            embeddings = self._model.encode(texts, convert_to_tensor=False)
            
            # Convert to list of lists if needed
            if hasattr(embeddings, 'tolist'):
                embeddings = embeddings.tolist()
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to embed texts: {e}")
            raise
    
    def embed_text(self, text: str) -> List[float]:
        """Embed single text"""
        return self.embed_texts([text])[0]


class MockEmbeddingService(EmbeddingInterface):
    """Mock embedding service for development"""
    
    def __init__(self, model_alias: str = "all-MiniLM-L6-v2"):
        self._model_alias = model_alias
        self._version = "v1"
        self._dimensions = 384  # Standard MiniLM dimensions
    
    def get_model_info(self) -> EmbeddingModelInfo:
        """Get model information"""
        return EmbeddingModelInfo(
            alias=self._model_alias,
            version=self._version,
            dimensions=self._dimensions,
            max_tokens=512,
            description=f"Mock embedding model {self._model_alias}"
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
            embedding = [random.uniform(-1, 1) for _ in range(self._dimensions)]
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
        """Get embedding service by alias"""
        settings = get_settings()
        
        # Use mock if configured
        if getattr(settings, 'EMB_USE_MOCK', False):
            if model_alias not in cls._services:
                cls._services[model_alias] = MockEmbeddingService(model_alias)
            return cls._services[model_alias]
        
        # Use real provider for all-MiniLM-L6-v2
        if model_alias == "all-MiniLM-L6-v2":
            if model_alias not in cls._services:
                cls._services[model_alias] = LocalSentenceTransformerProvider(model_alias)
            return cls._services[model_alias]
        
        # Fallback to mock for other models
        if model_alias not in cls._services:
            cls._services[model_alias] = MockEmbeddingService(model_alias)
        return cls._services[model_alias]
    
    @classmethod
    def list_available_models(cls) -> List[str]:
        """List available model aliases"""
        return ["all-MiniLM-L6-v2", "all-MiniLM-L12-v2", "all-mpnet-base-v2"]
