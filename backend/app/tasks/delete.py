from __future__ import annotations
from celery import shared_task
from app.core.s3 import get_minio
from app.core.qdrant import get_qdrant
from app.core.db import SessionLocal
from app.core.config import settings
from app.models.rag import RagDocuments, RagChunks
from .shared import log, task_metrics

COLLECTION = "rag_chunks"


@shared_task(name="app.tasks.delete.hard_delete", bind=True)
def hard_delete(self, document_id: str) -> dict:
    """Hard delete: removes MinIO objects, Qdrant points and DB rows."""
    with task_metrics("delete.hard_delete", "delete"):
        session = SessionLocal()
        s3 = get_minio()
        qdrant = get_qdrant()
        
        try:
            doc = session.get(RagDocuments, document_id)
            if not doc:
                return {"document_id": document_id, "status": "not_found"}
            
            # Delete MinIO objects
            if doc.url_file:
                try:
                    s3.remove_object(settings.S3_BUCKET_RAG, doc.url_file)
                    log.info(f"Deleted raw file: {doc.url_file}")
                except Exception as e:
                    log.error(f"Failed to delete raw file {doc.url_file}: {e}")
            
            if doc.url_canonical_file:
                try:
                    s3.remove_object(settings.S3_BUCKET_RAG, doc.url_canonical_file)
                    log.info(f"Deleted canonical file: {doc.url_canonical_file}")
                except Exception as e:
                    log.error(f"Failed to delete canonical file {doc.url_canonical_file}: {e}")
            
            # Delete Qdrant points
            try:
                from qdrant_client.http.models import Filter, FieldCondition, MatchValue
                f = Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))])
                qdrant.delete(collection_name=COLLECTION, points_selector=f)
                log.info(f"Deleted Qdrant points for document: {document_id}")
            except Exception as e:
                log.error(f"Failed to delete Qdrant points for {document_id}: {e}")
            
            # Delete DB chunks
            session.query(RagChunks).filter(RagChunks.document_id == doc.id).delete()
            
            # Delete document
            session.delete(doc)
            session.commit()
            
            log.info(f"Hard deleted document: {document_id}")
            return {"document_id": document_id, "status": "deleted"}
            
        except Exception as e:
            log.error(f"Error during hard delete of {document_id}: {e}")
            session.rollback()
            raise
        finally:
            session.close()