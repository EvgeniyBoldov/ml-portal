"""
Embedding Worker - воркер для конкретной модели эмбеддинга
Загружает модель из MinIO, кэширует локально, обрабатывает батчи
"""
from __future__ import annotations
import os
import time
import hashlib
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer
from celery import Celery
from app.core.model_registry import get_model_registry, ModelConfig
from app.core.config import settings

class EmbeddingWorker:
    """Воркер эмбеддингов для одной модели"""
    
    def __init__(self):
        self.model_alias = os.getenv("EMB_MODEL_ALIAS", "minilm")
        self.model_id = os.getenv("EMB_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2")
        self.model_rev = os.getenv("EMB_MODEL_REV", "default")
        self.dim = int(os.getenv("EMB_DIM", "384"))
        self.max_seq = int(os.getenv("EMB_MAX_SEQ", "256"))
        self.device = os.getenv("EMB_DEVICE", "cpu")
        
        # MinIO настройки
        self.s3_endpoint = os.getenv("S3_ENDPOINT", "http://minio:9000")
        self.s3_access_key = os.getenv("S3_ACCESS_KEY", "minioadmin")
        self.s3_secret_key = os.getenv("S3_SECRET_KEY", "minioadmin")
        self.models_bucket = os.getenv("MODELS_BUCKET", "models")
        self.models_cache_dir = os.getenv("MODELS_CACHE_DIR", "/models-cache")
        
        # Батчинг настройки
        self.batch_max_tokens_rt = int(os.getenv("BATCH_MAX_TOKENS_RT", "4096"))
        self.batch_max_tokens_bulk = int(os.getenv("BATCH_MAX_TOKENS_BULK", "16384"))
        self.batch_max_wait_ms_rt = int(os.getenv("BATCH_MAX_WAIT_MS_RT", "25"))
        self.batch_max_wait_ms_bulk = int(os.getenv("BATCH_MAX_WAIT_MS_BULK", "200"))
        
        self.model = None
        self.tokenizer = None
        self.registry = get_model_registry()
        self.s3_client = None
        self._setup_s3()
        self._load_model()
    
    def _setup_s3(self):
        """Настраивает S3 клиент для MinIO"""
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.s3_endpoint,
                aws_access_key_id=self.s3_access_key,
                aws_secret_access_key=self.s3_secret_key
            )
        except Exception as e:
            print(f"Failed to setup S3 client: {e}")
            self.s3_client = None
    
    def _get_model_cache_path(self) -> Path:
        """Получает путь к кэшу модели"""
        cache_dir = Path(self.models_cache_dir) / self.model_alias / self.model_rev
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    
    def _download_model_from_s3(self) -> bool:
        """Скачивает модель из MinIO в локальный кэш"""
        if not self.s3_client:
            print("S3 client not available, using local model")
            return False
        
        cache_path = self._get_model_cache_path()
        
        try:
            # Проверяем, есть ли уже модель в кэше
            if (cache_path / "config.json").exists():
                print(f"Model already cached at {cache_path}")
                return True
            
            # Скачиваем из MinIO
            s3_prefix = f"{self.model_id}/{self.model_rev}/"
            print(f"Downloading model from s3://{self.models_bucket}/{s3_prefix}")
            
            # Список файлов для скачивания
            files_to_download = [
                "config.json",
                "pytorch_model.bin",
                "tokenizer.json",
                "tokenizer_config.json",
                "vocab.txt"
            ]
            
            for filename in files_to_download:
                s3_key = f"{s3_prefix}{filename}"
                local_path = cache_path / filename
                
                try:
                    self.s3_client.download_file(self.models_bucket, s3_key, str(local_path))
                    print(f"Downloaded {filename}")
                except ClientError as e:
                    if e.response['Error']['Code'] == '404':
                        print(f"File {filename} not found in S3, skipping")
                    else:
                        print(f"Failed to download {filename}: {e}")
            
            return True
            
        except Exception as e:
            print(f"Failed to download model from S3: {e}")
            return False
    
    def _load_model(self):
        """Загружает модель и токенайзер"""
        try:
            # Проверяем, нужно ли использовать локальные модели
            use_local = os.getenv("USE_LOCAL_MODELS", "false").lower() == "true"
            local_models_dir = os.getenv("LOCAL_MODELS_DIR", "/local-models")
            
            if use_local:
                # Используем локальные модели
                model_dir_name = self.model_id.replace("/", "--")
                local_model_path = Path(local_models_dir) / model_dir_name
                
                if local_model_path.exists():
                    model_path = str(local_model_path)
                    print(f"Loading model from local directory: {model_path}")
                else:
                    print(f"Local model not found at {local_model_path}, falling back to HuggingFace")
                    model_path = self.model_id
            else:
                # Пробуем скачать из S3
                s3_success = self._download_model_from_s3()
                
                cache_path = self._get_model_cache_path()
                
                if s3_success and (cache_path / "config.json").exists():
                    # Загружаем из кэша
                    model_path = str(cache_path)
                    print(f"Loading model from cache: {model_path}")
                else:
                    # Fallback на загрузку из HuggingFace (только для разработки)
                    model_path = self.model_id
                    print(f"Loading model from HuggingFace: {model_path}")
            
            # Загружаем модель
            self.model = SentenceTransformer(model_path, device=self.device)
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            
            # Обновляем статус в реестре
            self.registry.update_health(self.model_alias, "ready")
            
            print(f"Model {self.model_alias} loaded successfully")
            
        except Exception as e:
            print(f"Failed to load model {self.model_alias}: {e}")
            self.registry.update_health(self.model_alias, "down")
            raise
    
    def process_embedding_batch(self, texts: List[str], profile: str = "rt") -> Dict[str, Any]:
        """Обрабатывает батч текстов"""
        if not self.model:
            raise Exception("Model not loaded")
        
        start_time = time.perf_counter()
        
        try:
            # Токенизация и проверка длины
            max_tokens = self.batch_max_tokens_rt if profile == "rt" else self.batch_max_tokens_bulk
            
            # Простая проверка длины (можно улучшить)
            processed_texts = []
            warnings = []
            
            for i, text in enumerate(texts):
                if len(text) > max_tokens * 4:  # Примерная оценка
                    # Обрезаем текст
                    truncated = text[:max_tokens * 4]
                    processed_texts.append(truncated)
                    warnings.append(f"Text {i} truncated due to length")
                else:
                    processed_texts.append(text)
            
            # Генерируем эмбеддинги
            vectors = self.model.encode(processed_texts, convert_to_tensor=False)
            vectors_list = vectors.tolist() if hasattr(vectors, 'tolist') else vectors
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            return {
                "model_alias": self.model_alias,
                "dim": self.dim,
                "vectors": vectors_list,
                "warnings": warnings,
                "duration_ms": duration_ms
            }
            
        except Exception as e:
            print(f"Error processing batch: {e}")
            raise

# Celery задачи для воркера
def create_embedding_worker_tasks(celery_app: Celery):
    """Создает Celery задачи для воркера эмбеддингов"""
    
    worker = None
    
    @celery_app.task(name="embedding_worker.process_embedding")
    def process_embedding_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Основная задача воркера эмбеддингов"""
        nonlocal worker
        
        if worker is None:
            worker = EmbeddingWorker()
        
        try:
            texts = task_data.get("texts", [])
            profile = task_data.get("profile", "rt")
            
            if not texts:
                return {
                    "error": "No texts provided",
                    "model_alias": worker.model_alias
                }
            
            result = worker.process_embedding_batch(texts, profile)
            return result
            
        except Exception as e:
            return {
                "error": str(e),
                "model_alias": worker.model_alias if worker else "unknown"
            }
    
    @celery_app.task(name="embedding_worker.health_check")
    def health_check_task() -> Dict[str, Any]:
        """Проверка здоровья воркера"""
        nonlocal worker
        
        if worker is None:
            try:
                worker = EmbeddingWorker()
                return {
                    "status": "ready",
                    "model_alias": worker.model_alias,
                    "dim": worker.dim
                }
            except Exception as e:
                return {
                    "status": "down",
                    "error": str(e)
                }
        
        return {
            "status": "ready" if worker.model else "down",
            "model_alias": worker.model_alias,
            "dim": worker.dim
        }
    
    return process_embedding_task, health_check_task
