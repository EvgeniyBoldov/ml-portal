from __future__ import annotations
from typing import Any, Mapping
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from app.api.deps import get_emb_client
from app.api.deps_idempotency import idempotency_guard
from app.core.http.clients import EmbClientProtocol
from app.core.sse import wrap_sse_stream, format_sse
from app.core.sse_protocol import EVENT_META, EVENT_TOKEN, EVENT_DONE, sse_error
from app.core.s3_links import S3LinkFactory, S3ContentType
from app.core.sse_utils import sse_response
from app.schemas.common import ProblemDetails

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])

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
