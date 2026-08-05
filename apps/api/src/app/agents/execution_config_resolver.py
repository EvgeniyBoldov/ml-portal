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
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.db import get_session_factory
from app.services.runtime_limits_service import ActorLimits, ResolvedActorLimits, RuntimeLimitsService

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
    ) -> tuple[PolicyLimits, GenerationParams, dict, ResolvedActorLimits]:
        from app.services.orchestration_service import OrchestrationSettingsProvider
        from app.services.platform_settings_service import PlatformSettingsProvider

        policy = PolicyLimits.from_policy(
            exec_request.policy_data,
            exec_request.limit_data,
        )
        gen = GenerationParams()
        self._apply_adapter_defaults(gen)

        runtime_deps = ctx.get_runtime_deps()
        session_factory = runtime_deps.session_factory or get_session_factory()
        platform_config: dict = {}
        resolved_limits = ResolvedActorLimits(
            own=ActorLimits(), effective=ActorLimits(llm_calls_max=10, tool_calls_max=50, wall_time_ms_max=300_000),
            sources={"llm_calls_max": "code", "tool_calls_max": "code", "wall_time_ms_max": "code"},
        )

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

                # Add tool_use_guard from OrchestrationSettings to platform_config
                # so prompt_assembler can use it as fallback for operations rules
                if config.get("tool_use_guard"):
                    platform_config["tool_use_guard"] = config.get("tool_use_guard")

                # Add retry_instruction from OrchestrationSettings to platform_config
                # so agent.py can use it instead of hardcoded DEFAULT_REQUIRED_OPERATION_RETRY_INSTRUCTION
                if config.get("retry_instruction"):
                    platform_config["retry_instruction"] = config.get("retry_instruction")

                # Add intent_messages from OrchestrationSettings to platform_config
                # so agent.py can use it instead of hardcoded DEFAULT_INTENT_MESSAGES
                if config.get("intent_messages"):
                    platform_config["intent_messages"] = config.get("intent_messages")

                # Add prompt_budgets from OrchestrationSettings to platform_config
                # so various modules can use it instead of hardcoded magic numbers
                if config.get("prompt_budgets"):
                    platform_config["prompt_budgets"] = config.get("prompt_budgets")

                # Add prompt_labels from OrchestrationSettings to platform_config
                # so prompt_assembler and capability_card_builder can use it instead of hardcoded labels
                if config.get("prompt_labels"):
                    platform_config["prompt_labels"] = config.get("prompt_labels")

                agent = exec_request.agent
                agent_slug = str(getattr(agent, "slug", "") or "").strip() if agent else ""
                resolved_limits = await RuntimeLimitsService(session).resolve_agent(
                    agent_slug or "default",
                    override=(sandbox_ov.get("agent_limits") if isinstance(sandbox_ov, dict) else None),
                )
                limits = resolved_limits.effective
                if limits.llm_calls_max is not None:
                    policy.max_llm_calls = int(limits.llm_calls_max)
                if limits.wall_time_ms_max is not None:
                    policy.max_wall_time_ms = int(limits.wall_time_ms_max)
                if limits.tool_calls_max is not None:
                    policy.max_tool_calls_total = int(limits.tool_calls_max)

                # temperature: Agent -> orchestration default
                agent_temperature = getattr(agent, "temperature", None) if agent else None
                if agent_temperature is not None:
                    gen.temperature = agent_temperature
                else:
                    gen.temperature = config.get("executor_temperature", gen.temperature)

                # model: runtime override -> Agent.model -> orchestration default
                resolved_model = model
                if resolved_model is None and agent:
                    resolved_model = getattr(agent, "model", None)
                if resolved_model is None:
                    resolved_model = config.get("executor_model")
                await self._apply_model_call_config(session, gen, resolved_model, policy)
                gen.model = await self._resolve_model_alias(
                    session,
                    resolved_model,
                    default_alias=base_settings.get("executor_model"),
                )
        else:
            gen.model = model

        return policy, gen, platform_config, resolved_limits

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
        self._apply_adapter_defaults(gen)

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
                await self._apply_model_call_config(session, gen, gen.model, None)
                gen.model = await self._resolve_model_alias(
                    session,
                    gen.model,
                    default_alias=base_settings.get("executor_model"),
                )

        return gen

    @staticmethod
    def _apply_adapter_defaults(gen: GenerationParams) -> None:
        """Make the SDK fallback explicit at the agent/runtime boundary.

        Scoped ``execution_limits`` remain authoritative.  When none exists,
        an agent must still pass the configured connector defaults instead of
        silently relying on the OpenAI SDK client's hidden transport values.
        """
        settings = get_settings()
        if gen.max_tokens is None:
            gen.max_tokens = max(1, int(settings.LLM_DEFAULT_MAX_TOKENS))
        if gen.timeout_s is None:
            gen.timeout_s = max(1, int(settings.LLM_TIMEOUT))

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

    @staticmethod
    async def _apply_model_call_config(
        session: AsyncSession,
        gen: GenerationParams,
        alias: Optional[str],
        policy: Optional[PolicyLimits],
    ) -> None:
        """Apply typed LLM deployment settings before the alias is resolved."""
        if not alias:
            return
        from sqlalchemy import select
        from app.models.model_registry import Model

        row = (await session.execute(
            select(Model).where((Model.alias == alias) | (Model.provider_model_name == alias), Model.deleted_at.is_(None)).limit(1)
        )).scalar_one_or_none()
        if row is None:
            return
        legacy = dict(row.extra_config or {})
        max_output = row.max_output_tokens or legacy.get("max_tokens")
        if max_output is not None:
            gen.max_tokens = int(max_output)
        if row.request_timeout_s is not None:
            gen.timeout_s = int(row.request_timeout_s)
        if policy is not None and row.max_retries is not None:
            policy.max_retries = int(row.max_retries)
