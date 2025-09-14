"""
Model Registry - простой реестр моделей в Redis
Управляет конфигурацией моделей эмбеддингов и LLM
"""
from __future__ import annotations
import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from app.core.redis import get_redis

@dataclass
class ModelConfig:
    """Конфигурация модели"""
    id: str                    # HF ID (например, "sentence-transformers/all-MiniLM-L6-v2")
    alias: str                 # Короткое имя (например, "minilm")
    rev: str                   # Ревизия/хеш
    dim: int                   # Размерность векторов
    max_seq: int               # Максимальная длина последовательности
    storage_uri: str           # Путь в MinIO (например, "s3://models/sentence-transformers/all-MiniLM-L6-v2/abc123")
    queues: Dict[str, str]     # {"rt": "embed.minilm.rt", "bulk": "embed.minilm.bulk"}
    weights: float = 1.0       # Вес для фьюзинга
    enabled: bool = True       # Включена ли модель
    health: str = "down"       # "ready" | "degraded" | "down"
    pooling: str = "mean"      # "mean" | "cls"
    tokenizer_rev: str = ""    # Ревизия токенайзера
    checksum: Dict[str, str] = None  # {"model.safetensors": "sha256:..."}
    
    def __post_init__(self):
        if self.checksum is None:
            self.checksum = {}

class ModelRegistry:
    """Реестр моделей в Redis"""
    
    def __init__(self):
        self.redis = get_redis()
        self._default_models = self._load_default_models()
    
    def _load_default_models(self) -> Dict[str, ModelConfig]:
        """Загружает дефолтные модели из переменных окружения"""
        models = {}
        
        # Читаем конфигурацию из переменных окружения
        # Формат: EMB_MODELS="minilm:sentence-transformers/all-MiniLM-L6-v2:abc123:384:256,minilm2:sentence-transformers/all-MiniLM-L6-v2:def456:384:256"
        emb_models = os.getenv("EMB_MODELS", "")
        if emb_models:
            for model_str in emb_models.split(","):
                if not model_str.strip():
                    continue
                parts = model_str.strip().split(":")
                if len(parts) >= 5:
                    alias, model_id, rev, dim, max_seq = parts[:5]
                    models[alias] = ModelConfig(
                        id=model_id,
                        alias=alias,
                        rev=rev,
                        dim=int(dim),
                        max_seq=int(max_seq),
                        storage_uri=f"s3://models/{model_id}/{rev}",
                        queues={
                            "rt": f"embed.{alias}.rt",
                            "bulk": f"embed.{alias}.bulk"
                        }
                    )
        
        # Если нет переменных, создаем дефолтную модель для тестирования
        if not models:
            models["minilm"] = ModelConfig(
                id="sentence-transformers/all-MiniLM-L6-v2",
                alias="minilm",
                rev="default",
                dim=384,
                max_seq=256,
                storage_uri="s3://models/sentence-transformers/all-MiniLM-L6-v2/default",
                queues={
                    "rt": "embed.minilm.rt",
                    "bulk": "embed.minilm.bulk"
                }
            )
        
        return models
    
    def register_model(self, config: ModelConfig) -> bool:
        """Регистрирует модель в реестре"""
        try:
            key = f"model:{config.alias}"
            self.redis.hset(key, mapping={
                "config": json.dumps(asdict(config), ensure_ascii=False)
            })
            return True
        except Exception as e:
            print(f"Failed to register model {config.alias}: {e}")
            return False
    
    def get_model(self, alias: str) -> Optional[ModelConfig]:
        """Получает конфигурацию модели по алиасу"""
        try:
            key = f"model:{alias}"
            data = self.redis.hget(key, "config")
            if not data:
                return None
            config_dict = json.loads(data)
            return ModelConfig(**config_dict)
        except Exception as e:
            print(f"Failed to get model {alias}: {e}")
            return None
    
    def list_models(self, enabled_only: bool = True) -> List[ModelConfig]:
        """Список всех моделей"""
        models = []
        try:
            # Сначала пробуем загрузить из Redis
            keys = self.redis.keys("model:*")
            for key in keys:
                data = self.redis.hget(key, "config")
                if data:
                    config_dict = json.loads(data)
                    config = ModelConfig(**config_dict)
                    if not enabled_only or config.enabled:
                        models.append(config)
            
            # Если в Redis ничего нет, используем дефолтные
            if not models:
                for config in self._default_models.values():
                    if not enabled_only or config.enabled:
                        models.append(config)
                        # Регистрируем дефолтные модели в Redis
                        self.register_model(config)
        
        except Exception as e:
            print(f"Failed to list models: {e}")
            # Fallback на дефолтные модели
            for config in self._default_models.values():
                if not enabled_only or config.enabled:
                    models.append(config)
        
        return models
    
    def get_default_models(self, profile: str = "rt") -> List[str]:
        """Получает список дефолтных моделей для профиля"""
        if profile == "rt":
            return os.getenv("EMB_DEFAULT_RT_MODELS", "minilm").split(",")
        else:
            return os.getenv("EMB_DEFAULT_BULK_MODELS", "minilm").split(",")
    
    def update_health(self, alias: str, health: str) -> bool:
        """Обновляет статус здоровья модели"""
        try:
            config = self.get_model(alias)
            if config:
                config.health = health
                return self.register_model(config)
            return False
        except Exception as e:
            print(f"Failed to update health for {alias}: {e}")
            return False
    
    def get_ready_models(self, profile: str = "rt") -> List[ModelConfig]:
        """Получает список готовых моделей для профиля"""
        models = self.list_models(enabled_only=True)
        ready_models = []
        
        for model in models:
            if model.health == "ready" and profile in model.queues:
                ready_models.append(model)
        
        return ready_models

# Глобальный экземпляр реестра
_registry = None

def get_model_registry() -> ModelRegistry:
    """Получает глобальный экземпляр реестра моделей"""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
