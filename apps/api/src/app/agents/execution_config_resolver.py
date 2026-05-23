"""
ExecutionConfigResolver — резолв runtime-конфигурации исполнения.

Собирает параметры из:
- PolicyVersion / LimitVersion -> PolicyLimits
- AgentVersion + OrchestrationSettings + Sandbox -> GenerationParams
- PlatformSettings -> caps
- ModelRegistry -> model alias resolution
"""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from app.agents.runtime.policy import GenerationParams, PolicyLimits
from app.core.logging import get_logger
from app.core.db import get_session_factory
from app.models.execution_limit import ExecutionLimitScope
from app.services.execution_limits_service import ExecutionLimitsService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)


class ExecutionConfigResolver:
    """Resolve execution config: limits, generation params, model."""

    async def resolve(
        self,
        exec_request: ExecutionRequest,
        ctx: ToolContext,
        model: Optional[str] = None,
    ) -> tuple[PolicyLimits, GenerationParams, dict]:
        from app.services.orchestration_service import OrchestrationSettingsProvider
        from app.services.platform_settings_service import PlatformSettingsProvider

        policy = PolicyLimits.from_policy(
            exec_request.policy_data,
            exec_request.limit_data,
        )
        gen = GenerationParams()

        runtime_deps = ctx.get_runtime_deps()
        session_factory = runtime_deps.session_factory or get_session_factory()
        platform_config: dict = {}

        if session_factory:
            settings_provider = OrchestrationSettingsProvider.get_instance()
            platform_provider = PlatformSettingsProvider.get_instance()
            async with session_factory() as session:
                base_settings = await settings_provider.get_config(session)
                config = await settings_provider.get_effective_config(
                    session,
                    agent_version=exec_request.agent_version,
                )
                platform_config = await platform_provider.get_config(session)

                sandbox_ov = runtime_deps.sandbox_overrides or {}
                orch_ov = sandbox_ov.get("orchestration", {})
                platform_ov = sandbox_ov.get("platform", {})
                if orch_ov:
                    config.update(orch_ov)
                    logger.info(
                        f"[Sandbox] Applied orchestration overrides: {list(orch_ov.keys())}",
                    )
                if platform_ov:
                    platform_config.update(platform_ov)
                    logger.info(
                        f"[Sandbox] Applied platform overrides: {list(platform_ov.keys())}",
                    )

                agent = exec_request.agent
                limits_service = ExecutionLimitsService(session)
                agent_slug = str(getattr(agent, "slug", "") or "").strip() if agent else ""
                limits = await limits_service.get_effective(
                    scope_type=ExecutionLimitScope.AGENT,
                    scope_ref=agent_slug or None,
                )
                if limits.runtime_steps_max is not None:
                    policy.max_steps = int(limits.runtime_steps_max)
                if limits.runtime_wall_time_ms_max is not None:
                    policy.max_wall_time_ms = int(limits.runtime_wall_time_ms_max)
                if limits.runtime_retries_max is not None:
                    policy.max_retries = int(limits.runtime_retries_max)
                if limits.runtime_tool_calls_max is not None:
                    policy.max_tool_calls_total = int(limits.runtime_tool_calls_max)

                # temperature: Agent -> orchestration default
                agent_temperature = getattr(agent, "temperature", None) if agent else None
                if agent_temperature is not None:
                    gen.temperature = agent_temperature
                else:
                    gen.temperature = config.get("executor_temperature", gen.temperature)

                if limits.llm_output_tokens_max is not None:
                    gen.max_tokens = int(limits.llm_output_tokens_max)

                # model: runtime override -> Agent.model -> orchestration default
                resolved_model = model
                if resolved_model is None and agent:
                    resolved_model = getattr(agent, "model", None)
                if resolved_model is None:
                    resolved_model = config.get("executor_model")
                gen.model = await self._resolve_model_alias(
                    session,
                    resolved_model,
                    default_alias=base_settings.get("executor_model"),
                )
        else:
            gen.model = model

        return policy, gen, platform_config

    async def resolve_direct(
        self,
        exec_request: ExecutionRequest,
        ctx: ToolContext,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> GenerationParams:
        from app.services.orchestration_service import OrchestrationSettingsProvider

        gen = GenerationParams(
            model=model,
            temperature=temperature if temperature is not None else 0.7,
            max_tokens=max_tokens,
        )

        runtime_deps = ctx.get_runtime_deps()
        session_factory = runtime_deps.session_factory or get_session_factory()
        if session_factory:
            settings_provider = OrchestrationSettingsProvider.get_instance()
            async with session_factory() as session:
                base_settings = await settings_provider.get_config(session)
                config = await settings_provider.get_effective_config(
                    session,
                    agent_version=exec_request.agent_version,
                )

                sandbox_ov = runtime_deps.sandbox_overrides or {}
                orch_ov = sandbox_ov.get("orchestration", {})
                if orch_ov:
                    config.update(orch_ov)
                    logger.info(
                        f"[Sandbox] Applied orchestration overrides: {list(orch_ov.keys())}",
                    )

                if gen.model is None:
                    gen.model = config.get("executor_model")
                if temperature is None:
                    gen.temperature = config.get("executor_temperature", 0.7)
                if gen.max_tokens is None and exec_request.agent:
                    limits_service = ExecutionLimitsService(session)
                    limits = await limits_service.get_effective(
                        scope_type=ExecutionLimitScope.AGENT,
                        scope_ref=str(getattr(exec_request.agent, "slug", "") or "").strip() or None,
                    )
                    if limits.llm_output_tokens_max is not None:
                        gen.max_tokens = int(limits.llm_output_tokens_max)

                gen.model = await self._resolve_model_alias(
                    session,
                    gen.model,
                    default_alias=base_settings.get("executor_model"),
                )

        return gen

    @staticmethod
    async def _resolve_model_alias(
        session: AsyncSession,
        alias: Optional[str],
        default_alias: Optional[str] = None,
    ) -> Optional[str]:
        from app.services.model_resolver import ModelResolver

        resolver = ModelResolver(session)
        resolved = await resolver.resolve(alias)
        if (
            alias
            and resolved == alias
            and alias.startswith("llm.")
            and default_alias
            and default_alias != alias
        ):
            fallback = await resolver.resolve(default_alias)
            if fallback:
                logger.warning(
                    "Execution model alias '%s' unresolved; fallback to executor_model '%s'",
                    alias,
                    default_alias,
                )
                return fallback
        return resolved
