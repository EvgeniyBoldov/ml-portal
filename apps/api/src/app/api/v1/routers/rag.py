from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from adapters.s3_client import s3_manager, PresignOptions
from core.config import get_settings
from core.s3_links import S3ContentType
from api.deps import db_session, get_current_user
from core.security import UserCtx
from repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from models.rag import RAGDocument, DocumentStatus, DocumentScope
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
    search: Optional[str] = Query(None),
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """List RAG documents with pagination and search"""
    try:
        # Get documents from database
        documents = await repo_factory.get_rag_documents(
            user_id=user.id,
            status=status,
            search=search,
            limit=size,
            offset=(page - 1) * size
        )
        
        # Get total count for pagination
        total_count = await repo_factory.count_rag_documents(
            user_id=user.id,
            status=status,
            search=search
        )
        
        # Convert to response format
        items = []
        for doc in documents:
            items.append({
                "id": str(doc.id),
                "name": doc.filename,
                "status": doc.status.value,
                "scope": doc.scope.value,
                "created_at": doc.created_at.isoformat() + "Z",
                "updated_at": doc.updated_at.isoformat() + "Z",
                "tags": doc.tags or [],
                "size": doc.size,
                "content_type": doc.content_type,
                "vectorized_models": []  # TODO: implement when worker is ready
            })
        
        return {
            "items": items,
            "pagination": {
                "page": page,
                "size": size,
                "total": total_count,
                "total_pages": (total_count + size - 1) // size,
                "has_next": page * size < total_count,
                "has_prev": page > 1
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")

@router.post("/upload")
async def upload_rag_file(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Upload a RAG file"""
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    try:
        # Generate document ID and prepare metadata
        doc_id = uuid.uuid4()
        doc_name = name or file.filename or f"Document {doc_id}"
        
        # Parse tags from JSON string
        doc_tags = []
        if tags:
            try:
                doc_tags = json.loads(tags)
            except json.JSONDecodeError:
                # Fallback: treat as comma-separated string
                doc_tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        # Upload file to MinIO
        settings = get_settings()
        s3_key = f"rag/documents/{doc_id}/{file.filename}"
        
        # Upload file to S3/MinIO
        await s3_manager.upload_file(
            bucket=settings.S3_BUCKET_RAG,
            key=s3_key,
            file_obj=file.file,
            content_type=file.content_type
        )
        
        # Create document record in database
        document = await repo_factory.create_rag_document(
            uploaded_by=user.id,
            name=doc_name,
            filename=file.filename or doc_name,
            content_type=file.content_type,
            size=file.size,
            tags=doc_tags,
            s3_key_raw=s3_key,
            status=DocumentStatus.UPLOADING.value
        )
        
        return {
            "id": str(document.id), 
            "status": document.status.value, 
            "message": "File uploaded successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

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
    kind: str = Query("original", regex="^(original|canonical)$"),
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Download RAG file"""
    try:
        document = await repo_factory.get_rag_document_by_id(uuid.UUID(doc_id))
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Determine S3 key based on kind
        s3_key = document.s3_key_raw if kind == "original" else document.s3_key_processed
        if not s3_key:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Generate presigned URL for download
        settings = get_settings()
        url = await s3_manager.generate_presigned_url(
            bucket=settings.S3_BUCKET_RAG,
            key=s3_key,
            options=PresignOptions(operation="get", expiry_seconds=3600)
        )
        
        return {"url": url}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate download URL: {str(e)}")

@router.post("/{doc_id}/archive")
async def archive_rag_document(
    doc_id: str,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Archive RAG document"""
    try:
        document = await repo_factory.get_rag_document_by_id(uuid.UUID(doc_id))
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Update status to archived
        document.status = DocumentStatus.ARCHIVED
        document.updated_at = datetime.utcnow()
        
        await session.commit()
        
        return {"id": doc_id, "archived": True}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to archive document: {str(e)}")

@router.delete("/{doc_id}")
async def delete_rag_document(
    doc_id: str,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Delete RAG document"""
    try:
        document = await repo_factory.get_rag_document_by_id(uuid.UUID(doc_id))
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Delete file from MinIO if exists
        if document.s3_key_raw:
            settings = get_settings()
            try:
                await s3_manager.delete_file(
                    bucket=settings.S3_BUCKET_RAG,
                    key=document.s3_key_raw
                )
            except Exception as e:
                # Log error but don't fail the deletion
                print(f"Failed to delete file from S3: {e}")
        
        # Delete document from database
        await repo_factory.delete_rag_document(uuid.UUID(doc_id))
        
        return {"id": doc_id, "deleted": True}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

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
    scope: str = Form(...),
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Update RAG document scope (local/global)"""
    if scope not in ["local", "global"]:
        raise HTTPException(status_code=400, detail="Scope must be 'local' or 'global'")
    
    try:
        document = await repo_factory.get_rag_document_by_id(uuid.UUID(doc_id))
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Update scope
        document.scope = DocumentScope(scope)
        document.updated_at = datetime.utcnow()
        
        await session.commit()
        
        return {
            "id": doc_id, 
            "scope": scope, 
            "message": f"Document scope updated to {scope}"
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update scope: {str(e)}")

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
