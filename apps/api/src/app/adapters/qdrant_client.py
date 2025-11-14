"""
Qdrant adapter with collection caching and explicit filter construction
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Union
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class QdrantAdapter:
    """Qdrant adapter with collection caching and explicit filters"""
    
    def __init__(self):
        self.client: Optional[QdrantClient] = None
        self._settings = get_settings()
        self._collection_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_cache_update = 0
    
    async def connect(self):
        """Connect to Qdrant"""
        try:
            self.client = QdrantClient(url=self._settings.QDRANT_URL)
            
            # Test connection
            await self._test_connection()
            logger.info("Connected to Qdrant")
            
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise
    
    async def _test_connection(self):
        """Test Qdrant connection"""
        try:
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.get_collections()
            )
        except Exception as e:
            logger.error(f"Qdrant connection test failed: {e}")
            raise
    
    async def _refresh_collection_cache(self):
        """Refresh collection cache if TTL expired"""
        current_time = time.time()
        if current_time - self._last_cache_update < self._cache_ttl:
            return
        
        try:
            loop = asyncio.get_event_loop()
            collections = await loop.run_in_executor(
                None,
                lambda: self.client.get_collections()
            )
            
            self._collection_cache = {
                collection.name: {
                    'name': collection.name,
                    'vectors_count': collection.vectors_count,
                    'indexed_vectors_count': collection.indexed_vectors_count,
                    'points_count': collection.points_count,
                    'segments_count': collection.segments_count,
                    'status': collection.status,
                    'optimizer_status': collection.optimizer_status,
                    'payload_schema': collection.payload_schema,
                    'config': collection.config
                }
                for collection in collections.collections
            }
            
            self._last_cache_update = current_time
            logger.debug(f"Refreshed collection cache: {len(self._collection_cache)} collections")
            
        except Exception as e:
            logger.error(f"Failed to refresh collection cache: {e}")
    
    async def get_collections(self) -> Dict[str, Dict[str, Any]]:
        """Get collections with caching"""
        await self._refresh_collection_cache()
        return self._collection_cache.copy()
    
    async def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists"""
        await self._refresh_collection_cache()
        return collection_name in self._collection_cache
    
    async def create_collection(self, collection_name: str, vector_size: int, 
                               distance: Distance = Distance.COSINE) -> bool:
        """Create collection"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=vector_size,
                        distance=distance
                    )
                )
            )
            
            # Invalidate cache
            self._last_cache_update = 0
            logger.info(f"Created collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False
    
    async def delete_collection(self, collection_name: str) -> bool:
        """Delete collection"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.delete_collection(collection_name)
            )
            
            # Invalidate cache
            self._last_cache_update = 0
            logger.info(f"Deleted collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete collection {collection_name}: {e}")
            return False
    
    def _build_search_filter(self, tenant_id: str, scope: Optional[str] = None, 
                           additional_filters: Optional[Dict[str, Any]] = None) -> Optional[Filter]:
        """Build explicit search filter with must/should/must_not structure"""
        conditions = []
        
        # Tenant and scope filtering
        if scope == 'local':
            conditions.append(
                FieldCondition(
                    key="tenant_id",
                    match=MatchValue(value=tenant_id)
                )
            )
            conditions.append(
                FieldCondition(
                    key="scope",
                    match=MatchValue(value="local")
                )
            )
        elif scope == 'global':
            conditions.append(
                FieldCondition(
                    key="scope",
                    match=MatchValue(value="global")
                )
            )
        else:
            # Default: (tenant_id==current AND scope='local') OR (scope='global')
            # This is handled by the search method with multiple queries
            pass
        
        # Additional filters
        if additional_filters:
            for key, value in additional_filters.items():
                if isinstance(value, list):
                    # Handle 'in' operator
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=models.MatchAny(any=value)
                        )
                    )
                else:
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
        
        if not conditions:
            return None
        
        return Filter(must=conditions)
    
    async def search(self, collection_name: str, query_vector: List[float], 
                    top_k: int = 10, filter_conditions: Optional[Dict[str, Any]] = None,
                    tenant_id: Optional[str] = None, scope: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search vectors with explicit filtering"""
        try:
            # Build filter
            search_filter = None
            if filter_conditions or tenant_id:
                search_filter = self._build_search_filter(
                    tenant_id or "", scope, filter_conditions
                )
            
            # Handle scope filtering for local+global search
            if scope is None and tenant_id:
                # Search both local and global documents
                local_results = await self._search_with_filter(
                    collection_name, query_vector, top_k,
                    self._build_search_filter(tenant_id, 'local', filter_conditions)
                )
                
                global_results = await self._search_with_filter(
                    collection_name, query_vector, top_k,
                    self._build_search_filter(tenant_id, 'global', filter_conditions)
                )
                
                # Combine and deduplicate results
                all_results = local_results + global_results
                seen_ids = set()
                unique_results = []
                
                for result in all_results:
                    point_id = result.get('id')
                    if point_id not in seen_ids:
                        seen_ids.add(point_id)
                        unique_results.append(result)
                
                # Sort by score and limit
                unique_results.sort(key=lambda x: x.get('score', 0), reverse=True)
                return unique_results[:top_k]
            
            # Single scope search
            return await self._search_with_filter(
                collection_name, query_vector, top_k, search_filter
            )
            
        except Exception as e:
            logger.error(f"Search error in {collection_name}: {e}")
            return []
    
    async def _search_with_filter(self, collection_name: str, query_vector: List[float],
                                 top_k: int, search_filter: Optional[Filter]) -> List[Dict[str, Any]]:
        """Internal search method with filter"""
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self.client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    query_filter=search_filter,
                    with_payload=True,
                    with_vectors=False
                )
            )
            
            return [
                {
                    'id': result.id,
                    'score': result.score,
                    'payload': result.payload or {}
                }
                for result in results
            ]
            
        except Exception as e:
            logger.error(f"Search with filter error in {collection_name}: {e}")
            return []
    
    async def upsert_points(self, collection_name: str, points: List[Dict[str, Any]]) -> bool:
        """Upsert points to collection"""
        try:
            point_structs = [
                PointStruct(
                    id=point['id'],
                    vector=point['vector'],
                    payload=point.get('payload', {})
                )
                for point in points
            ]
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.upsert(
                    collection_name=collection_name,
                    points=point_structs
                )
            )
            
            logger.debug(f"Upserted {len(points)} points to {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upsert points to {collection_name}: {e}")
            return False
    
    async def delete_points(self, collection_name: str, point_ids: List[Union[str, int]]) -> bool:
        """Delete points from collection"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.delete(
                    collection_name=collection_name,
                    points_selector=models.PointIdsList(points=point_ids)
                )
            )
            
            logger.debug(f"Deleted {len(point_ids)} points from {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete points from {collection_name}: {e}")
            return False
    
    async def delete_by_filter(self, collection_name: str, filter_conditions: Dict[str, Any]) -> bool:
        """Delete points by filter"""
        try:
            search_filter = self._build_search_filter("", None, filter_conditions)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.delete(
                    collection_name=collection_name,
                    points_selector=models.FilterSelector(filter=search_filter)
                )
            )
            
            logger.debug(f"Deleted points by filter from {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete points by filter from {collection_name}: {e}")
            return False
    
    async def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """Get collection information"""
        await self._refresh_collection_cache()
        return self._collection_cache.get(collection_name)
    
    async def health_check(self) -> bool:
        """Check Qdrant connectivity"""
        try:
            await self._test_connection()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False


# Global Qdrant adapter instance
_qdrant_adapter: Optional[QdrantAdapter] = None

async def get_qdrant_adapter() -> QdrantAdapter:
    """Get global Qdrant adapter instance"""
    global _qdrant_adapter
    if _qdrant_adapter is None:
        _qdrant_adapter = QdrantAdapter()
        await _qdrant_adapter.connect()
    return _qdrant_adapter
