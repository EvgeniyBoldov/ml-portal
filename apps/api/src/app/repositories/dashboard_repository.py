"""Bounded SQL aggregates for the platform overview (never loads trace payloads)."""
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.model_registry import Model
from app.models.orchestration_settings import OrchestrationSettings
from app.models.platform_usage import PlatformUsageCoverage
from app.models.system_llm_role import SystemLLMRole


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in (await self.session.execute(text(sql), params)).mappings()]

    async def coverage(self) -> datetime:
        return (await self.session.execute(select(PlatformUsageCoverage.started_at)
            .where(PlatformUsageCoverage.id == 1))).scalar_one()

    async def summary(self, start: datetime, end: datetime) -> dict[str, Any]:
        rows = await self.rows("""
            SELECT count(*) FILTER (WHERE kind='run') AS requests,
                count(*) FILTER (WHERE kind='run' AND origin='chat') AS chat_requests,
                count(*) FILTER (WHERE kind='run' AND origin='shadow') AS shadow_requests,
                count(DISTINCT user_id) FILTER (WHERE kind='run') AS active_users,
                count(DISTINCT agent_slug) FILTER (WHERE kind='agent') AS active_agents,
                count(*) FILTER (WHERE kind='run' AND status='failed') AS failed_requests,
                count(*) FILTER (WHERE kind='run' AND status='completed') AS completed_requests
            FROM platform_usage
            WHERE origin IN ('chat','shadow') AND started_at >= :start AND started_at < :end
        """, start=start, end=end)
        return rows[0]

    async def timeline(self, start: datetime, end: datetime, hourly: bool) -> list[dict[str, Any]]:
        return await self.rows("""
            SELECT date_trunc(:grain, started_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS at,
                count(*) AS requests, count(*) FILTER (WHERE status='failed') AS errors
            FROM platform_usage WHERE kind='run' AND origin IN ('chat','shadow')
                AND started_at >= :start AND started_at < :end GROUP BY 1 ORDER BY 1
        """, start=start, end=end, grain="hour" if hourly else "day")

    async def model_usage(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return await self.rows("""
            SELECT model_alias AS alias, count(*) AS calls,
                count(*) FILTER (WHERE error_code IS NOT NULL OR status IN ('failed','waiting_retry')) AS errors,
                sum(tokens_in) AS tokens_in, sum(tokens_out) AS tokens_out,
                count(*) FILTER (WHERE token_source='estimate') AS estimated_calls,
                count(*) FILTER (WHERE tokens_in IS NOT NULL OR tokens_out IS NOT NULL) AS metered_calls,
                avg(duration_ms) FILTER (WHERE finished_at IS NOT NULL) AS avg_duration_ms
            FROM platform_usage WHERE kind='llm' AND origin IN ('chat','shadow')
                AND started_at >= :start AND started_at < :end GROUP BY model_alias ORDER BY calls DESC
        """, start=start, end=end)

    async def agents(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return await self.rows("""
            SELECT u.agent_slug AS slug, a.id::text AS id, coalesce(a.name,u.agent_slug) AS name,
                u.origin, count(*) AS executions, count(DISTINCT u.user_id) AS users,
                count(*) FILTER (WHERE u.status='failed') AS errors,
                avg(extract(epoch FROM (u.finished_at-u.started_at))*1000)
                    FILTER (WHERE u.finished_at IS NOT NULL) AS avg_duration_ms
            FROM platform_usage u LEFT JOIN agents a ON a.slug=u.agent_slug
            WHERE u.kind='agent' AND u.origin IN ('chat','shadow')
                AND u.started_at >= :start AND u.started_at < :end
            GROUP BY u.agent_slug,a.id,a.name,u.origin ORDER BY executions DESC,u.agent_slug
        """, start=start, end=end)

    async def catalog(self) -> tuple[list[Model], list[Agent], list[SystemLLMRole], OrchestrationSettings | None]:
        models = list((await self.session.scalars(select(Model).where(Model.deleted_at.is_(None))
            .order_by(Model.alias))).unique())
        agents = list((await self.session.scalars(select(Agent).where(Agent.lifecycle_status == "active"))))
        roles = list((await self.session.scalars(select(SystemLLMRole).where(SystemLLMRole.is_active.is_(True)))))
        settings = await self.session.scalar(select(OrchestrationSettings).limit(1))
        return models, agents, roles, settings

    async def collections(self) -> list[dict[str, Any]]:
        return await self.rows("""
            WITH chunk_counts AS (SELECT source_id,count(*) AS count FROM chunks GROUP BY source_id),
            embeddings AS (SELECT m.collection_id,array_agg(DISTINCT r.node_key ORDER BY r.node_key) AS models
                FROM document_collection_memberships m JOIN rag_statuses r ON r.doc_id=m.source_id
                JOIN ragdocuments d ON d.id=m.source_id AND d.status!='archived'
                WHERE r.node_type='embedding' GROUP BY m.collection_id)
            SELECT c.id::text AS id,c.slug,c.name,count(d.id) AS documents,
                coalesce(sum(coalesce(d.size_bytes,d.size)),0) AS source_bytes,
                count(d.id) FILTER (WHERE coalesce(d.size_bytes,d.size) IS NULL) AS unknown_sizes,
                coalesce(sum(cc.count),0) AS chunks,
                count(d.id) FILTER (WHERE coalesce(d.agg_status,d.status::text) IN ('ready','done','completed','indexed')) AS ready,
                count(d.id) FILTER (WHERE coalesce(d.agg_status,d.status::text) IN ('failed','error')) AS failed,
                count(d.id) FILTER (WHERE d.agg_status='partial') AS partial,
                count(d.id) FILTER (WHERE coalesce(d.agg_status,d.status::text) NOT IN
                    ('ready','done','completed','indexed','failed','error','partial')) AS processing,
                coalesce(e.models,'{}') AS embedding_models
            FROM collections c
            LEFT JOIN document_collection_memberships m ON m.collection_id=c.id
            LEFT JOIN ragdocuments d ON d.id=m.source_id AND d.status!='archived'
            LEFT JOIN chunk_counts cc ON cc.source_id=d.id
            LEFT JOIN embeddings e ON e.collection_id=c.id
            WHERE c.collection_type='document' AND c.lifecycle_status='active'
            GROUP BY c.id,c.slug,c.name,e.models ORDER BY source_bytes DESC,c.name
        """)

    async def memory_scopes(self, cutoff: datetime) -> list[dict[str, Any]]:
        return await self.rows("""
            WITH latest AS (SELECT DISTINCT ON (document_id) document_id,status,action,updated_at
                FROM long_memory_document_operations ORDER BY document_id,generation DESC)
            SELECT s.key,s.name,
                count(d.id) FILTER (WHERE l.document_id IS NOT NULL AND l.action!='delete') AS documents,
                count(d.id) FILTER (WHERE l.status IN ('pending','processing','running')) AS pending,
                count(d.id) FILTER (WHERE l.status='failed') AS failed,
                count(d.id) FILTER (WHERE l.status IN ('pending','processing','running') AND l.updated_at < :cutoff) AS stalled
            FROM memory_scopes s LEFT JOIN document_memory_scopes b ON b.scope_id=s.id
            LEFT JOIN ragdocuments d ON d.id=b.document_id AND d.status!='archived'
            LEFT JOIN latest l ON l.document_id=d.id
            WHERE s.lifecycle_status='active' GROUP BY s.key,s.name ORDER BY s.name
        """, cutoff=cutoff)

    async def connectors(self) -> list[dict[str, Any]]:
        return await self.rows("""SELECT id::text,name,health_status,updated_at
            FROM tool_instances WHERE is_active
                AND health_status IN ('unhealthy','unavailable','degraded') ORDER BY name""")

    async def stalled_documents(self, cutoff: datetime) -> list[dict[str, Any]]:
        return await self.rows("""
            SELECT m.collection_id::text AS id,c.slug,c.name,count(DISTINCT d.id) AS count,max(d.updated_at) AS last_at
            FROM ragdocuments d JOIN document_collection_memberships m ON m.source_id=d.id
            JOIN collections c ON c.id=m.collection_id
            WHERE coalesce(d.agg_status,d.status::text) IN ('processing','running','queued','pending')
                AND coalesce(d.updated_at,d.created_at) < :cutoff AND c.lifecycle_status='active'
            GROUP BY m.collection_id,c.slug,c.name
        """, cutoff=cutoff)

    async def repeated_errors(self, start: datetime, end: datetime, threshold: int) -> list[dict[str, Any]]:
        return await self.rows("""
            WITH errors AS (
                SELECT model_alias,error_code,count(*) AS count,max(finished_at) AS last_at
                FROM platform_usage WHERE kind='llm' AND origin IN ('chat','shadow')
                    AND started_at >= :start AND started_at < :end AND error_code IS NOT NULL
                GROUP BY model_alias,error_code HAVING count(*) >= :threshold
            )
            SELECT coalesce(e.model_alias,'default') AS model,e.error_code,e.count,e.last_at FROM errors e
            WHERE NOT EXISTS (SELECT 1 FROM platform_usage s WHERE s.kind='llm'
                AND s.origin IN ('chat','shadow') AND s.model_alias IS NOT DISTINCT FROM e.model_alias
                AND s.status='completed' AND s.error_code IS NULL AND s.finished_at > e.last_at
                AND s.started_at < :end)
            ORDER BY e.count DESC LIMIT 20
        """, start=start, end=end, threshold=threshold)

    async def failed_agents(self, start: datetime, end: datetime, threshold: int) -> list[dict[str, Any]]:
        return await self.rows("""
            WITH failures AS (
                SELECT agent_slug,count(*) AS count,max(finished_at) AS last_at
                FROM platform_usage WHERE kind='agent' AND origin IN ('chat','shadow')
                    AND started_at >= :start AND started_at < :end AND status='failed'
                GROUP BY agent_slug HAVING count(*) >= :threshold
            )
            SELECT f.* FROM failures f WHERE NOT EXISTS (SELECT 1 FROM platform_usage s
                WHERE s.kind='agent' AND s.origin IN ('chat','shadow') AND s.agent_slug=f.agent_slug
                    AND s.status='completed' AND s.finished_at > f.last_at AND s.started_at < :end)
            ORDER BY f.count DESC LIMIT 20
        """, start=start, end=end, threshold=threshold)
