from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.execution_limit import ActorExecutionLimitScope
from app.models.system_llm_role import SystemLLMRoleType
from app.schemas.runtime_limits import OrchestratorLimitsUpdate
from app.schemas.system_llm_roles import OrchestratorRoleSettingsUpdate
from app.schemas.system_llm_roles import SystemLLMRoleUpdate
from app.services.runtime_limits_service import ActorLimits, ResolvedActorLimits
from app.services import system_llm_role_service as role_service_module
from app.services.system_llm_role_service import SystemLLMRoleService
from app.core.exceptions import ConflictError, SystemLLMRoleValidationError


@pytest.mark.asyncio
@pytest.mark.parametrize("role_type", [
    SystemLLMRoleType.PLANNER,
    SystemLLMRoleType.TURN_PREFLIGHT,
    SystemLLMRoleType.SYNTHESIZER,
    SystemLLMRoleType.FACT_EXTRACTOR,
    SystemLLMRoleType.FACT_COMPACTOR,
])
async def test_role_and_phase_limits_are_saved_together_for_each_active_orchestrator(monkeypatch, role_type):
    role = object()
    resolution = ResolvedActorLimits(
        own=ActorLimits(llm_calls_max=None, wall_time_ms_max=90_000),
        effective=ActorLimits(llm_calls_max=12, wall_time_ms_max=90_000),
        sources={"llm_calls_max": "default", "wall_time_ms_max": "entity"},
    )
    runtime_limits = AsyncMock()
    runtime_limits.resolve_orchestrator.return_value = resolution
    monkeypatch.setattr(
        role_service_module,
        "RuntimeLimitsService",
        lambda _session: runtime_limits,
    )

    service = SystemLLMRoleService(object())
    service.update_active_role = AsyncMock(return_value=role)
    payload = OrchestratorRoleSettingsUpdate(
        identity="updated identity",
        model="llm.test",
        temperature=0.25,
        execution_limits=OrchestratorLimitsUpdate(
            llm_calls_max=None,
            wall_time_ms_max=90_000,
        ),
    )

    updated_role, updated_limits = await service.update_active_orchestrator_settings(role_type, payload)

    assert updated_role is role
    assert updated_limits is resolution
    role_payload = service.update_active_role.await_args.args[1]
    assert role_payload.identity == "updated identity"
    assert role_payload.model == "llm.test"
    assert not hasattr(role_payload, "execution_limits")
    runtime_limits.update_actor.assert_awaited_once_with(
        ActorExecutionLimitScope.ORCHESTRATOR_ROLE,
        role_type.value,
        ActorLimits(llm_calls_max=None, wall_time_ms_max=90_000, tool_calls_max=None),
        {"llm_calls_max", "wall_time_ms_max"},
    )
    runtime_limits.resolve_orchestrator.assert_awaited_once_with(role_type.value)


@pytest.mark.asyncio
async def test_activating_role_deactivates_other_active_rows_of_same_type():
    role = SimpleNamespace(id=uuid4(), role_type=SystemLLMRoleType.PLANNER, is_active=False)
    other_active = SimpleNamespace(id=uuid4(), is_active=True)
    service = SystemLLMRoleService(object())
    service.repo.get_by_id = AsyncMock(return_value=role)
    service.repo.get_roles_by_type = AsyncMock(return_value=[role, other_active])
    service.repo.update = AsyncMock(return_value=role)

    await service.update_role(role.id, SystemLLMRoleUpdate(is_active=True))

    assert role.is_active is True
    assert other_active.is_active is False
    service.repo.update.assert_awaited_once_with(role)


@pytest.mark.asyncio
async def test_active_role_configuration_cannot_disable_itself():
    service = SystemLLMRoleService(object())
    service.repo.get_active_role = AsyncMock(return_value=SimpleNamespace(is_active=True))
    service.repo.update = AsyncMock()

    with pytest.raises(SystemLLMRoleValidationError):
        await service.update_active_role(
            SystemLLMRoleType.PLANNER,
            SystemLLMRoleUpdate(is_active=False),
        )

    service.repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_role_cannot_be_deleted_before_replacement_is_activated():
    role_id = uuid4()
    service = SystemLLMRoleService(object())
    service.repo.get_by_id = AsyncMock(return_value=SimpleNamespace(is_active=True))
    service.repo.delete = AsyncMock()

    with pytest.raises(ConflictError):
        await service.delete_role(role_id)

    service.repo.delete.assert_not_awaited()
