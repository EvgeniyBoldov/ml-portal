from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from app.api.deps_idempotency import idempotency_guard
from app.core.s3_links import S3LinkFactory

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])

@router.post("/presign", dependencies=[Depends(lambda request: idempotency_guard(request, scope="artifacts:put"))])
async def presign_artifact(request: Request, body: dict[str, Any]) -> dict:
    job_id = body.get("job_id")
    filename = body.get("filename")
    if not job_id or not filename:
        raise HTTPException(status_code=400, detail="job_id and filename are required")
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="missing_tenant")
    link = S3LinkFactory().for_artifact(job_id=job_id, filename=filename, tenant_id=tenant_id, content_type=body.get("content_type"))
    return {
        "presigned_url": link.url,
        "bucket": link.bucket,
        "key": link.key,
        "content_type": link.content_type,
        "expires_in": link.expires_in,
        "max_bytes": link.meta.get("max_bytes"),
    }
