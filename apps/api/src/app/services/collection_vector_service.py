"""
Collection Vector Service - управление векторизацией коллекций
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from app.models.collection import Collection
from app.core.config import settings


class CollectionVectorService:
    """Сервис для работы с векторным поиском в коллекциях"""
    
    def __init__(self, session: AsyncSession, qdrant_client: Optional[QdrantClient] = None):
        self.session = session
        self.qdrant_client = qdrant_client or QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY if hasattr(settings, 'QDRANT_API_KEY') else None,
        )
    
    async def create_qdrant_collection(
        self, 
        collection: Collection,
        vector_size: int = 1536,  # OpenAI ada-002 default
    ) -> None:
        """
        Создать Qdrant коллекцию для векторного поиска
        
        Args:
            collection: Collection модель
            vector_size: Размерность векторов (зависит от модели эмбеддинга)
        """
        if not collection.qdrant_collection_name:
            raise ValueError("Collection must have qdrant_collection_name")
        
        # Проверяем существует ли коллекция
        collections = self.qdrant_client.get_collections().collections
        exists = any(c.name == collection.qdrant_collection_name for c in collections)
        
        if not exists:
            self.qdrant_client.create_collection(
                collection_name=collection.qdrant_collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
    
    async def delete_qdrant_collection(self, qdrant_collection_name: str) -> None:
        """Удалить Qdrant коллекцию"""
        try:
            self.qdrant_client.delete_collection(collection_name=qdrant_collection_name)
        except Exception:
            # Коллекция может не существовать
            pass
    
    async def index_row(
        self,
        collection: Collection,
        row_id: str,
        row_data: Dict[str, Any],
        embeddings: Dict[str, List[float]],
    ) -> int:
        """
        Индексировать одну строку в Qdrant
        
        Args:
            collection: Collection модель
            row_id: ID строки из SQL таблицы
            row_data: Данные строки
            embeddings: Словарь {field_name: vector} для векторных полей
        
        Returns:
            Количество созданных чанков (точек в Qdrant)
        """
        if not collection.qdrant_collection_name:
            raise ValueError("Collection must have qdrant_collection_name")
        
        points = []
        chunk_count = 0
        
        # Для каждого векторного поля создаём точки в Qdrant
        for field in collection.vector_fields:
            field_name = field["name"]
            if field_name not in embeddings:
                continue
            
            # Каждый чанк = отдельная точка в Qdrant
            for chunk_idx, vector in enumerate(embeddings[field_name]):
                point_id = f"{row_id}_{field_name}_{chunk_idx}"
                
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "row_id": row_id,
                            "field_name": field_name,
                            "chunk_idx": chunk_idx,
                            "text": row_data.get(field_name, ""),
                            **{k: v for k, v in row_data.items() if k != field_name},
                        },
                    )
                )
                chunk_count += 1
        
        if points:
            self.qdrant_client.upsert(
                collection_name=collection.qdrant_collection_name,
                points=points,
            )
        
        return chunk_count
    
    async def update_vectorization_stats(
        self,
        collection_id: uuid.UUID,
        vectorized_rows_delta: int = 0,
        total_chunks_delta: int = 0,
        failed_rows_delta: int = 0,
    ) -> None:
        """
        Обновить статистику векторизации
        
        Args:
            collection_id: ID коллекции
            vectorized_rows_delta: Изменение количества векторизованных строк
            total_chunks_delta: Изменение количества чанков
            failed_rows_delta: Изменение количества failed строк
        """
        await self.session.execute(
            text("""
                UPDATE collections
                SET 
                    vectorized_rows = vectorized_rows + :vectorized,
                    total_chunks = total_chunks + :chunks,
                    failed_rows = failed_rows + :failed,
                    updated_at = :now
                WHERE id = :collection_id
            """),
            {
                "collection_id": str(collection_id),
                "vectorized": vectorized_rows_delta,
                "chunks": total_chunks_delta,
                "failed": failed_rows_delta,
                "now": datetime.utcnow(),
            },
        )
        await self.session.commit()
    
    async def search_similar(
        self,
        collection: Collection,
        query_vector: List[float],
        field_name: Optional[str] = None,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Поиск похожих записей по вектору
        
        Args:
            collection: Collection модель
            query_vector: Вектор запроса
            field_name: Опционально - искать только в конкретном поле
            limit: Максимальное количество результатов
            filters: Опциональные фильтры для payload
        
        Returns:
            Список найденных записей с score
        """
        if not collection.qdrant_collection_name:
            raise ValueError("Collection must have qdrant_collection_name")
        
        # Формируем фильтр
        search_filter = None
        if field_name or filters:
            conditions = []
            if field_name:
                conditions.append({"key": "field_name", "match": {"value": field_name}})
            if filters:
                for key, value in filters.items():
                    conditions.append({"key": key, "match": {"value": value}})
            
            if conditions:
                search_filter = {"must": conditions}
        
        # Поиск в Qdrant
        results = self.qdrant_client.search(
            collection_name=collection.qdrant_collection_name,
            query_vector=query_vector,
            query_filter=search_filter,
            limit=limit,
        )
        
        # Группируем по row_id и берём лучший score
        rows_map: Dict[str, Dict[str, Any]] = {}
        for hit in results:
            row_id = hit.payload["row_id"]
            if row_id not in rows_map or hit.score > rows_map[row_id]["score"]:
                rows_map[row_id] = {
                    "row_id": row_id,
                    "score": hit.score,
                    "field_name": hit.payload["field_name"],
                    "chunk_idx": hit.payload["chunk_idx"],
                    "text": hit.payload.get("text", ""),
                    "payload": {k: v for k, v in hit.payload.items() 
                               if k not in ["row_id", "field_name", "chunk_idx", "text"]},
                }
        
        return sorted(rows_map.values(), key=lambda x: x["score"], reverse=True)
