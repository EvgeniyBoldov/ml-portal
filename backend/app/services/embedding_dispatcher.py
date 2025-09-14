"""
Embedding Dispatcher - маршрутизатор задач эмбеддинга
Принимает логическую задачу и распределяет по моделям
"""
from __future__ import annotations
import asyncio
import time
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from celery import Celery
from app.core.model_registry import get_model_registry, ModelConfig
from app.core.config import settings

@dataclass
class EmbeddingRequest:
    """Запрос на эмбеддинг"""
    request_id: str
    texts: List[str]
    profile: str  # "rt" | "bulk"
    models: Optional[List[str]] = None
    tenant_id: Optional[str] = None
    reply_to: Optional[str] = None
    correlation_id: Optional[str] = None
    idempotency_key: Optional[str] = None

@dataclass
class ModelResult:
    """Результат от одной модели"""
    model: str
    dim: int
    vectors: List[List[float]]
    warnings: List[str]
    duration_ms: int

@dataclass
class EmbeddingResponse:
    """Ответ диспетчера"""
    request_id: str
    model_results: List[ModelResult]
    errors: List[str]
    used_profile: str

class EmbeddingDispatcher:
    """Диспетчер эмбеддингов"""
    
    def __init__(self, celery_app: Celery):
        self.celery = celery_app
        self.registry = get_model_registry()
    
    def dispatch_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Основной метод диспетчера"""
        start_time = time.perf_counter()
        
        # Определяем модели для использования
        if request.models:
            target_models = request.models
        else:
            target_models = self.registry.get_default_models(request.profile)
        
        # Получаем готовые модели
        ready_models = []
        for alias in target_models:
            model = self.registry.get_model(alias)
            if model and model.health == "ready":
                ready_models.append(model)
        
        if not ready_models:
            return EmbeddingResponse(
                request_id=request.request_id,
                model_results=[],
                errors=[f"No ready models found for profile {request.profile}"],
                used_profile=request.profile
            )
        
        # Отправляем задачи в очереди моделей
        tasks = []
        for model in ready_models:
            queue_name = model.queues[request.profile]
            task = self._send_embedding_task(request, model, queue_name)
            tasks.append((model, task))
        
        # Собираем результаты
        model_results = []
        errors = []
        
        for model, task in tasks:
            try:
                result = self._wait_for_result(task, request.profile)
                if result:
                    model_results.append(result)
                else:
                    errors.append(f"Model {model.alias} failed to respond")
            except Exception as e:
                errors.append(f"Model {model.alias} error: {str(e)}")
        
        return EmbeddingResponse(
            request_id=request.request_id,
            model_results=model_results,
            errors=errors,
            used_profile=request.profile
        )
    
    def _send_embedding_task(self, request: EmbeddingRequest, model: ModelConfig, queue_name: str) -> str:
        """Отправляет задачу в очередь модели"""
        task_payload = {
            "request_id": request.request_id,
            "texts": request.texts,
            "profile": request.profile,
            "model_alias": model.alias,
            "tenant_id": request.tenant_id,
            "reply_to": request.reply_to or f"embed.dispatch.{request.request_id}",
            "correlation_id": request.correlation_id,
            "idempotency_key": request.idempotency_key
        }
        
        # Отправляем задачу в очередь модели
        task = self.celery.send_task(
            "embedding_worker.process_embedding",
            args=[task_payload],
            queue=queue_name
        )
        
        return task.id
    
    def _wait_for_result(self, task_id: str, profile: str) -> Optional[ModelResult]:
        """Ждет результат от задачи"""
        timeout = 600 if profile == "bulk" else 800  # мс
        
        try:
            result = self.celery.AsyncResult(task_id)
            # Ждем результат с таймаутом
            response = result.get(timeout=timeout / 1000.0)
            
            if response and "error" not in response:
                return ModelResult(
                    model=response.get("model_alias", "unknown"),
                    dim=response.get("dim", 0),
                    vectors=response.get("vectors", []),
                    warnings=response.get("warnings", []),
                    duration_ms=response.get("duration_ms", 0)
                )
            else:
                return None
                
        except Exception as e:
            print(f"Task {task_id} failed: {e}")
            return None

# Celery задачи для диспетчера
def create_dispatcher_tasks(celery_app: Celery):
    """Создает Celery задачи для диспетчера"""
    
    @celery_app.task(name="embedding_dispatcher.dispatch")
    def dispatch_embedding_task(request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Celery задача для диспетчера"""
        request = EmbeddingRequest(**request_data)
        dispatcher = EmbeddingDispatcher(celery_app)
        response = dispatcher.dispatch_embedding(request)
        
        # Конвертируем в словарь для сериализации
        return {
            "request_id": response.request_id,
            "model_results": [
                {
                    "model": mr.model,
                    "dim": mr.dim,
                    "vectors": mr.vectors,
                    "warnings": mr.warnings,
                    "duration_ms": mr.duration_ms
                }
                for mr in response.model_results
            ],
            "errors": response.errors,
            "used_profile": response.used_profile
        }
    
    return dispatch_embedding_task

# Удобная функция для использования в API
def embed_texts_dispatcher(texts: List[str], profile: str = "rt", models: Optional[List[str]] = None) -> List[List[float]]:
    """Упрощенный интерфейс для эмбеддинга через диспетчер"""
    from app.celery_app import celery_app
    
    request = EmbeddingRequest(
        request_id=str(uuid.uuid4()),
        texts=texts,
        profile=profile,
        models=models
    )
    
    dispatcher = EmbeddingDispatcher(celery_app)
    response = dispatcher.dispatch_embedding(request)
    
    # Возвращаем векторы от первой успешной модели
    if response.model_results:
        return response.model_results[0].vectors
    else:
        raise Exception(f"Embedding failed: {response.errors}")
