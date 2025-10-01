from __future__ import annotations
from typing import Any, Mapping
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import get_emb_client
from app.api.deps_idempotency import idempotency_guard
from app.core.http.clients import EmbClientProtocol
from app.core.sse import wrap_sse_stream, format_sse
from app.core.s3_links import S3LinkFactory, S3ContentType
from app.schemas.common import ProblemDetails

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])

@router.post("/ingest/presign", dependencies=[Depends(lambda request: idempotency_guard(request, scope="analyze:ingest"))])
async def presign_ingest(body: dict[str, Any]) -> dict:
    """Return a presigned URL for uploading a document to be analyzed."""
    doc_id = str(body.get("document_id"))
    if not doc_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    content_type = body.get("content_type", S3ContentType.OCTET)
    link = S3LinkFactory().for_document_upload(doc_id=doc_id, content_type=content_type)
    return {
        "presigned_url": link.url,
        "bucket": link.bucket,
        "key": link.key,
        "content_type": content_type,
        "expires_in": link.expires_in,
    }

@router.post("/stream", dependencies=[Depends(lambda request: idempotency_guard(request, scope="analyze:stream"))])
async def analyze_stream(
    request: Request,
    body: dict[str, Any],
    emb: EmbClientProtocol = Depends(get_emb_client),
):
    """Prototype SSE stream for analyze pipeline.
    For real pipeline you'll call embeddings/vector store/chunker.
    Here we stream back the embedding length as a simple token flow.
    """
    texts: list[str] = body.get("texts", [])
    if not texts:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ProblemDetails(title="No texts provided", status=400).model_dump(),
        )

    async def _gen():
        try:
            vecs = await emb.embed_texts(texts)
            yield format_sse({"chunks": len(texts), "dims": len(vecs[0]) if vecs else 0}, event="meta")
            for i, v in enumerate(vecs):
                if await request.is_disconnected():
                    break
                yield format_sse({"i": i, "norm": sum(abs(x) for x in v)}, event="token")
            yield format_sse({"ok": True}, event="done")
        except Exception as e:
            yield format_sse({"error": str(e)}, event="error")
    return StreamingResponse(_gen(), media_type="text/event-stream")
