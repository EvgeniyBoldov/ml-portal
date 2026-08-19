from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.repositories.project_memory_catalog_repository import (
    ProjectMemoryProjectRecord,
)
from app.services.project_memory_catalog_service import ProjectMemoryCatalogService


class _Repository:
    def __init__(self) -> None:
        self.tenant_id = None
        self.project_key = None

    async def list_projects(self, *, tenant_id):
        self.tenant_id = tenant_id
        return [
            ProjectMemoryProjectRecord(
                id=uuid4(),
                key="nemesis",
                name="Nemesis",
                aliases=("NMS",),
                status_counts={"confirmed": 2, "pending": 1},
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]

    async def list_project_facts(self, *, tenant_id, project_key):
        self.tenant_id = tenant_id
        self.project_key = project_key
        return None


@pytest.mark.asyncio
async def test_project_memory_catalog_projects_are_safe_projection() -> None:
    repository = _Repository()
    service = ProjectMemoryCatalogService(session=object())  # type: ignore[arg-type]
    service._repository = repository  # type: ignore[assignment]
    tenant_id = uuid4()

    projects = await service.list_projects(tenant_id=tenant_id)

    assert repository.tenant_id == tenant_id
    assert projects[0].key == "nemesis"
    assert projects[0].status_counts == {"confirmed": 2, "pending": 1}


@pytest.mark.asyncio
async def test_project_memory_catalog_normalizes_project_key_and_handles_missing_project() -> None:
    repository = _Repository()
    service = ProjectMemoryCatalogService(session=object())  # type: ignore[arg-type]
    service._repository = repository  # type: ignore[assignment]

    detail = await service.get_project(tenant_id=uuid4(), project_key="  NEMESIS  ")

    assert detail is None
    assert repository.project_key == "nemesis"
