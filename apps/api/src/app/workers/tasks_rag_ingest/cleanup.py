from __future__ import annotations
import logging
import uuid
from typing import Dict, Any

from celery import Task

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.adapters.s3_client import s3_manager
from app.storage.paths import get_document_prefix
from app.workers.session_factory import get_worker_session_factory

logger = logging.getLogger(__name__)


@celery_app.task(
    queue="cleanup_low",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3
)
def cleanup_document_artifacts(self: Task, tenant_id: str, source_id: str) -> Dict[str, Any]:
    """
    Clean up all S3 artifacts for a document.
    Deletes the entire prefix: {tenant_id}/{source_id}/
    
    Args:
        tenant_id: Tenant ID
        source_id: Document (Source) ID
    
    Returns:
        Dict: Cleanup status
    """
    logger.info(f"Starting cleanup_document_artifacts for {source_id}")
    
    try:
        import asyncio
        
        async def _cleanup():
            settings = get_settings()
            
            # Construct the prefix to delete
            # Ensure we are deleting the correct folder
            try:
                t_uuid = uuid.UUID(tenant_id)
                s_uuid = uuid.UUID(source_id)
                prefix = get_document_prefix(t_uuid, s_uuid)
            except ValueError:
                logger.error(f"Invalid UUIDs: tenant={tenant_id}, source={source_id}")
                return {"status": "failed", "error": "Invalid UUIDs"}
            
            # Safety check: prefix should not be empty or root
            if not prefix or len(prefix) < 10:
                logger.error(f"Dangerous prefix deletion attempted: {prefix}")
                return {"status": "failed", "error": "Dangerous prefix"}
            
            logger.info(f"Deleting S3 prefix: {prefix}")
            
            # List objects to verify (optional, but good for logging)
            # Delete recursively
            await s3_manager.delete_folder(
                bucket=settings.S3_BUCKET_RAG,
                prefix=prefix
            )
            
            # Also delete from vector store (Qdrant)
            # We need to delete by filter source_id
            try:
                from app.adapters.impl.qdrant import QdrantVectorStore
                from app.repositories.rag_status_repo import AsyncRAGStatusRepository
                from app.schemas.common import EmbeddingModel
                
                # Determine which models were used for this document
                # by querying the RAGStatus table
                used_models = []
                session_factory = get_worker_session_factory()
                
                try:
                    async with session_factory() as session:
                        status_repo = AsyncRAGStatusRepository(session, tenant_id=uuid.UUID(tenant_id))
                        embedding_nodes = await status_repo.get_embedding_nodes(uuid.UUID(source_id))
                        used_models = [node.node_key for node in embedding_nodes]
                except Exception as db_err:
                    logger.warning(f"Could not fetch used models from DB: {db_err}. Falling back to all known models.")
                
                # Fallback if no info found (e.g. status already deleted or never created)
                if not used_models:
                    used_models = [m.value for m in EmbeddingModel]
                
                logger.info(f"Cleaning up vectors for models: {used_models}")
                
                vector_store = QdrantVectorStore()
                client = await vector_store.get_client()
                
                for model_alias in used_models:
                    collection_name = f"{tenant_id}__{model_alias}"
                    try:
                        # Qdrant delete by filter
                        from qdrant_client.http import models
                        await client.delete(
                            collection_name=collection_name,
                            points_selector=models.FilterSelector(
                                filter=models.Filter(
                                    must=[
                                        models.FieldCondition(
                                            key="source_id",
                                            match=models.MatchValue(value=source_id)
                                        )
                                    ]
                                )
                            )
                        )
                        logger.info(f"Deleted vectors for {source_id} from {collection_name}")
                    except Exception as q_err:
                        # Collection might not exist or other error
                        logger.warning(f"Failed to delete from {collection_name}: {q_err}")
                        pass
                        
            except Exception as v_err:
                logger.error(f"Failed to clean up vectors: {v_err}")

            return {
                "source_id": source_id,
                "status": "completed",
                "prefix_deleted": prefix,
                "models_cleaned": used_models if 'used_models' in locals() else []
            }

        return asyncio.run(_cleanup())

    except Exception as e:
        logger.error(f"Error in cleanup_document_artifacts for {source_id}: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)
