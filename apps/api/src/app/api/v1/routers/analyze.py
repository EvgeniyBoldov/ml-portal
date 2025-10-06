from __future__ import annotations
from typing import Any, Mapping, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from api.deps import get_emb_client
from api.deps_idempotency import idempotency_guard
from core.http.clients import EmbClientProtocol
from core.sse import wrap_sse_stream, format_sse
from core.sse_protocol import EVENT_META, EVENT_TOKEN, EVENT_DONE, sse_error
from core.s3_links import S3LinkFactory, S3ContentType
from core.sse_utils import sse_response
from schemas.common import ProblemDetails
import uuid
import json
from datetime import datetime

router = APIRouter(tags=["analyze"])

# Mock data for development
MOCK_ANALYZE_DOCUMENTS = [
    {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "Analysis Document 1",
        "status": "done",
        "date_upload": "2024-01-01T00:00:00Z",
        "result": {
            "summary": "Document analysis completed",
            "keywords": ["analysis", "document", "test"],
            "sentiment": "neutral"
        },
        "url_canonical_file": "https://example.com/canonical1.pdf"
    },
    {
        "id": "550e8400-e29b-41d4-a716-446655440002",
        "name": "Analysis Document 2", 
        "status": "processing",
        "date_upload": "2024-01-02T00:00:00Z",
        "result": None,
        "url_canonical_file": None
    }
]

@router.get("")
async def list_analyze_documents(
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    """List analyze documents with pagination and search"""
    # Filter by status if provided
    filtered_docs = MOCK_ANALYZE_DOCUMENTS
    if status:
        filtered_docs = [doc for doc in filtered_docs if doc["status"] == status]
    
    # Filter by search if provided
    if search:
        filtered_docs = [doc for doc in filtered_docs if search.lower() in doc["name"].lower()]
    
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
async def upload_analyze_file(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None)
):
    """Upload a file for analysis"""
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    doc_id = str(uuid.uuid4())
    doc_name = name or file.filename or f"Analysis Document {len(MOCK_ANALYZE_DOCUMENTS) + 1}"
    
    now = datetime.utcnow().isoformat() + "Z"
    
    new_doc = {
        "id": doc_id,
        "name": doc_name,
        "status": "processing",
        "date_upload": now,
        "result": None,
        "url_canonical_file": None
    }
    
    MOCK_ANALYZE_DOCUMENTS.append(new_doc)
    return {"id": doc_id, "status": "processing", "message": "File uploaded for analysis"}

@router.get("/{doc_id}")
async def get_analyze_document(doc_id: str):
    """Get a single analyze document by ID"""
    for doc in MOCK_ANALYZE_DOCUMENTS:
        if doc["id"] == doc_id:
            return doc
    raise HTTPException(status_code=404, detail="Document not found")

@router.delete("/{doc_id}")
async def delete_analyze_document(doc_id: str):
    """Delete an analyze document"""
    for i, doc in enumerate(MOCK_ANALYZE_DOCUMENTS):
        if doc["id"] == doc_id:
            MOCK_ANALYZE_DOCUMENTS.pop(i)
            return {"id": doc_id, "deleted": True}
    raise HTTPException(status_code=404, detail="Document not found")

@router.post("/{doc_id}/reanalyze")
async def reanalyze_document(doc_id: str):
    """Reanalyze a document"""
    for doc in MOCK_ANALYZE_DOCUMENTS:
        if doc["id"] == doc_id:
            doc["status"] = "processing"
            doc["result"] = None
            return {"id": doc_id, "status": "processing"}
    raise HTTPException(status_code=404, detail="Document not found")

@router.get("/{doc_id}/download")
async def download_analyze_file(
    doc_id: str,
    kind: str = Query("original", regex="^(original|canonical)$")
):
    """Download an analyze document file"""
    for doc in MOCK_ANALYZE_DOCUMENTS:
        if doc["id"] == doc_id:
            if kind == "canonical" and doc["url_canonical_file"]:
                return {"url": doc["url_canonical_file"]}
            elif kind == "original":
                return {"url": f"https://example.com/download/{doc_id}"}
            else:
                raise HTTPException(status_code=404, detail="File not found")
    raise HTTPException(status_code=404, detail="Document not found")

@router.post("/ingest/presign", dependencies=[Depends(lambda request: idempotency_guard(request, scope="analyze:ingest"))])
async def presign_ingest(request: Request, body: dict[str, Any]) -> dict:
    doc_id = str(body.get("document_id"))
    if not doc_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="missing_tenant")
    content_type = body.get("content_type", S3ContentType.OCTET)
    link = S3LinkFactory().for_document_upload(doc_id=doc_id, tenant_id=tenant_id, content_type=content_type)
    return {
        "presigned_url": link.url,
        "bucket": link.bucket,
        "key": link.key,
        "content_type": content_type,
        "expires_in": link.expires_in,
        "max_bytes": link.meta.get("max_bytes"),
    }

@router.post("/stream", dependencies=[Depends(lambda request: idempotency_guard(request, scope="analyze:stream"))])
async def analyze_stream(
    request: Request,
    body: dict[str, Any],
    emb: EmbClientProtocol = Depends(get_emb_client),
):
    texts: list[str] = body.get("texts", [])
    if not texts:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ProblemDetails(title="No texts provided", status=400).model_dump(),
            media_type="application/problem+json",
        )

    async def _gen():
        try:
            vecs = await emb.embed_texts(texts)
            yield format_sse({"chunks": len(texts), "dims": len(vecs[0]) if vecs else 0}, event=EVENT_META)
            for i, v in enumerate(vecs):
                if await request.is_disconnected():
                    break
                yield format_sse({"i": i, "norm": sum(abs(x) for x in v)}, event=EVENT_TOKEN)
            yield format_sse({"ok": True}, event=EVENT_DONE)
        except Exception as e:
            yield sse_error(str(e), status=502, title="Analyze upstream error")

    return sse_response(_gen())
