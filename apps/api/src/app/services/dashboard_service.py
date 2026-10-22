"""Compose usage history and current operational state for platform administrators."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import (
    DashboardModel, DashboardProblem, DashboardResponse, UsageSummary,
)
from app.services.hipporag_service import HippoRAGService


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _summary(row: dict) -> UsageSummary:
    total = row["completed_requests"] + row["failed_requests"]
    return UsageSummary(**row, error_rate=round(100 * row["failed_requests"] / total, 1) if total else None)


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = DashboardRepository(session)
        self.hipporag = HippoRAGService(session)

    async def overview(self, days: Literal[1, 7, 30]) -> DashboardResponse:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        repo = self.repository
        settings = get_settings()
        coverage = await repo.coverage()
        current = _summary(await repo.summary(start, now))
        previous = _summary(await repo.summary(start - timedelta(days=days), start))
        buckets = {row["at"]: row for row in await repo.timeline(start, now, days == 1)}
        cursor = start.replace(minute=0, second=0, microsecond=0)
        if days != 1:
            cursor = cursor.replace(hour=0)
        step = timedelta(hours=1) if days == 1 else timedelta(days=1)
        timeline = []
        while cursor < now:
            timeline.append(buckets.get(cursor, {"at": cursor, "requests": 0, "errors": 0}))
            cursor += step

        catalog, agents, roles, orchestration = await repo.catalog()
        defaults = {_value(model.type): model.alias for model in catalog if model.enabled and model.default_for_type}
        assignments: dict[str, list[str]] = {}

        def assign(alias: str | None, label: str) -> None:
            if alias:
                assignments.setdefault(alias, []).append(label)

        default_llm = defaults.get("llm_chat")
        executor_model = (orchestration.executor_model if orchestration else None) or default_llm
        for role in roles:
            # Historical roles remain in the catalog, but do not execute in the
            # active pipeline and must not imply a live runtime dependency.
            if role.role_type not in {"memory", "document_memory_extractor", "memory_evaluator"}:
                assign(role.model or default_llm, f"Роль: {role.role_type}")
        for agent in agents:
            assign(agent.model or executor_model, f"Агент: {agent.name}")
        for model in catalog:
            if model.default_for_type:
                assign(model.alias, "По умолчанию")
            if model.use_for_long_memory:
                assign(model.alias, "HippoRAG: embedding")
        assign(default_llm, "HippoRAG: извлечение")

        usage = {row["alias"] or "unresolved": row for row in await repo.model_usage(start, now)}
        collections = await repo.collections()
        for collection in collections:
            for alias in collection["embedding_models"]:
                assign(alias, f"RAG: {collection['name']}")
        models: list[DashboardModel] = []
        for model in catalog:
            recent = model.last_health_check_at and (now - model.last_health_check_at).total_seconds() <= settings.DASHBOARD_HEALTH_STALE_SECONDS
            model_usage = dict(usage.pop(model.alias, {}))
            model_usage.pop("alias", None)
            models.append(DashboardModel(
                alias=model.alias, id=str(model.id), name=model.name, type=_value(model.type),
                enabled=model.enabled, health=_value(model.health_status) if recent and model.health_status else "unknown",
                checked_at=model.last_health_check_at, assignments=assignments.get(model.alias, []), **model_usage,
            ))
        for alias, row in usage.items():
            models.append(DashboardModel(**{**row, "alias": alias}, name="Модель не определена" if alias == "unresolved" else alias,
                type="llm_chat", enabled=False, health="unknown"))
        models.sort(key=lambda model: (-model.calls, -len(model.assignments), model.alias))

        memory_scopes = await repo.memory_scopes(now - timedelta(seconds=settings.DASHBOARD_STALLED_DOCUMENT_SECONDS))
        memory_available = True
        try:
            memory_snapshot = await self.hipporag.corpus_statistics()
            snapshots = {row["scope_slug"]: row for row in memory_snapshot["scopes"]}
        except Exception:
            memory_available = False
            snapshots = {}
        for scope in memory_scopes:
            snapshot = snapshots.get(scope["key"])
            if snapshot:
                scope.update({key: snapshot.get(key) for key in ("status", "nodes", "edges", "indexed_at")})
                scope["documents"] = snapshot["documents"]
            else:
                scope["status"] = "absent" if memory_available else "unknown"

        problems: list[DashboardProblem] = []
        for model in models:
            if model.assignments and (not model.enabled or model.health in {"unavailable", "unhealthy", "degraded"}):
                problems.append(DashboardProblem(key=f"model:{model.alias}", severity="danger",
                    title=f"Модель {model.name} недоступна" if not model.enabled or model.health != "degraded" else f"Модель {model.name}: сбой проверки",
                    detail=f"Назначений: {len(model.assignments)}", last_at=model.checked_at,
                    href=f"/admin/platform/models/{model.id}" if model.id else "/admin/platform/models"))
        for connector in await repo.connectors():
            problems.append(DashboardProblem(key=f"connector:{connector['id']}", severity="danger",
                title=f"Подключение {connector['name']}: сбой проверки", detail="Проверьте доступность подключения",
                last_at=connector["updated_at"], href=f"/admin/connectors/{connector['id']}"))
        for collection in collections:
            if collection["failed"] or collection["partial"]:
                problems.append(DashboardProblem(key=f"rag:{collection['id']}", severity="warning",
                    title=f"Проблемы индексации: {collection['name']}", detail="Есть ошибки или частично готовые индексы",
                    count=collection["failed"] + collection["partial"], href=f"/admin/collections/{quote(collection['slug'], safe='')}"))
        for scope in memory_scopes:
            if scope["failed"] or (scope["documents"] and scope["status"] == "absent" and not scope["pending"]):
                problems.append(DashboardProblem(key=f"memory:{scope['key']}", severity="warning",
                    title=f"Память: {scope['name']}", detail="Есть ошибки обработки" if scope["failed"] else "Готовый индекс отсутствует",
                    count=scope["failed"] or 1, href="/admin/memory"))
            if scope["stalled"]:
                problems.append(DashboardProblem(key=f"memory-stalled:{scope['key']}", severity="warning",
                    title=f"Долго обновляется память: {scope['name']}", detail="Нет обновлений состояния дольше установленного порога",
                    count=scope["stalled"], href="/admin/memory"))
        if memory_scopes and not memory_available:
            problems.append(DashboardProblem(key="memory:unavailable", severity="warning",
                title="Не удалось получить состояние HippoRAG", detail="Готовность графов неизвестна", href="/admin/memory"))
        for row in await repo.stalled_documents(now - timedelta(seconds=settings.DASHBOARD_STALLED_DOCUMENT_SECONDS)):
            problems.append(DashboardProblem(key=f"stalled:{row['id']}", severity="warning",
                title=f"Долго обрабатываются документы: {row['name']}", detail="Нет обновлений состояния дольше установленного порога",
                count=row["count"], last_at=row["last_at"], href=f"/admin/collections/{quote(row['slug'], safe='')}"))
        for row in await repo.repeated_errors(start, now, settings.DASHBOARD_REPEATED_ERROR_THRESHOLD):
            problems.append(DashboardProblem(key=f"errors:{row['model']}:{row['error_code']}", severity="warning",
                title=f"{row['model']}: {row['error_code']}", detail="Повторяющиеся ошибки модели за выбранный период",
                count=row["count"], last_at=row["last_at"], href="/admin/agent-runs"))
        by_slug = {agent.slug: agent for agent in agents}
        for row in await repo.failed_agents(start, now, settings.DASHBOARD_REPEATED_ERROR_THRESHOLD):
            agent = by_slug.get(row["agent_slug"])
            problems.append(DashboardProblem(key=f"agent-errors:{row['agent_slug']}", severity="warning",
                title=f"Неуспешные запуски: {agent.name if agent else row['agent_slug']}",
                detail="Повторяющиеся ошибки выполнения агента",
                count=row["count"], last_at=row["last_at"],
                href=f"/admin/agents/{agent.id}" if agent else "/admin/agent-runs"))
        problems.sort(key=lambda item: (item.severity != "danger", -item.count, item.key))
        return DashboardResponse(days=days, generated_at=now, period_start=start, coverage_started_at=coverage,
            current=current, previous=previous, timeline=timeline, models=models,
            agents=await repo.agents(start, now), collections=collections, memory_scopes=memory_scopes,
            memory_available=memory_available, problems=problems)
