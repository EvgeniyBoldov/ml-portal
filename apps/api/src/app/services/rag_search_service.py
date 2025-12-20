"""
RAG Search Service - поиск по векторной базе данных
"""
from __future__ import annotations
import asyncio
from app.core.logging import get_logger
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

from app.core.config import get_settings
from app.adapters.impl.qdrant import QdrantVectorStore
from app.adapters.embeddings import EmbeddingServiceFactory
from app.repositories.rag_ingest_repos import AsyncChunkRepository
from app.core.db import get_session_factory

logger = get_logger(__name__)


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
    source_name: str = ""  # Имя документа-источника


class RagSearchService:
    """Сервис для поиска по RAG данным"""
    
    def __init__(self):
        self.settings = get_settings()
        # Don't create vector_store here to avoid event loop issues
    
    async def _get_tenant_models(self, tenant_id: str) -> List[str]:
        """
        Получить модели эмбеддингов для поиска: ищем коллекции в Qdrant для этого тенанта
        """
        from uuid import UUID
        from sqlalchemy import select
        from app.models.model_registry import ModelRegistry, ModelType, ModelStatus
        
        session_factory = get_session_factory()
        async with session_factory() as session:
            # Get all available embedding models
            result = await session.execute(
                select(ModelRegistry).where(
                    (ModelRegistry.type == ModelType.EMBEDDING) & 
                    (ModelRegistry.enabled == True) &
                    (ModelRegistry.status == ModelStatus.AVAILABLE)
                )
            )
            all_models = result.scalars().all()
            
            # Check which collections exist in Qdrant for this tenant
            vector_store = QdrantVectorStore()
            models: List[str] = []
            
            for model in all_models:
                collection_name = f"{tenant_id}__{model.alias}"
                try:
                    exists = await vector_store.collection_exists(collection_name)
                    if exists:
                        models.append(model.alias)
                        logger.info(f"Found collection {collection_name}")
                except Exception as e:
                    logger.debug(f"Collection {collection_name} check failed: {e}")
            
            if not models:
                # Fallback to default model if no collections found
                default_model = next((m for m in all_models if m.default_for_type), None)
                if default_model:
                    models.append(default_model.alias)
                    logger.warning(f"No collections found, using default model: {default_model.alias}")
            
            return models
    
    async def search(
        self, 
        tenant_id: str, 
        query: str, 
        k: int = 5, 
        models: Optional[List[str]] = None,
        user: Optional[Any] = None  # User object for RBAC filtering
    ) -> List[SearchResult]:
        """
        Поиск по векторной базе данных с поддержкой scope-фильтров и реранкинга
        
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
        
        # Генерируем эмбеддинг для запроса (используем глобальную модель = первая в списке)
        embedding_service = EmbeddingServiceFactory.get_service(models[0])
        query_embedding = await asyncio.to_thread(embedding_service.embed_texts, [query])
        query_embedding = query_embedding[0]
        
        # Поиск по каждой модели
        all_results = []
        # Берем больше кандидатов для реранкинга (Recall phase)
        # Если реранкер включен, нам нужно больше кандидатов, чтобы отсеять мусор
        candidates_k = k * 4 if self.settings.RERANK_ENABLED else k * 2
        
        for model_alias in models:
            try:
                collection_name = f"{tenant_id}__{model_alias}"
                
                # Поиск в Qdrant с scope-фильтрами
                search_results = await vector_store.search(
                    collection=collection_name,
                    query=query_embedding,
                    top_k=candidates_k,
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
        
        # Объединяем результаты через RRF (Fusion phase)
        merged_results = self._rrf_merge(all_results, k=60)
        
        # Reranking phase (Precision phase)
        final_results = merged_results
        
        if self.settings.RERANK_ENABLED:
            try:
                # Берем топ кандидатов для реранкинга
                rerank_candidates = merged_results[:candidates_k]
                if rerank_candidates:
                    logger.info(f"Reranking {len(rerank_candidates)} candidates...")
                    reranked_results = await self._rerank_results(query, rerank_candidates, top_k=k)
                    final_results = reranked_results
                    logger.info(f"Reranking finished. Top score: {final_results[0].score if final_results else 0}")
                else:
                    final_results = []
            except Exception as e:
                logger.error(f"Reranking failed, falling back to RRF results: {e}")
                # Fallback to RRF results
                final_results = merged_results[:k]
        else:
            # Если реранкер выключен, просто берем топ-k по RRF
            final_results = merged_results[:k]
        
        # Обогащаем результаты именами документов
        await self._enrich_with_source_names(final_results, tenant_id)
        
        logger.info(f"Returning {len(final_results)} final results")
        return final_results

    async def _rerank_results(self, query: str, candidates: List[SearchResult], top_k: int) -> List[SearchResult]:
        """
        Переранжирование кандидатов с использованием Cross-Encoder сервиса
        """
        if not candidates:
            return []
            
        import httpx
        
        # Подготовка payload для реранкера
        # Reranker API ожидает: { "query": str, "documents": [str], "top_k": int }
        payload = {
            "query": query,
            "documents": [c.text for c in candidates],
            "top_k": top_k
        }
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.settings.RERANK_SERVICE_URL}/rerank",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                # Результаты приходят в формате: { "results": [ { "index": 0, "score": 0.99, "document": "..." } ] }
                reranked_indices = data.get("results", [])
                
                final_results = []
                for res in reranked_indices:
                    idx = res["index"]
                    new_score = res["score"]
                    
                    # Берем исходного кандидата по индексу
                    candidate = candidates[idx]
                    
                    # Сохраняем старый скор (RRF) в метаданных для отладки
                    if "rrf_score" not in candidate.meta:
                        candidate.meta["rrf_score"] = candidate.score
                        
                    # Обновляем скор на score от реранкера
                    candidate.score = new_score
                    
                    final_results.append(candidate)
                
                return final_results
                
        except httpx.RequestError as e:
            logger.error(f"Reranker connection error: {e}")
            raise e
        except httpx.HTTPStatusError as e:
            logger.error(f"Reranker API error {e.response.status_code}: {e.response.text}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error during reranking: {e}")
            raise e
    
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
    
    async def _enrich_with_source_names(self, results: List[SearchResult], tenant_id: str):
        """
        Обогащает результаты именами документов-источников
        """
        if not results:
            return
        
        # Собираем уникальные source_id
        source_ids = list(set(r.source_id for r in results if r.source_id))
        if not source_ids:
            return
        
        from uuid import UUID
        from sqlalchemy import select
        from app.models.rag import RAGDocument
        
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                # Получаем имена документов
                result = await session.execute(
                    select(RAGDocument.id, RAGDocument.name).where(
                        RAGDocument.id.in_([UUID(sid) for sid in source_ids])
                    )
                )
                source_names = {str(row.id): row.name for row in result.fetchall()}
                
                # Обновляем результаты
                for r in results:
                    if r.source_id in source_names:
                        r.source_name = source_names[r.source_id] or ""
                        
            except Exception as e:
                logger.error(f"Error enriching source names: {e}")
    
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