from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.repositories.chat_context_repository import ChatContextRepository
from app.runtime.entity_ids import runtime_task_id


@pytest.mark.asyncio
async def test_glossary_provenance_scopes_tenant_entries_to_current_tenant() -> None:
    chat_id, turn_id, user_id, tenant_id, glossary_id = (uuid4() for _ in range(5))
    statements = []

    async def scalar(statement):
        statements.append(statement)
        return SimpleNamespace(user_id=user_id) if len(statements) == 1 else glossary_id

    session = SimpleNamespace(scalar=AsyncMock(side_effect=scalar))
    repository = ChatContextRepository(session)

    await repository.validate_provenance(
        chat_id=str(chat_id), chat_turn_id=str(turn_id), tenant_id=str(tenant_id),
        project_keys=["ML-Portal"],
        source_ids=[f"turn:{turn_id}", f"glossary:{glossary_id}"],
    )

    params = list(statements[1].compile().params.values())
    assert "global" in params
    assert "user" in params
    assert "tenant" in params
    assert "project" in params
    assert tenant_id in params or str(tenant_id) in {str(value) for value in params}


@pytest.mark.asyncio
async def test_task_provenance_uses_canonical_runtime_task_entity_id() -> None:
    chat_id, turn_id, run_id, plan_id = (uuid4() for _ in range(4))
    entity_id = runtime_task_id(str(plan_id), "planner-local-task")
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(user_id=uuid4(), runtime_run_id=run_id)),
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(plan_id, "planner-local-task")])),
    )
    repository = ChatContextRepository(session)

    provenance = await repository.validate_provenance(
        chat_id=str(chat_id), chat_turn_id=str(turn_id),
        source_ids=[f"turn:{turn_id}", f"run:{run_id}", f"task:{entity_id}"],
        expected_task_refs={entity_id: str(plan_id)},
    )

    assert provenance["source_run_id"] == run_id


@pytest.mark.asyncio
async def test_task_provenance_rejects_claimed_plan_mismatch() -> None:
    chat_id, turn_id, run_id, plan_id = (uuid4() for _ in range(4))
    entity_id = runtime_task_id(str(plan_id), "planner-local-task")
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(user_id=uuid4(), runtime_run_id=run_id)),
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(plan_id, "planner-local-task")])),
    )
    with pytest.raises(ValueError, match="another runtime plan"):
        await ChatContextRepository(session).validate_provenance(
            chat_id=str(chat_id), chat_turn_id=str(turn_id),
            source_ids=[f"turn:{turn_id}", f"task:{entity_id}"],
            expected_task_refs={entity_id: str(uuid4())},
        )
