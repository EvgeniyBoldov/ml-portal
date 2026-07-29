from app.runtime.llm.limits import resolve_llm_timeout_s
from app.services.execution_limits_service import ExecutionLimitsPayload


def test_llm_timeout_limit_overrides_role_timeout() -> None:
    assert resolve_llm_timeout_s(
        configured_timeout_s=40,
        limits=ExecutionLimitsPayload(llm_timeout_s=60),
    ) == 60


def test_llm_timeout_uses_role_timeout_when_limit_is_unset() -> None:
    assert resolve_llm_timeout_s(
        configured_timeout_s=40,
        limits=ExecutionLimitsPayload(),
    ) == 40
