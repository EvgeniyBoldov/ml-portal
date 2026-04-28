from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from app.agents.contracts import CollectionRuntimeReadiness, CollectionRuntimeStatus, ResolvedOperation


class CollectionReadinessBuilder:
    """Build canonical runtime collection readiness DTO for planner/admin surfaces."""

    def __init__(self, *, schema_stale_after_hours: int = 24) -> None:
        self._schema_stale_delta = timedelta(hours=max(1, int(schema_stale_after_hours)))

    def build(
        self,
        *,
        collection: Any,
        data_instance: Any,
        provider_instance: Optional[Any],
        operations: Sequence[ResolvedOperation],
        collection_snapshot: Optional[dict[str, Any]] = None,
    ) -> CollectionRuntimeReadiness:
        collection_type = str(getattr(collection, "collection_type", "") or "").strip().lower() or None
        schema_status = str(getattr(collection, "schema_status", "") or "").strip() or None
        last_sync_at = self._to_iso(getattr(collection, "last_sync_at", None))
        schema_freshness = self._resolve_schema_freshness(
            collection_type=collection_type,
            last_sync_at=getattr(collection, "last_sync_at", None),
            collection_snapshot=collection_snapshot or {},
        )

        op_slugs = sorted({str(op.operation_slug) for op in operations if str(op.operation_slug).strip()})
        provider_health = self._resolve_provider_health(provider_instance or data_instance)
        credential_status = self._resolve_credential_status(operations, data_instance, provider_instance)
        missing_requirements = self._resolve_missing_requirements(
            op_slugs=op_slugs,
            provider_health=provider_health,
            credential_status=credential_status,
            schema_freshness=schema_freshness,
        )
        status = self._resolve_status(
            op_slugs=op_slugs,
            provider_health=provider_health,
            credential_status=credential_status,
            schema_freshness=schema_freshness,
        )

        current_version = getattr(collection, "current_version", None)
        return CollectionRuntimeReadiness(
            collection_id=self._to_text(getattr(collection, "id", None)),
            collection_slug=self._to_text(getattr(collection, "slug", None)),
            collection_type=collection_type,
            current_version_id=self._to_text(getattr(collection, "current_version_id", None)),
            current_version=int(getattr(current_version, "version", 0) or 0) if current_version else None,
            current_version_status=self._to_text(getattr(current_version, "status", None)),
            schema_status=schema_status,
            schema_freshness=schema_freshness,
            data_instance_id=self._to_text(getattr(data_instance, "id", None)),
            data_instance_slug=self._to_text(getattr(data_instance, "slug", None)),
            provider_instance_id=self._to_text(getattr(provider_instance, "id", None)),
            provider_instance_slug=self._to_text(getattr(provider_instance, "slug", None)),
            provider_health=provider_health,
            credential_status=credential_status,
            available_operations=op_slugs,
            missing_requirements=missing_requirements,
            status=status,
            last_sync_at=last_sync_at,
        )

    @staticmethod
    def _to_text(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _to_iso(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    def _resolve_schema_freshness(
        self,
        *,
        collection_type: Optional[str],
        last_sync_at: Any,
        collection_snapshot: dict[str, Any],
    ) -> str:
        snapshot_status = str((collection_snapshot or {}).get("status") or "").strip().lower()
        if collection_type == "document":
            # Document collections are "fresh" only when retrieval pipeline is ready.
            return "fresh" if snapshot_status == "ready" else "stale"
        if collection_type == "sql":
            if not isinstance(last_sync_at, datetime):
                return "stale"
            now = datetime.now(timezone.utc)
            ts = last_sync_at if last_sync_at.tzinfo is not None else last_sync_at.replace(tzinfo=timezone.utc)
            return "fresh" if (now - ts) <= self._schema_stale_delta else "stale"
        return "fresh"

    @staticmethod
    def _resolve_provider_health(provider_instance: Any) -> str:
        raw = str(getattr(provider_instance, "health_status", "") or "").strip().lower()
        if not raw:
            return "unknown"
        if raw == "unhealthy":
            return "unhealthy"
        return "healthy"

    @staticmethod
    def _resolve_credential_status(
        operations: Sequence[ResolvedOperation],
        data_instance: Any,
        provider_instance: Optional[Any],
    ) -> str:
        if operations:
            mcp_ops = [op for op in operations if str(getattr(op, "source", "")).strip().lower() == "mcp"]
            if not mcp_ops:
                return "not_required"
            if any(not bool(getattr(op.target, "has_credentials", False)) for op in mcp_ops):
                return "missing"
            return "ok"
        instance_remote = bool(getattr(data_instance, "is_remote", False))
        provider_remote = bool(getattr(provider_instance, "is_remote", False)) if provider_instance else False
        if instance_remote or provider_remote:
            return "unknown"
        return "not_required"

    @staticmethod
    def _resolve_missing_requirements(
        *,
        op_slugs: Sequence[str],
        provider_health: str,
        credential_status: str,
        schema_freshness: str,
    ) -> list[str]:
        missing: list[str] = []
        if not op_slugs:
            missing.append("no_operations")
        if provider_health == "unhealthy":
            missing.append("provider_unhealthy")
        if credential_status == "missing":
            missing.append("missing_credentials")
        if schema_freshness == "stale":
            missing.append("schema_stale")
        return missing

    @staticmethod
    def _resolve_status(
        *,
        op_slugs: Sequence[str],
        provider_health: str,
        credential_status: str,
        schema_freshness: str,
    ) -> CollectionRuntimeStatus:
        if provider_health == "unhealthy":
            return CollectionRuntimeStatus.DEGRADED_PROVIDER_UNHEALTHY
        if credential_status == "missing":
            return CollectionRuntimeStatus.DEGRADED_MISSING_CREDENTIALS
        if schema_freshness == "stale":
            return CollectionRuntimeStatus.SCHEMA_STALE
        if not op_slugs:
            return CollectionRuntimeStatus.NO_OPERATIONS
        return CollectionRuntimeStatus.READY
