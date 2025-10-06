from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from adapters.s3_client import s3_manager, PresignOptions
from core.config import get_settings
from core.s3_links import S3ContentType
import uuid
import json
from datetime import datetime

router = APIRouter(tags=["rag"])

# Mock data for development
MOCK_RAG_DOCUMENTS = [
    {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "Document 1",
        "status": "processed",
        "scope": "local",  # local or global
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "tags": ["test", "demo"],
        "size": 1024,
        "content_type": "application/pdf",
        "vectorized_models": ["all-MiniLM-L6-v2", "text-embedding-ada-002"]
    },
    {
        "id": "550e8400-e29b-41d4-a716-446655440002", 
        "name": "Document 2",
        "status": "processing",
        "scope": "local",
        "created_at": "2024-01-02T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "tags": ["test"],
        "size": 2048,
        "content_type": "text/plain",
        "vectorized_models": []
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
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    tags: Optional[str] = Form(None)
):
    """Upload a RAG file"""
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    doc_id = str(uuid.uuid4())
    doc_name = name or file.filename or f"Document {len(MOCK_RAG_DOCUMENTS) + 1}"
    
    # Parse tags from JSON string
    doc_tags = []
    if tags:
        try:
            doc_tags = json.loads(tags)
        except json.JSONDecodeError:
            # Fallback: treat as comma-separated string
            doc_tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
    
    now = datetime.utcnow().isoformat() + "Z"
    
    new_doc = {
        "id": doc_id,
        "name": doc_name,
        "status": "processing",
        "scope": "local",  # Default to local scope
        "created_at": now,
        "updated_at": now,
        "tags": doc_tags,
        "size": file.size or 0,
        "content_type": file.content_type or "application/octet-stream",
        "vectorized_models": []
    }
    
    MOCK_RAG_DOCUMENTS.append(new_doc)
    return {"id": doc_id, "status": "processing", "message": "File uploaded successfully"}

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

@router.put("/{doc_id}/scope")
async def update_rag_document_scope(
    doc_id: str,
    scope: str = Form(...)
):
    """Update RAG document scope (local/global)"""
    if scope not in ["local", "global"]:
        raise HTTPException(status_code=400, detail="Scope must be 'local' or 'global'")
    
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            doc["scope"] = scope
            doc["updated_at"] = datetime.utcnow().isoformat() + "Z"
            return {"id": doc_id, "scope": scope, "message": f"Document scope updated to {scope}"}
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.post("/{doc_id}/vectorize")
async def vectorize_rag_document(
    doc_id: str,
    model: str = Form("all-MiniLM-L6-v2")
):
    """Vectorize document with specific model"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            if model not in doc["vectorized_models"]:
                doc["vectorized_models"].append(model)
            doc["updated_at"] = datetime.utcnow().isoformat() + "Z"
            return {"id": doc_id, "model": model, "message": f"Document vectorized with {model}"}
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.get("/{doc_id}/models")
async def get_rag_document_models(doc_id: str):
    """Get vectorized models for a document"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            return {
                "id": doc_id,
                "vectorized_models": doc["vectorized_models"],
                "available_models": ["all-MiniLM-L6-v2", "text-embedding-ada-002", "sentence-transformers/all-mpnet-base-v2"]
            }
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.post("/{doc_id}/merge")
async def merge_rag_document(doc_id: str):
    """Merge document chunks (admin/ml-engineer only)"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            doc["updated_at"] = datetime.utcnow().isoformat() + "Z"
            return {"id": doc_id, "message": "Document chunks merged successfully"}
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.post("/{doc_id}/optimize")
async def optimize_rag_document(doc_id: str):
    """Optimize document for better retrieval (admin/ml-engineer only)"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            doc["updated_at"] = datetime.utcnow().isoformat() + "Z"
            return {"id": doc_id, "message": "Document optimized successfully"}
    
    raise HTTPException(status_code=404, detail="Document not found")

@router.get("/{doc_id}/analytics")
async def get_rag_document_analytics(doc_id: str):
    """Get document analytics (admin/ml-engineer only)"""
    for doc in MOCK_RAG_DOCUMENTS:
        if doc["id"] == doc_id:
            return {
                "id": doc_id,
                "analytics": {
                    "search_count": 42,
                    "last_searched": "2024-01-15T10:30:00Z",
                    "avg_score": 0.85,
                    "chunk_count": 15,
                    "popularity_score": 0.7
                }
            }
    
    raise HTTPException(status_code=404, detail="Document not found")

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
