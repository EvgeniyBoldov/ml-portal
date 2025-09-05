from __future__ import annotations
import os, uuid
from datetime import datetime
import httpx
from celery import shared_task
from qdrant_client.http.models import VectorParams, Distance, PointStruct
from app.core.config import settings
from app.core.qdrant import get_qdrant
from app.core.db import SessionLocal
from app.core.metrics import rag_vectors_upserted_total
from app.models.rag import RagDocuments, RagChunks
from .shared import log, RetryableError, task_metrics, env_int, embedding_batch_inflight

EMB_URL = os.getenv("EMBEDDINGS_URL", "http://emb:8001")
COLLECTION = os.getenv("QDRANT_COLLECTION", "rag_chunks")

def _embed_sync(texts: list[str]) -> list[list[float]]:
    with httpx.Client(timeout=60) as client:
        r = client.post(f"{EMB_URL}/embed", json={"inputs": texts})
        r.raise_for_status()
        payload = r.json()
        return payload.get("vectors", [])

@shared_task(name="app.tasks.embed.compute", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def compute(self, document_id: str) -> dict:
    with task_metrics("embed.compute", "embed"):
        session = SessionLocal()
        qdrant = get_qdrant()
        try:
            doc = session.get(RagDocuments, document_id)
            if not doc:
                raise RetryableError("document_not_found")
            doc_tags = doc.tags or []
            BATCH = env_int("EMBEDDING_BATCH_SIZE", 8)
            rows = session.query(RagChunks).filter(RagChunks.document_id==doc.id, RagChunks.qdrant_point_id==None).order_by(RagChunks.chunk_idx.asc()).all()
            total = 0
            for i in range(0, len(rows), BATCH):
                batch = rows[i:i+BATCH]
                texts = [c.text for c in batch]
                embedding_batch_inflight.inc()
                try:
                    vectors = _embed_sync(texts)
                finally:
                    embedding_batch_inflight.dec()
                if not vectors:
                    raise RetryableError("empty_vectors")

                dim = len(vectors[0])
                try:
                    qdrant.get_collection(COLLECTION)
                except Exception:
                    from qdrant_client.http.models import OptimizersConfigDiff
                    qdrant.recreate_collection(
                        collection_name=COLLECTION,
                        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                        optimizers_config=OptimizersConfigDiff(memmap_threshold=20000)
                    )

                points = []
                now = datetime.utcnow()
                for chunk, vec in zip(batch, vectors):
                    pid = uuid.uuid4()
                    points.append(PointStruct(id=str(pid), vector=vec, payload={
                        "document_id": str(doc.id),
                        "chunk_idx": chunk.chunk_idx,
                        "text": chunk.text,
                        "tags": doc_tags,
                    }))
                    chunk.qdrant_point_id = pid
                    chunk.embedding_model = os.getenv("MODEL_ID","BAAI/bge-m3")
                    chunk.embedding_version = "v1"
                    chunk.date_embedding = now
                qdrant.upsert(collection_name=COLLECTION, points=points)
                session.commit()
                rag_vectors_upserted_total.inc(len(points))
                total += len(batch)
            doc.status = "indexing"; doc.updated_at = datetime.utcnow()
            session.commit()
            return {"document_id": str(doc.id), "embedded": total, "status": doc.status}
        finally:
            session.close()
