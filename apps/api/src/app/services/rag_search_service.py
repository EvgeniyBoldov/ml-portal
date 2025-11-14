"""
RAG Search Service - поиск по векторной базе данных
"""
from __future__ import annotations
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

from app.core.config import get_settings
from app.adapters.impl.qdrant import QdrantVectorStore
from app.adapters.embeddings import EmbeddingServiceFactory
from app.repositories.rag_ingest_repos import AsyncChunkRepository
from app.core.db import get_session_factory

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Результат поиска"""
    text: str
    score: float
    source_id: str
    chunk_id: str
    page: int
    model_hits: List[Dict[str, Any]]  # [{"alias": "model1", "score": 0.8}]
    meta: Dict[str, Any]


class RagSearchService:
    """Сервис для поиска по RAG данным"""
    
    def __init__(self):
        self.settings = get_settings()
        # Don't create vector_store here to avoid event loop issues
    
    async def _get_tenant_models(self, tenant_id: str) -> List[str]:
        """
        Получить активные модели эмбеддингов для тенанта
        
        Args:
            tenant_id: ID тенанта
            
        Returns:
            Список алиасов моделей
        """
        from uuid import UUID
        from app.repositories.tenants_repo import AsyncTenantsRepository
        from app.core.config import get_embedding_models
        
        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                tenants_repo = AsyncTenantsRepository(session)
                tenant = await tenants_repo.get_by_id(UUID(tenant_id))
                
                if tenant and tenant.embed_models:
                    logger.info(f"Using tenant-specific models: {tenant.embed_models}")
                    return tenant.embed_models
                else:
                    # Fallback to global config
                    default_models = get_embedding_models()
                    logger.info(f"Tenant has no specific models, using default: {default_models}")
                    return default_models
        except Exception as e:
            logger.error(f"Error getting tenant models: {e}, falling back to global config")
            from app.core.config import get_embedding_models
            return get_embedding_models()
    
    async def search(
        self, 
        tenant_id: str, 
        query: str, 
        k: int = 5, 
        models: Optional[List[str]] = None,
        user: Optional[Any] = None  # User object for RBAC filtering
    ) -> List[SearchResult]:
        """
        Поиск по векторной базе данных с поддержкой scope-фильтров
        
        Args:
            tenant_id: ID тенанта
            query: Поисковый запрос
            k: Количество результатов
            models: Список моделей для поиска (если None - берём из tenant profile)
            user: User object для RBAC фильтрации
            
        Returns:
            Список результатов поиска
        """
        # Get models from tenant profile if not explicitly provided
        if models is None:
            models = await self._get_tenant_models(tenant_id)
        
        logger.info(f"Searching for query: '{query[:50]}...' with models: {models}")
        
        # Create vector store for this search
        vector_store = QdrantVectorStore()
        
        # Build scope filters for RBAC
        search_filter = None
        if user:
            from app.core.rbac import RBACValidator
            search_filter = RBACValidator.build_search_filters(user)
            logger.info(f"Using RBAC filters: {search_filter}")
        
        # Генерируем эмбеддинг для запроса (используем первую модель)
        embedding_service = EmbeddingServiceFactory.get_service(models[0])
        query_embedding = await asyncio.to_thread(embedding_service.embed_texts, [query])
        query_embedding = query_embedding[0]
        
        # Поиск по каждой модели
        all_results = []
        for model_alias in models:
            try:
                collection_name = f"{tenant_id}__{model_alias}"
                
                # Поиск в Qdrant с scope-фильтрами (берем больше результатов для лучшего объединения)
                search_results = await vector_store.search(
                    collection=collection_name,
                    query=query_embedding,
                    top_k=k * 2,  # Берем больше для RRF
                    filter=search_filter  # Применяем RBAC фильтры
                )
                
                if search_results:
                    # Нормализуем скоры для этой модели
                    normalized_results = self._normalize_scores(search_results)
                    # Добавляем alias модели к каждому результату
                    for result in normalized_results:
                        result['model_alias'] = model_alias
                    all_results.append(normalized_results)
                    logger.info(f"Found {len(normalized_results)} results for model {model_alias}")
                else:
                    logger.warning(f"No results found for model {model_alias}")
                    
            except Exception as e:
                logger.error(f"Error searching with model {model_alias}: {e}")
                continue
        
        if not all_results:
            logger.warning("No results found from any model")
            return []
        
        # Объединяем результаты через RRF
        merged_results = self._rrf_merge(all_results, k=60)  # RRF parameter
        
        # Ограничиваем количество результатов
        final_results = merged_results[:k]
        
        # Получаем тексты чанков
        # Используем тексты из payload Qdrant (уже есть в результатах)
        # await self._enrich_with_texts(final_results, tenant_id)
        
        logger.info(f"Returning {len(final_results)} final results")
        return final_results
    
    def _normalize_scores(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Нормализует скоры в диапазоне [0, 1] используя min-max нормализацию
        """
        if not results:
            return results
        
        scores = [r.get('score', 0.0) for r in results]
        if not scores:
            return results
        
        min_score = min(scores)
        max_score = max(scores)
        
        # Избегаем деления на ноль
        if max_score == min_score:
            normalized_results = []
            for r in results:
                normalized_r = r.copy()
                normalized_r['score'] = 1.0
                normalized_results.append(normalized_r)
            return normalized_results
        
        # Min-max нормализация
        normalized_results = []
        for r in results:
            normalized_r = r.copy()
            original_score = r.get('score', 0.0)
            normalized_score = (original_score - min_score) / (max_score - min_score)
            normalized_r['score'] = normalized_score
            normalized_results.append(normalized_r)
        
        return normalized_results
    
    def _rrf_merge(self, all_results: List[List[Dict[str, Any]]], k: int = 60) -> List[SearchResult]:
        """
        Объединяет результаты из разных моделей через Reciprocal Rank Fusion (RRF)
        """
        # Собираем все уникальные чанки
        chunk_scores = defaultdict(lambda: defaultdict(float))  # chunk_id -> {model: score}
        chunk_metadata = {}  # chunk_id -> metadata
        
        for model_idx, model_results in enumerate(all_results):
            # Получаем alias из первого результата (если есть)
            model_alias = model_results[0].get('model_alias', f"model_{model_idx}") if model_results else f"model_{model_idx}"
            
            for rank, result in enumerate(model_results):
                chunk_id = result.get('payload', {}).get('chunk_id')
                if not chunk_id:
                    continue
                
                # RRF score = 1 / (rank + k), где k - параметр функции
                rrf_score = 1.0 / (rank + k)
                chunk_scores[chunk_id][model_alias] = rrf_score
                
                # Сохраняем метаданные (берем из первого вхождения)
                if chunk_id not in chunk_metadata:
                    chunk_metadata[chunk_id] = result.get('payload', {})
        
        # Создаем финальные результаты
        final_results = []
        for chunk_id, model_scores in chunk_scores.items():
            # Суммируем RRF скоры
            total_score = sum(model_scores.values())
            
            # Создаем model_hits
            model_hits = [
                {"alias": model, "score": score} 
                for model, score in model_scores.items()
            ]
            
            metadata = chunk_metadata.get(chunk_id, {})
            
            result = SearchResult(
                text=metadata.get('text', ''),  # Используем текст из payload
                score=total_score,
                source_id=metadata.get('source_id', ''),
                chunk_id=chunk_id,
                page=metadata.get('page', 0),
                model_hits=model_hits,
                meta=metadata
            )
            final_results.append(result)
        
        # Сортируем по убыванию скора
        final_results.sort(key=lambda x: x.score, reverse=True)
        
        return final_results
    
    async def _enrich_with_texts(self, results: List[SearchResult], tenant_id: str):
        """
        Обогащает результаты текстами чанков из базы данных
        """
        if not results:
            return
        
        # Собираем все chunk_id для batch запроса
        chunk_ids_by_source = defaultdict(list)
        for result in results:
            chunk_ids_by_source[result.source_id].append(result.chunk_id)
        
        # Получаем тексты из БД
        from uuid import UUID
        session_factory = get_session_factory()
        async with session_factory() as session:
            chunk_repo = AsyncChunkRepository(session, UUID(tenant_id))
            
            for source_id, chunk_ids in chunk_ids_by_source.items():
                try:
                    # Получаем тексты для чанков
                    chunk_texts = await chunk_repo.get_texts_for_chunk_ids(UUID(source_id), chunk_ids)
                    
                    # Обновляем результаты
                    for result in results:
                        if result.source_id == source_id and result.chunk_id in chunk_texts:
                            result.text = chunk_texts[result.chunk_id]
                            
                except Exception as e:
                    logger.error(f"Error getting texts for source {source_id}: {e}")
                    # Заполняем пустыми строками
                    for result in results:
                        if result.source_id == source_id:
                            result.text = ""