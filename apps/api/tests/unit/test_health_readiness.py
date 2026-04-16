from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from types import ModuleType
import sys

import pytest

from app.api.v1.routers import health as health_module
from app.api.v1.routers.health import readiness_check_endpoint

class TestHealthReadiness:
    @pytest.mark.asyncio
    async def test_readyz_returns_degraded_when_infra_ready_but_app_service_not_ready(self, mock_session):
        registry_module = ModuleType("app.agents.registry")
        registry_module.ToolRegistry = type("ToolRegistry", (), {"list_slugs": staticmethod(lambda: ["rag.search"])})

        agent_service_module = ModuleType("app.services.agent_service")
        agent_service_module.AgentService = type(
            "AgentService",
            (),
            {
                "__init__": lambda self, session: None,
                "get_default_agent_slug": AsyncMock(return_value="rag-search"),
            },
        )

        with patch.object(health_module, "db_health_check", AsyncMock(return_value=True)), \
             patch.object(health_module, "get_cache", AsyncMock(return_value=object())), \
             patch.object(health_module, "get_s3_client") as get_s3_client, \
             patch.object(health_module, "get_qdrant_adapter", AsyncMock()) as get_qdrant_adapter, \
             patch("app.celery_app.app") as celery_app, \
             patch("app.core.di.get_llm_client") as get_llm_client, \
             patch("app.core.di.get_emb_client") as get_emb_client, \
             patch("app.services.run_store.RunStore"), \
             patch.dict(sys.modules, {
                 "app.agents.registry": registry_module,
                 "app.services.agent_service": agent_service_module,
             }):
            s3_client = MagicMock()
            s3_client.health_check = AsyncMock(return_value=True)
            get_s3_client.return_value = s3_client

            qdrant = MagicMock()
            qdrant.health_check = AsyncMock(return_value=True)
            get_qdrant_adapter.return_value = qdrant

            llm = MagicMock()
            llm.chat = AsyncMock(side_effect=RuntimeError("llm down"))
            get_llm_client.return_value = llm

            emb = MagicMock()
            emb.embed = AsyncMock(return_value=[[0.1, 0.2]])
            get_emb_client.return_value = emb

            celery_app.control.ping.return_value = [{"worker@api": {"ok": "pong"}}]

            response = await readiness_check_endpoint(mock_session)
            assert response.status_code == 200
            body = json.loads(response.body.decode())
            assert body["status"] == "degraded"
            assert body["infra"]["database"] == "ready"
            assert body["app_services"]["llm"] == "not_ready"
            assert body["app_services"]["tool_registry"] == "ready"

    @pytest.mark.asyncio
    async def test_readyz_returns_503_when_infra_not_ready(self, mock_session):
        registry_module = ModuleType("app.agents.registry")
        registry_module.ToolRegistry = type("ToolRegistry", (), {"list_slugs": staticmethod(lambda: [])})

        agent_service_module = ModuleType("app.services.agent_service")
        agent_service_module.AgentService = type(
            "AgentService",
            (),
            {
                "__init__": lambda self, session: None,
                "get_default_agent_slug": AsyncMock(return_value=None),
            },
        )

        with patch.object(health_module, "db_health_check", AsyncMock(return_value=False)), \
             patch.object(health_module, "get_cache", AsyncMock(side_effect=RuntimeError("redis down"))), \
             patch.object(health_module, "get_s3_client") as get_s3_client, \
             patch.object(health_module, "get_qdrant_adapter", AsyncMock(side_effect=RuntimeError("qdrant down"))), \
             patch("app.core.di.get_llm_client") as get_llm_client, \
             patch("app.core.di.get_emb_client") as get_emb_client, \
             patch("app.services.run_store.RunStore"), \
             patch("app.celery_app.app") as celery_app, \
             patch.dict(sys.modules, {
                 "app.agents.registry": registry_module,
                 "app.services.agent_service": agent_service_module,
             }):
            s3_client = MagicMock()
            s3_client.health_check = AsyncMock(return_value=False)
            get_s3_client.return_value = s3_client

            llm = MagicMock()
            llm.chat = AsyncMock(return_value={"content": "pong"})
            get_llm_client.return_value = llm

            emb = MagicMock()
            emb.embed = AsyncMock(return_value=[[0.1]])
            get_emb_client.return_value = emb

            celery_app.control.ping.return_value = []

            response = await readiness_check_endpoint(mock_session)
            assert response.status_code == 503
            body = json.loads(response.body.decode())
            assert body["status"] == "not_ready"
            assert body["infra"]["database"] == "not_ready"
            assert body["infra"]["redis"] == "not_ready"
