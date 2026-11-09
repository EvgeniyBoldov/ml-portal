"""Read-only, run-scoped browsing of retained tool datasets."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.services.tool_result_store import get_tool_results_engine

MAX_PAGE_BYTES = 1024 * 1024


class ResultRowTooLarge(Exception):
    """One row exceeds the browser response limit."""


class SandboxResultBrowser:
    async def get_metadata(
        self, *, run_id: str, user_id: UUID, tenant_id: UUID, result_id: UUID,
    ) -> dict[str, Any] | None:
        async with get_tool_results_engine().connect() as connection:
            row = (await connection.execute(text("""
                SELECT id::text AS result_id, operation, call_id, task_id, agent_execution_id,
                       row_count, source_total, source_complete, revision, observed_schema,
                       created_at, expires_at
                FROM runtime_tool_payloads
                WHERE id=:result_id AND run_id=:run_id AND user_id=:user_id
                  AND tenant_id=:tenant_id AND expires_at > now()
            """), dict(run_id=run_id, user_id=user_id, tenant_id=tenant_id,
                       result_id=result_id))).mappings().first()
        return dict(row) if row is not None else None

    async def list_results(
        self, *, run_id: str, user_id: UUID, tenant_id: UUID,
        offset: int, limit: int, agent_execution_id: str | None = None,
    ) -> list[dict[str, Any]]:
        async with get_tool_results_engine().connect() as connection:
            rows = (await connection.execute(text("""
                SELECT id::text AS result_id, operation, call_id, task_id,
                       agent_execution_id, row_count, source_total, source_complete,
                       revision, observed_schema, created_at, expires_at
                FROM runtime_tool_payloads
                WHERE run_id=:run_id AND user_id=:user_id AND tenant_id=:tenant_id
                  AND expires_at > now()
                  AND (CAST(:agent_execution_id AS text) IS NULL OR agent_execution_id=:agent_execution_id)
                ORDER BY created_at, id OFFSET :offset LIMIT :limit
            """), dict(run_id=run_id, user_id=user_id, tenant_id=tenant_id,
                       agent_execution_id=agent_execution_id, offset=offset, limit=limit))).mappings().all()
        return [dict(row) for row in rows]

    async def read_page(
        self, *, run_id: str, user_id: UUID, tenant_id: UUID, result_id: UUID,
        offset: int, limit: int, revision: int | None,
    ) -> dict[str, Any] | None:
        scope = dict(run_id=run_id, user_id=user_id, tenant_id=tenant_id, result_id=result_id)
        async with get_tool_results_engine().begin() as connection:
            metadata = (await connection.execute(text("""
                SELECT id::text AS result_id, operation, call_id, task_id, agent_execution_id,
                       row_count, source_total, source_complete, revision, observed_schema,
                       created_at, expires_at
                FROM runtime_tool_payloads
                WHERE id=:result_id AND run_id=:run_id AND user_id=:user_id
                  AND tenant_id=:tenant_id AND expires_at > now() FOR SHARE
            """), scope)).mappings().first()
            if metadata is None:
                return None
            if revision is not None and revision != metadata["revision"]:
                raise ValueError("Dataset revision changed")
            sizes = (await connection.execute(text("""
                SELECT octet_length(data::text) FROM runtime_tool_result_rows
                WHERE result_id=:result_id AND run_id=:run_id AND ordinal>=:offset
                ORDER BY ordinal LIMIT :limit
            """), {**scope, "offset": offset, "limit": limit})).scalars().all()
            count = 0
            total_bytes = 0
            for size in sizes:
                if total_bytes + size > MAX_PAGE_BYTES:
                    if count == 0:
                        raise ResultRowTooLarge()
                    break
                total_bytes += size
                count += 1
            rows = (await connection.execute(text("""
                SELECT data FROM runtime_tool_result_rows
                WHERE result_id=:result_id AND run_id=:run_id AND ordinal>=:offset
                ORDER BY ordinal LIMIT :limit
            """), {**scope, "offset": offset, "limit": count})).scalars().all()
            next_offset = offset + len(rows)
            return {**dict(metadata), "rows": list(rows), "offset": offset,
                    "next_offset": next_offset if next_offset < metadata["row_count"] else None}
