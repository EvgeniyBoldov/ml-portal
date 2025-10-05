from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from adapters.s3_client import s3_manager, PresignOptions
from core.config import get_settings
from core.s3_links import S3ContentType
import uuid

router = APIRouter(tags=["rag"])

# Mock data for development
MOCK_RAG_DOCUMENTS = [
    {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "Document 1",
        "status": "processed",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "tags": ["test", "demo"],
        "size": 1024,
        "content_type": "application/pdf"
    },
    {
        "id": "550e8400-e29b-41d4-a716-446655440002", 
        "name": "Document 2",
        "status": "processing",
        "created_at": "2024-01-02T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "tags": ["test"],
        "size": 2048,
        "content_type": "text/plain"
    }
]

@router.get("")
async def list_rag_documents(
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    """List RAG documents with pagination and search"""
    # Filter by status if provided
    filtered_docs = MOCK_RAG_DOCUMENTS
    if status:
        filtered_docs = [doc for doc in filtered_docs if doc["status"] == status]
    
    # Filter by search if provided
    if search:
        filtered_docs = [doc for doc in filtered_docs if search.lower() in doc["name"].lower()]
    
    # Calculate pagination
    total = len(filtered_docs)
    start_idx = (page - 1) * size
    end_idx = start_idx + size
    items = filtered_docs[start_idx:end_idx]
    
    return {
        "items": items,
        "pagination": {
            "page": page,
            "size": size,
            "total": total,
            "total_pages": (total + size - 1) // size,
            "has_next": end_idx < total,
            "has_prev": page > 1
        }
    }

@router.post("/upload")
async def upload_rag_file(
    file: Any,  # This would be a file upload in real implementation
    name: Optional[str] = None,
    tags: Optional[str] = None
):
    """Upload a RAG file"""
    doc_id = str(uuid.uuid4())
    doc_name = name or f"Document {len(MOCK_RAG_DOCUMENTS) + 1}"
    doc_tags = tags.split(",") if tags else []
    
    new_doc = {
        "id": doc_id,
        "name": doc_name,
        "status": "processing",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "tags": doc_tags,
        "size": 1024,
        "content_type": "application/pdf"
    }
    
    MOCK_RAG_DOCUMENTS.append(new_doc)
    return {"id": doc_id, "status": "processing"}

@router.put("/{doc_id}/tags")
async def update_rag_document_tags(doc_id: str, tags: list[str]):
    """Update RAG document tags"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            doc["tags"] = tags
            doc["updated_at"] = "2024-01-01T00:00:00Z"
            return {"id": doc_id, "tags": tags}
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.get("/{doc_id}/progress")
async def get_rag_progress(doc_id: str):
    """Get RAG document processing progress"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            return {
                "id": doc_id,
                "status": doc["status"],
                "progress": 100 if doc["status"] == "processed" else 50,
                "message": "Processing complete" if doc["status"] == "processed" else "Processing..."
            }
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.get("/stats")
async def get_rag_stats():
    """Get RAG statistics"""
    total_docs = len(MOCK_RAG_DOCUMENTS)
    processed_docs = len([doc for doc in MOCK_RAG_DOCUMENTS if doc["status"] == "processed"])
    processing_docs = len([doc for doc in MOCK_RAG_DOCUMENTS if doc["status"] == "processing"])
    
    return {
        "total_documents": total_docs,
        "processed_documents": processed_docs,
        "processing_documents": processing_docs,
        "failed_documents": 0
    }

@router.get("/metrics")
async def get_rag_metrics():
    """Get RAG metrics"""
    return {
        "total_chunks": 150,
        "avg_chunk_size": 512,
        "index_size_mb": 25.6,
        "last_indexed": "2024-01-01T00:00:00Z"
    }

@router.get("/{doc_id}/download")
async def download_rag_file(
    doc_id: str,
    kind: str = Query("original", regex="^(original|canonical)$")
):
    """Download RAG file"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            return {"url": f"http://localhost:9000/rag/docs/{doc_id}"}
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.post("/{doc_id}/archive")
async def archive_rag_document(doc_id: str):
    """Archive RAG document"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            doc["status"] = "archived"
            doc["updated_at"] = "2024-01-01T00:00:00Z"
            return {"id": doc_id, "archived": True}
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.delete("/{doc_id}")
async def delete_rag_document(doc_id: str):
    """Delete RAG document"""
    for i, doc in enumerate(MOCK_RAG_DOCUMENTS):
        if doc["id"] == doc_id:
            MOCK_RAG_DOCUMENTS.pop(i)
            return {"id": doc_id, "deleted": True}
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.post("/search")
async def rag_search(payload: dict[str, Any]):
    """Search RAG documents"""
    text = payload.get("text", "")
    top_k = payload.get("top_k", 10)
    min_score = payload.get("min_score", 0.0)
    
    # Mock search results
    results = [
        {
            "document_id": "550e8400-e29b-41d4-a716-446655440001",
            "chunk_id": "chunk-1",
            "score": 0.95,
            "snippet": f"Found text: {text}"
        },
        {
            "document_id": "550e8400-e29b-41d4-a716-446655440002",
            "chunk_id": "chunk-2", 
            "score": 0.87,
            "snippet": f"Another match: {text}"
        }
    ]
    
    return {"items": results[:top_k]}

@router.post("/{doc_id}/reindex")
async def reindex_rag_document(doc_id: str):
    """Reindex RAG document"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            doc["status"] = "processing"
            doc["updated_at"] = "2024-01-01T00:00:00Z"
            return {"id": doc_id, "status": "processing"}
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.post("/reindex")
async def reindex_all_rag_documents():
    """Reindex all RAG documents"""
    for doc in MOCK_RAG_DOCUMENTS:
        doc["status"] = "processing"
        doc["updated_at"] = "2024-01-01T00:00:00Z"
    
    return {
        "reindexed_count": len(MOCK_RAG_DOCUMENTS),
        "total_documents": len(MOCK_RAG_DOCUMENTS)
    }

@router.post("/upload/presign")
def presign_rag_upload(body: dict[str, Any]) -> dict:
    doc_id = body.get("document_id")
    if not doc_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    content_type = body.get("content_type", S3ContentType.OCTET)
    key = f"docs/{doc_id}"
    s = get_settings()
    url = s3_manager.generate_presigned_url(
        bucket=s.S3_BUCKET_RAG,
        key=key,
        options=PresignOptions(operation="put", expiry_seconds=3600, content_type=content_type),
    )
    return {"presigned_url": url, "bucket": s.S3_BUCKET_RAG, "key": key, "content_type": content_type, "expires_in": 3600}
