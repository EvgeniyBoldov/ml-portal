"""Models API endpoints (New Architecture)

CRUD operations for LLM and Embedding models.
No file system scanning - models are added manually.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_uow, get_current_user, require_admin
from app.core.security import UserCtx
from app.services.model_service import ModelService
from app.models.model_registry import Model, HealthStatus
from app.schemas.model_registry import (
    Model as ModelSchema,
    ModelCreate,
    ModelUpdate,
    ModelListResponse,
    ModelTypeEnum,
    ModelStatusEnum,
    HealthCheckRequest,
    HealthCheckResponse,
)
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["models"])


def _map_modality_to_model_type(modality: str | None) -> Optional[str]:
    raw = str(modality or "").strip().lower()
    if not raw:
        return None
    if "embed" in raw or raw == "text":
        return "embedding"
    if "rerank" in raw:
        return "reranker"
    if "chat" in raw or "llm" in raw or "text" in raw:
        return "llm_chat"
    return None


async def _probe_manifest(base_url: str) -> Tuple[Dict[str, Any], str]:
    normalized = base_url.rstrip("/")
    health_status = "unavailable"
    health_payload: Dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            health = await client.get(f"{normalized}/health")
            if health.status_code == 200:
                health_status = "healthy"
                if health.headers.get("content-type", "").startswith("application/json"):
                    health_payload = health.json()
        except Exception:
            health_status = "unavailable"

        resp = await client.get(f"{normalized}/models")
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            raise ValueError("models_manifest_empty")
        first = data[0] or {}
        if not isinstance(first, dict):
            raise ValueError("models_manifest_invalid")
        first["_health"] = health_payload
        return first, health_status


def _resolve_connector(model: Model) -> str:
    connector = getattr(model, "connector", None)
    if connector:
        return connector

    provider = (model.provider or "").lower()
    model_type = model.type.value if hasattr(model.type, "value") else str(model.type)
    if provider == "local" and model_type == "embedding":
        return "local_emb_http"
    if provider == "local" and model_type == "reranker":
        return "local_rerank_http"
    if provider == "local" and model_type == "llm_chat":
        return "local_llm_http"
    if provider == "azure":
        return "azure_openai_http"
    return "openai_http"


def _resolve_base_url(model: Model) -> Optional[str]:
    if getattr(model, "base_url", None):
        return model.base_url
    state = inspect(model)
    if "instance" not in state.unloaded and model.instance is not None and getattr(model.instance, "url", None):
        return model.instance.url
    if model.extra_config and model.extra_config.get("base_url"):
        return model.extra_config.get("base_url")
    return None


def serialize_model(model: Model) -> Dict[str, Any]:
    """Serialize Model ORM object to dict for API response"""
    state = inspect(model)
    instance_name: Optional[str] = None
    if "instance" not in state.unloaded and model.instance is not None:
        instance_name = model.instance.name

    def _enum_value(value: Any) -> Any:
        if value is None:
            return None
        return value.value if hasattr(value, "value") else value

    return {
        "id": str(model.id),
        "alias": model.alias,
        "name": model.name,
        "type": _enum_value(model.type),
        "provider": model.provider,
        "connector": _resolve_connector(model),
        "provider_model_name": model.provider_model_name,
        "base_url": _resolve_base_url(model),
        "instance_id": str(model.instance_id) if model.instance_id else None,
        "instance_name": instance_name,
        "extra_config": model.extra_config,
        "status": _enum_value(model.status),
        "enabled": model.enabled,
        "is_system": model.is_system,
        "default_for_type": model.default_for_type,
        "model_version": model.model_version,
        "description": model.description,
        "last_health_check_at": model.last_health_check_at,
        "health_status": _enum_value(model.health_status),
        "health_error": model.health_error,
        "health_latency_ms": model.health_latency_ms,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
        "deleted_at": model.deleted_at,
    }


async def _load_embedding_usage_rows(session: AsyncSession, model_alias: str) -> list[dict[str, Any]]:
    params = {"model_alias": model_alias}
    membership_sql = text(
        """
        SELECT
          c.id AS collection_id,
          c.name AS collection_name,
          c.slug AS collection_slug,
          c.tenant_id AS tenant_id,
          t.name AS tenant_name,
          t.is_active AS tenant_active,
          COUNT(DISTINCT rd.id) AS total_docs,
          COUNT(DISTINCT CASE WHEN rs.status = 'completed' THEN rd.id END) AS vectorized_docs
        FROM collections c
        JOIN tenants t ON t.id = c.tenant_id
        LEFT JOIN document_collection_memberships dcm ON dcm.collection_id = c.id
        LEFT JOIN ragdocuments rd ON rd.id = dcm.source_id
        LEFT JOIN rag_statuses rs
          ON rs.doc_id = rd.id
         AND rs.node_type = 'embedding'
         AND rs.node_key = :model_alias
         AND rs.status = 'completed'
        WHERE c.collection_type = 'document'
        GROUP BY c.id, c.name, c.slug, c.tenant_id, t.name, t.is_active
        ORDER BY t.name, c.name
        """
    )
    fallback_sql = text(
        """
        WITH source_docs AS (
          SELECT
            rd.id AS doc_id,
            s.tenant_id AS tenant_id,
            COALESCE(s.meta #>> '{collection,id}', s.meta ->> 'collection_id') AS collection_id_text
          FROM ragdocuments rd
          JOIN sources s ON s.source_id = rd.id
        )
        SELECT
          c.id AS collection_id,
          c.name AS collection_name,
          c.slug AS collection_slug,
          c.tenant_id AS tenant_id,
          t.name AS tenant_name,
          t.is_active AS tenant_active,
          COUNT(DISTINCT sd.doc_id) AS total_docs,
          COUNT(DISTINCT CASE WHEN rs.status = 'completed' THEN sd.doc_id END) AS vectorized_docs
        FROM collections c
        JOIN tenants t ON t.id = c.tenant_id
        LEFT JOIN source_docs sd
          ON sd.collection_id_text = c.id::text
        LEFT JOIN rag_statuses rs
          ON rs.doc_id = sd.doc_id
         AND rs.node_type = 'embedding'
         AND rs.node_key = :model_alias
         AND rs.status = 'completed'
        WHERE c.collection_type = 'document'
        GROUP BY c.id, c.name, c.slug, c.tenant_id, t.name, t.is_active
        ORDER BY t.name, c.name
        """
    )
    try:
        result = await session.execute(membership_sql, params)
    except ProgrammingError as exc:
        message = str(getattr(exc, "orig", exc)).lower()
        if "document_collection_memberships" not in message or "does not exist" not in message:
            raise
        result = await session.execute(fallback_sql, params)

    rows: list[dict[str, Any]] = []
    for row in result.mappings().all():
        total = int(row.get("total_docs") or 0)
        vectorized = int(row.get("vectorized_docs") or 0)
        rows.append(
            {
                "collection_id": str(row["collection_id"]),
                "collection_name": str(row["collection_name"] or ""),
                "collection_slug": str(row["collection_slug"] or ""),
                "tenant_id": str(row["tenant_id"]),
                "tenant_name": str(row["tenant_name"] or ""),
                "tenant_active": bool(row["tenant_active"]),
                "total_docs": total,
                "vectorized_docs": vectorized,
                "not_vectorized_docs": max(total - vectorized, 0),
            }
        )
    return rows


@router.post("/probe-info")
async def probe_model_info(
    payload: Dict[str, Any],
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    base_url = str(payload.get("base_url") or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url is required")

    try:
        first, health_status = await _probe_manifest(base_url)
        return {
            "provider_model_name": str(first.get("alias") or first.get("name") or ""),
            "model_version": str(first.get("version") or ""),
            "model_type": _map_modality_to_model_type(str(first.get("modality") or "")),
            "health_status": health_status,
            "raw": first,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Probe failed: {exc}")


@router.post("/{model_id}/verify")
async def verify_model(
    model_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    try:
        service = ModelService(session)
        model = await service.get_by_id(uuid.UUID(model_id))
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        base_url = _resolve_base_url(model)
        if not base_url:
            raise HTTPException(status_code=400, detail="Model has no base_url/instance URL")

        manifest, health_status = await _probe_manifest(base_url)
        model_type = _map_modality_to_model_type(str(manifest.get("modality") or ""))
        update_data: Dict[str, Any] = {
            "provider_model_name": str(manifest.get("alias") or manifest.get("name") or model.provider_model_name),
            "model_version": str(manifest.get("version") or model.model_version or ""),
        }
        if model_type:
            update_data["type"] = model_type

        extra = dict(model.extra_config or {})
        if manifest.get("dimensions") is not None:
            try:
                extra["vector_dim"] = int(manifest.get("dimensions"))
            except Exception:
                pass
        if manifest.get("max_tokens") is not None:
            try:
                extra["max_tokens"] = int(manifest.get("max_tokens"))
            except Exception:
                pass
        extra["manifest"] = manifest
        update_data["extra_config"] = extra

        updated = await service.update_model(model.id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Model not found")

        hs = HealthStatus.HEALTHY if health_status == "healthy" else HealthStatus.UNAVAILABLE
        await service.update_health_status(updated.id, hs, latency_ms=None, error=None if health_status == "healthy" else "verify_failed")
        if health_status == "healthy":
            await service.update_model(updated.id, {"status": "available"})
        else:
            await service.update_model(updated.id, {"status": "unavailable"})

        refreshed = await service.get_by_id(updated.id)
        payload = serialize_model(refreshed)
        payload["manifest"] = manifest
        payload["resolved_type_from_manifest"] = model_type
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to verify model: {exc}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Verify failed: {exc}")


@router.get("/{model_id}/embedding-usage")
async def get_embedding_usage(
    model_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user=Depends(require_admin),
):
    try:
        service = ModelService(session)
        model = await service.get_by_id(uuid.UUID(model_id))
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        model_type = model.type.value if hasattr(model.type, "value") else str(model.type)
        if model_type != "embedding":
            raise HTTPException(status_code=400, detail="Embedding usage is available only for embedding models")

        rows = await _load_embedding_usage_rows(session, model.alias)

        tenants_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            tid = row["tenant_id"]
            entry = tenants_map.setdefault(
                tid,
                {
                    "tenant_id": tid,
                    "tenant_name": row["tenant_name"],
                    "tenant_active": row["tenant_active"],
                    "collection_count": 0,
                    "total_docs": 0,
                    "vectorized_docs": 0,
                    "not_vectorized_docs": 0,
                },
            )
            entry["collection_count"] += 1
            entry["total_docs"] += row["total_docs"]
            entry["vectorized_docs"] += row["vectorized_docs"]
            entry["not_vectorized_docs"] += row["not_vectorized_docs"]

        tenants = sorted(tenants_map.values(), key=lambda x: str(x["tenant_name"]).lower())
        collections = [
            {
                "collection_id": row["collection_id"],
                "collection_name": row["collection_name"],
                "collection_slug": row["collection_slug"],
                "tenant_id": row["tenant_id"],
                "tenant_name": row["tenant_name"],
                "total_docs": row["total_docs"],
                "vectorized_docs": row["vectorized_docs"],
                "not_vectorized_docs": row["not_vectorized_docs"],
            }
            for row in rows
        ]

        return {
            "model_id": str(model.id),
            "model_alias": model.alias,
            "tenants": tenants,
            "collections": collections,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to load embedding usage: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load embedding usage: {exc}")


@router.get("", response_model=ModelListResponse)
async def list_models(
    type: Optional[str] = Query(None, description="Filter by type (llm_chat, embedding)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    enabled_only: bool = Query(False, description="Show only enabled models"),
    search: Optional[str] = Query(None, description="Search by alias, name, or provider model"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """List models with filtering and pagination"""
    try:
        service = ModelService(session)
        
        # Parse enum filters
        type_filter = ModelTypeEnum(type) if type else None
        status_filter = ModelStatusEnum(status) if status else None
        
        models = await service.list_models(
            type=type_filter,
            status=status_filter,
            enabled_only=enabled_only,
            search=search
        )
        
        total = len(models)
        start = (page - 1) * size
        end = start + size
        items = models[start:end]
        
        return {
            "items": [serialize_model(m) for m in items],
            "total": total,
            "page": page,
            "size": size,
            "has_more": end < total,
        }
    except Exception as e:
        logger.error(f"Failed to list models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list models: {str(e)}")


@router.post("", response_model=ModelSchema, status_code=status.HTTP_201_CREATED)
async def create_model(
    payload: ModelCreate,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Create a new model"""
    try:
        service = ModelService(session)
        model = await service.create_model(payload.model_dump())
        return serialize_model(model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create model: {str(e)}")


@router.get("/{model_id}", response_model=ModelSchema)
async def get_model(
    model_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Get model by ID"""
    try:
        service = ModelService(session)
        model = await service.get_by_id(uuid.UUID(model_id))
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return serialize_model(model)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get model: {str(e)}")


@router.patch("/{model_id}", response_model=ModelSchema)
async def update_model(
    model_id: str,
    payload: ModelUpdate,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Update model"""
    try:
        service = ModelService(session)
        data = payload.model_dump(exclude_unset=True)
        model = await service.update_model(uuid.UUID(model_id), data)
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return serialize_model(model)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update model: {str(e)}")


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Delete model (soft delete)"""
    try:
        service = ModelService(session)
        ok = await service.delete_model(uuid.UUID(model_id))
        
        if not ok:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return None
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {str(e)}")


@router.post("/health-check-all")
async def health_check_all_models(
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Perform health check on all enabled models
    
    Returns summary of health check results.
    """
    try:
        from app.services.model_health_checker import get_health_checker
        
        service = ModelService(session)
        models = await service.list_models(enabled_only=True)
        
        health_checker = get_health_checker()
        results = []
        
        for model in models:
            result = await health_checker.check_model(model, session=session)
            await service.update_health_status(
                model.id,
                result.status,
                latency_ms=result.latency_ms,
                error=result.error
            )
            results.append({
                "model_id": str(model.id),
                "alias": model.alias,
                "status": result.status.value,
                "latency_ms": result.latency_ms,
                "error": result.error
            })
        
        healthy = sum(1 for r in results if r["status"] == "healthy")
        
        return {
            "total": len(results),
            "healthy": healthy,
            "unhealthy": len(results) - healthy,
            "results": results
        }
    except Exception as e:
        logger.error(f"Failed to health check all models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to health check models: {str(e)}")


@router.post("/{model_id}/health-check", response_model=HealthCheckResponse)
async def health_check_model(
    model_id: str,
    request: HealthCheckRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    admin_user = Depends(require_admin),
):
    """Perform health check on model
    
    Calls the actual provider to verify model availability.
    Updates model status based on result.
    """
    try:
        from app.services.model_health_checker import get_health_checker
        
        service = ModelService(session)
        model = await service.get_by_id(uuid.UUID(model_id))
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        # Perform actual health check
        health_checker = get_health_checker()
        result = await health_checker.check_model(model, session=session)
        
        # Update model health status in DB
        await service.update_health_status(
            model.id,
            result.status,
            latency_ms=result.latency_ms,
            error=result.error
        )
        
        return {
            "model_id": str(model.id),
            "alias": model.alias,
            "status": result.status.value,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "checked_at": datetime.now(timezone.utc)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to health check model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to health check model: {str(e)}")
