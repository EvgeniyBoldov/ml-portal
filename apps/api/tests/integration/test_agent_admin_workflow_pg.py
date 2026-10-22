"""Real PostgreSQL coverage for agent admin CRUD and version lifecycle endpoints."""
import os
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.api.deps import db_session, require_admin
from app.api.v1.routers.admin import agents as agents_router
from app.core.config import get_settings

pytestmark = pytest.mark.skipif(
    os.getenv("AGENT_ADMIN_PG") != "1", reason="requires opt-in PostgreSQL"
)


@pytest.mark.asyncio
async def test_agent_admin_create_list_edit_publish_archive_delete_workflow():
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    agent_slug = f"agent-admin-pg-{uuid4().hex}"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    app = FastAPI()
                    app.include_router(agents_router.router, prefix="/admin/agents")
                    app.dependency_overrides[db_session] = lambda: session
                    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}

                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        created_response = await client.post("/admin/agents", json={
                            "slug": agent_slug,
                            "name": "Agent admin integration",
                            "model": "llm.admin-test",
                            "temperature": 0.35,
                            "requires_confirmation_for_write": True,
                            "risk_level": "high",
                        })
                        assert created_response.status_code == 201, created_response.text
                        agent_id = created_response.json()["id"]

                        listing = await client.get("/admin/agents")
                        assert listing.status_code == 200, listing.text
                        item = next(row for row in listing.json() if row["id"] == agent_id)
                        assert item["model"] == "llm.admin-test"
                        assert item["temperature"] == 0.35
                        assert item["requires_confirmation_for_write"] is True
                        assert item["risk_level"] == "high"

                        created_version = await client.post(
                            f"/admin/agents/{agent_id}/versions",
                            json={
                                "mission": "Initial mission",
                                "planner_short_info": "Find exact records",
                                "task_contracts": [{"name": "lookup", "inputs": ["id"]}],
                                "supports_dynamic_contracts": False,
                                "requires_fresh_retrieval": True,
                            },
                        )
                        assert created_version.status_code == 201, created_version.text
                        version_number = created_version.json()["version"]
                        assert created_version.json()["task_contracts"] == [
                            {"name": "lookup", "inputs": ["id"]}
                        ]

                        updated = await client.patch(
                            f"/admin/agents/{agent_id}/versions/{version_number}",
                            json={
                                "task_contracts": [{"name": "lookup", "inputs": ["record_id"]}],
                                "supports_dynamic_contracts": True,
                                "requires_fresh_retrieval": False,
                            },
                        )
                        assert updated.status_code == 200, updated.text
                        assert updated.json()["task_contracts"][0]["inputs"] == ["record_id"]
                        assert updated.json()["supports_dynamic_contracts"] is True
                        assert updated.json()["requires_fresh_retrieval"] is False

                        published = await client.post(
                            f"/admin/agents/{agent_id}/versions/{version_number}/publish"
                        )
                        assert published.status_code == 200, published.text
                        assert published.json()["status"] == "published"

                        set_current = await client.put(
                            f"/admin/agents/{agent_id}/current-version",
                            params={"version_id": published.json()["id"]},
                        )
                        assert set_current.status_code == 200, set_current.text
                        assert set_current.json()["current_version_id"] == published.json()["id"]

                        archived = await client.post(
                            f"/admin/agents/{agent_id}/versions/{version_number}/archive"
                        )
                        assert archived.status_code == 200, archived.text
                        assert archived.json()["status"] == "archived"

                        deleted = await client.delete(
                            f"/admin/agents/{agent_id}/versions/{version_number}"
                        )
                        assert deleted.status_code == 204
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
