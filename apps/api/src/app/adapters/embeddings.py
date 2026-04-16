"""
Embedding service factory and implementations

Supports:
- Local SentenceTransformer models
- OpenAI API (text-embedding-3-large, etc.)
- Local embedding service (HTTP API)
- Mock for testing
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import os
from app.core.logging import get_logger
import httpx
from app.adapters.interfaces.embeddings import EmbeddingInterface, EmbeddingModelInfo
from app.core.config import get_settings

logger = get_logger(__name__)


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


class OpenAIEmbeddingProvider(EmbeddingInterface):
    """OpenAI API embedding provider"""
    
    # Model dimensions mapping
    MODEL_DIMENSIONS = {
        "text-embedding-3-large": 3072,
        "text-embedding-3-small": 1536,
        "text-embedding-ada-002": 1536,
    }
    
    def __init__(
        self, 
        model_alias: str,
        provider_model_name: str,
        base_url: str,
        api_key: Optional[str] = None,
        dimensions: Optional[int] = None
    ):
        self._model_alias = model_alias
        self._provider_model_name = provider_model_name
        self._base_url = base_url.rstrip('/')
        self._api_key = api_key
        self._dimensions = dimensions or self.MODEL_DIMENSIONS.get(provider_model_name, 1536)
        self._version = "1.0"
        
    def get_model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            alias=self._model_alias,
            version=self._version,
            dimensions=self._dimensions,
            max_tokens=8191,
            description=f"OpenAI {self._provider_model_name}"
        )
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed texts via OpenAI API"""
        if not texts:
            return []
        
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        
        payload = {
            "input": texts,
            "model": self._provider_model_name,
        }
        
        # Add dimensions if model supports it
        if self._provider_model_name.startswith("text-embedding-3"):
            payload["dimensions"] = self._dimensions
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self._base_url}/embeddings",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                # Extract embeddings from response
                embeddings = [item["embedding"] for item in data["data"]]
                return embeddings
                
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"OpenAI embedding failed: {e.response.text}")
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise
    
    def embed_text(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]


class LocalEmbeddingServiceProvider(EmbeddingInterface):
    """Local embedding service via HTTP API (e.g., emb container)"""
    
    def __init__(
        self,
        model_alias: str,
        provider_model_name: str,
        base_url: str,
        dimensions: int = 384
    ):
        self._model_alias = model_alias
        self._provider_model_name = provider_model_name
        self._base_url = base_url.rstrip('/')
        self._dimensions = dimensions
        self._version = "1.0"
        self._model_info: Optional[EmbeddingModelInfo] = None
    
    def _fetch_model_info(self) -> EmbeddingModelInfo:
        """Fetch model info from service"""
        if self._model_info:
            return self._model_info
            
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self._base_url}/info")
                if response.status_code == 200:
                    data = response.json()
                    self._dimensions = data.get("dimensions", self._dimensions)
                    self._version = data.get("version", self._version)
        except Exception as e:
            logger.warning(f"Could not fetch model info from {self._base_url}: {e}")
        
        self._model_info = EmbeddingModelInfo(
            alias=self._model_alias,
            version=self._version,
            dimensions=self._dimensions,
            max_tokens=512,
            description=f"Local embedding service {self._provider_model_name}"
        )
        return self._model_info
    
    def get_model_info(self) -> EmbeddingModelInfo:
        return self._fetch_model_info()
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed texts via local HTTP service
        
        Emb service expects {"text": "string"} and returns {"vectors": [[...]]}
        We batch by calling once per text.
        """
        if not texts:
            return []
        
        try:
            embeddings = []
            with httpx.Client(timeout=30.0) as client:
                for text in texts:
                    response = client.post(
                        f"{self._base_url}/embed",
                        json={"text": text}
                    )
                    response.raise_for_status()
                    data = response.json()
                    vectors = data.get("vectors", [[]])
                    if vectors:
                        embeddings.append(vectors[0])
                    else:
                        embeddings.append([])
            return embeddings
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Local embedding service error: {e.response.status_code}")
            raise RuntimeError(f"Local embedding failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Local embedding error: {e}")
            raise
    
    def embed_text(self, text: str) -> List[float]:
        """Embed single text"""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self._base_url}/embed",
                    json={"text": text}
                )
                response.raise_for_status()
                data = response.json()
                vectors = data.get("vectors", [[]])
                return vectors[0] if vectors else []
        except Exception as e:
            logger.error(f"Local embedding error: {e}")
            raise


class MockEmbeddingService(EmbeddingInterface):
    """Mock embedding service for development"""
    
    def __init__(self, model_alias: str = "all-MiniLM-L6-v2", dimensions: int = 384):
        self._model_alias = model_alias
        self._version = "v1"
        self._dimensions = dimensions
    
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


@dataclass
class ModelConfig:
    """Model configuration from database"""
    alias: str
    provider: str
    provider_model_name: str
    base_url: str
    api_key: Optional[str] = None
    dimensions: Optional[int] = None
    extra_config: Optional[Dict[str, Any]] = None
    connector: Optional[str] = None


class EmbeddingServiceFactory:
    """Factory for embedding services
    
    Creates appropriate provider based on model configuration from database.
    Caches service instances for reuse.
    """
    
    _services: Dict[str, EmbeddingInterface] = {}
    _model_configs: Dict[str, ModelConfig] = {}
    
    @classmethod
    def _resolve_api_key(cls, api_key_ref: Optional[str]) -> Optional[str]:
        """Resolve API key from environment variable reference"""
        if not api_key_ref:
            return None
        # api_key_ref is env var name like "OPENAI_API_KEY"
        return os.getenv(api_key_ref)
    
    @classmethod
    def _create_provider(cls, config: ModelConfig) -> EmbeddingInterface:
        """Create embedding provider based on config"""
        settings = get_settings()
        
        # Mock mode
        if getattr(settings, 'EMB_USE_MOCK', False):
            dimensions = config.dimensions or 384
            return MockEmbeddingService(config.alias, dimensions)
        
        connector = (config.connector or "").lower()
        provider = config.provider.lower()
        
        if connector == "local_emb_http" or (not connector and provider == "local" and config.base_url.startswith("http")):
            return LocalEmbeddingServiceProvider(
                model_alias=config.alias,
                provider_model_name=config.provider_model_name,
                base_url=config.base_url,
                dimensions=config.dimensions or 384
            )
        
        elif connector == "openai_http" or connector == "azure_openai_http" or (not connector and provider == "openai"):
            return OpenAIEmbeddingProvider(
                model_alias=config.alias,
                provider_model_name=config.provider_model_name,
                base_url=config.base_url,
                api_key=config.api_key,
                dimensions=config.dimensions
            )
        
        elif not connector and provider == "local":
            return LocalSentenceTransformerProvider(config.provider_model_name)
        
        elif not connector and provider == "sentence-transformers":
            return LocalSentenceTransformerProvider(config.provider_model_name)
        
        else:
            logger.warning(f"Unknown connector '{connector}'/provider '{provider}' for {config.alias}, using mock")
            return MockEmbeddingService(config.alias, config.dimensions or 384)
    
    @classmethod
    def register_model(cls, config: ModelConfig) -> None:
        """Register model configuration (called during startup)"""
        cls._model_configs[config.alias] = config
        # Clear cached service if exists
        if config.alias in cls._services:
            del cls._services[config.alias]

    @classmethod
    async def ensure_model_registered_async(cls, session: Any, model_alias: str) -> None:
        """Register model config from an async SQLAlchemy session when startup registry is unavailable."""
        if model_alias in cls._model_configs or model_alias in cls._services:
            return

        from sqlalchemy import text as sa_text

        result = await session.execute(
            sa_text(
                "SELECT alias, provider, provider_model_name, connector, base_url, extra_config "
                "FROM models WHERE alias = :alias AND type = 'EMBEDDING'"
            ),
            {"alias": model_alias},
        )
        mdata = result.mappings().first()
        if not mdata:
            return

        extra = mdata["extra_config"] or {}
        cls.register_model(
            ModelConfig(
                alias=mdata["alias"],
                provider=mdata["provider"] or "local",
                provider_model_name=mdata["provider_model_name"] or model_alias,
                base_url=mdata["base_url"] or extra.get("base_url", ""),
                dimensions=extra.get("vector_dim"),
                extra_config=extra,
                connector=mdata["connector"] or "",
            )
        )
    
    @classmethod
    def get_service(cls, model_alias: str) -> EmbeddingInterface:
        """Get embedding service by alias"""
        # Return cached service if available
        if model_alias in cls._services:
            return cls._services[model_alias]
        
        # Check if we have config for this model
        if model_alias in cls._model_configs:
            config = cls._model_configs[model_alias]
            service = cls._create_provider(config)
            cls._services[model_alias] = service
            return service
        
        # Fallback: try to load from database synchronously
        # This is a fallback for cases where startup didn't register models
        config = cls._load_model_config_sync(model_alias)
        if config:
            cls._model_configs[model_alias] = config
            service = cls._create_provider(config)
            cls._services[model_alias] = service
            return service
        
        # Ultimate fallback: mock service
        logger.warning(f"Model '{model_alias}' not found, using mock")
        service = MockEmbeddingService(model_alias)
        cls._services[model_alias] = service
        return service
    
    @classmethod
    def _load_model_config_sync(cls, model_alias: str) -> Optional[ModelConfig]:
        """Load model config from database (sync fallback)"""
        try:
            import asyncio
            from app.core.db import get_session_factory
            from app.models.model_registry import Model, ModelType
            from sqlalchemy import select
            
            async def _load():
                session_factory = get_session_factory()
                async with session_factory() as session:
                    result = await session.execute(
                        select(Model).where(
                            (Model.alias == model_alias) &
                            (Model.type == ModelType.EMBEDDING)
                        )
                    )
                    model = result.scalars().first()
                    if model:
                        # Resolve base_url and api_key from instance + credentials
                        base_url = ''
                        api_key = None
                        if model.instance:
                            base_url = model.instance.url or ''
                        
                        # 1. Try CredentialService (new approach)
                        if model.instance_id:
                            try:
                                from app.services.credential_service import CredentialService
                                cred_service = CredentialService(session)
                                decrypted = await cred_service.resolve_credentials(
                                    instance_id=model.instance_id,
                                    strategy="ANY",
                                )
                                if decrypted:
                                    if decrypted.auth_type == "api_key":
                                        api_key = decrypted.payload.get("api_key")
                                    elif decrypted.auth_type == "token":
                                        api_key = decrypted.payload.get("token")
                            except Exception as e:
                                logger.warning(f"Failed to resolve credentials for {model.alias}: {e}")
                        
                        # 2. Fallback: instance.config (legacy)
                        if not api_key and model.instance and model.instance.config:
                            api_key = model.instance.config.get('api_key')
                            if not api_key:
                                ref = model.instance.config.get('api_key_ref')
                                if ref:
                                    api_key = os.getenv(ref)
                        
                        if not base_url and model.extra_config and model.extra_config.get('base_url'):
                            base_url = model.extra_config['base_url']
                        
                        return ModelConfig(
                            alias=model.alias,
                            provider=model.provider,
                            provider_model_name=model.provider_model_name,
                            base_url=base_url,
                            api_key=api_key,
                            dimensions=model.extra_config.get('vector_dim') if model.extra_config else None,
                            extra_config=model.extra_config
                        )
                    return None
            
            # Try to get existing event loop or create new one
            try:
                loop = asyncio.get_running_loop()
                # If we're in async context, we can't use run()
                # This shouldn't happen in normal flow
                logger.warning(f"Cannot load model config in async context for {model_alias}")
                return None
            except RuntimeError:
                # No running loop, safe to create one
                return asyncio.run(_load())
                
        except Exception as e:
            logger.error(f"Failed to load model config for {model_alias}: {e}")
            return None
    
    @classmethod
    def list_available_models(cls) -> List[str]:
        """List available model aliases"""
        return list(cls._model_configs.keys())
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached services and configs"""
        cls._services.clear()
        cls._model_configs.clear()
