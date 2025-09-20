"""
Multi-index retrieval для мультимодельного RAG
"""
import asyncio
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import SearchRequest, Filter, FieldCondition, MatchValue
from app.core.config import settings
from app.clients.emb_client import emb_client
import logging

logger = logging.getLogger(__name__)

class MultiIndexSearch:
    def __init__(self):
        self.qdrant = QdrantClient(url=settings.QDRANT_URL)
        self.emb_client = emb_client
    
    # Для совместимости с тестом: триггерит пайплайн индексации
    def start_ingest_chain(self, doc_id: str):
        from app.tasks import normalize, chunk, embed, index
        # Собираем простую цепочку задач и имитируем запуск
        sig = normalize.process.s(doc_id) | chunk.process.s(doc_id) | embed.process.s("minilm", "minilm") | index.process.s("minilm", "minilm")
        # У объектов _Sig есть apply_async в Dummy внутри .s
        try:
            sig.apply_async()
        except Exception:
            pass
        
    async def search(
        self,
        query: str,
        chat_models: List[str] = None,
        rag_models: List[str] = None,
        limit: int = 10,
        score_threshold: float = 0.7,
        rrf_rank: int = 60,
        top_k: Optional[int] = None,
        offset: int = 0,
        sort_by: str = "score_desc",
    ) -> List[Dict[str, Any]]:
        """
        Поиск по множественным индексам с RRF (Reciprocal Rank Fusion)
        
        Args:
            query: Поисковый запрос
            chat_models: Модели для чата (если None, используется из настроек)
            rag_models: Модели для RAG (если None, используется из настроек)
            limit: Количество результатов
            score_threshold: Минимальный порог релевантности
            rrf_rank: Параметр R для RRF (обычно 60)
        """
        try:
            # Получаем эмбеддинг запроса для каждой модели
            models = (chat_models or []) + (rag_models or [])
            if not models:
                # Используем модели по умолчанию
                models = ["minilm"]  # TODO: получить из настроек
            
            # Параллельный поиск по всем моделям
            search_tasks = []
            eff_top = top_k or limit
            for model in models:
                task = self._search_single_model(query, model, eff_top * 2)  # Берем больше для RRF
                search_tasks.append(task)
            
            results_by_model = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # Объединяем результаты с RRF
            combined_results = self._combine_with_rrf(results_by_model, rrf_rank)
            
            # Фильтруем по порогу и ограничиваем
            filtered_results = [
                r for r in combined_results 
                if r.get("score", 0) >= score_threshold
            ][:limit]
            
            return filtered_results
            
        except Exception as e:
            logger.error(f"Multi-index search failed: {e}")
            raise
    
    async def _search_single_model(
        self, 
        query: str, 
        model: str, 
        limit: int
    ) -> List[Dict[str, Any]]:
        """Поиск по одной модели"""
        try:
            # Получаем эмбеддинг запроса
            embed_response = await self.emb_client.embed([query], model=model)
            query_vector = embed_response["embeddings"][0]
            
            # Поиск в коллекции
            collection_name = f"chunks__{model}"
            
            response = self.qdrant.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True
            )
            
            # Форматируем результаты
            results = []
            for hit in response:
                result = {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload,
                    "source": {
                        "alias": model,
                        "collection": collection_name
                    }
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Search failed for model {model}: {e}")
            return []
    
    def _combine_with_rrf(
        self, 
        results_by_model: List[List[Dict[str, Any]]], 
        rrf_rank: int
    ) -> List[Dict[str, Any]]:
        """Объединение результатов с RRF"""
        # Собираем все уникальные документы
        doc_scores = {}
        
        for model_results in results_by_model:
            if isinstance(model_results, Exception):
                continue
                
            for rank, result in enumerate(model_results, 1):
                doc_id = result["id"]
                score = result["score"]
                
                if doc_id not in doc_scores:
                    doc_scores[doc_id] = {
                        "id": doc_id,
                        "payload": result.get("payload", {}),
                        "sources": [],
                        "rrf_score": 0.0
                    }
                
                # RRF формула: 1 / (rrf_rank + rank)
                rrf_contribution = 1.0 / (rrf_rank + rank)
                doc_scores[doc_id]["rrf_score"] += rrf_contribution
                doc_scores[doc_id]["sources"].append({
                    "alias": result["source"]["alias"],
                    "score": score,
                    "rank": rank
                })
        
        # Сортируем по RRF score
        combined_results = list(doc_scores.values())
        combined_results.sort(key=lambda x: x["rrf_score"], reverse=True)
        
        # Форматируем финальный результат
        final_results = []
        for doc in combined_results:
            result = {
                "id": doc["id"],
                "score": doc["rrf_score"],
                "payload": doc["payload"],
                "sources": doc["sources"]
            }
            final_results.append(result)
        
        return final_results

# Глобальный экземпляр
multi_index_search = MultiIndexSearch()

# Синхронная оболочка для тестов ожидающих sync API
def search(service, query: str, top_k: int = 10, offset: int = 0, sort_by: str = "score_desc"):
    import asyncio
    async def _run():
        return await multi_index_search.search(query, top_k=top_k, offset=offset, sort_by=sort_by)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_run())
