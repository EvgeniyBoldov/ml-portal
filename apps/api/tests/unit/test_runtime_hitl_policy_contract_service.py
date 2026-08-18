from uuid import uuid4
from typing import Literal

from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.services.runtime_hitl_policy_contract_service import RuntimeHitlPolicyContractService


def _op(
    slug: str,
    *,
    side_effects: bool,
    risk_level: Literal["safe", "write", "destructive"] = "safe",
    requires_confirmation: bool = False,
) -> ResolvedOperation:
    target = ProviderExecutionTarget(
        operation_slug=slug,
        provider_type="local",
        data_instance_id=str(uuid4()),
        data_instance_slug="instance-a",
    )
    return ResolvedOperation(
        operation_slug=slug,
        operation="collection.table.mutate",
        name=slug,
        input_schema={},
        data_instance_id=target.data_instance_id,
        data_instance_slug=target.data_instance_slug,
        source="local",
        risk_level=risk_level,
        side_effects=side_effects,
        requires_confirmation=requires_confirmation,
        target=target,
    )


def test_hitl_contract_blocks_destructive_when_forbidden():
    payload = RuntimeHitlPolicyContractService().build(
        platform_config={"forbid_destructive": True},
        operations=[_op("tool.destructive", side_effects=True, risk_level="destructive")],
    )

    assert payload["operation_policies"][0]["effective_decision"] == "block"


def test_hitl_contract_requires_confirmation_from_semantics_and_platform():
    payload = RuntimeHitlPolicyContractService().build(
        platform_config={"require_confirmation_for_write": True},
        operations=[
            _op("tool.write", side_effects=True, risk_level="write"),
            _op("tool.semantic", side_effects=False, requires_confirmation=True),
        ],
    )

    decisions = {item["operation_slug"]: item["effective_decision"] for item in payload["operation_policies"]}
    assert decisions["tool.write"] == "require_confirmation"
    assert decisions["tool.semantic"] == "require_confirmation"


def test_hitl_contract_exposes_one_resume_payload_for_chat_and_sandbox():
    payload = RuntimeHitlPolicyContractService().build(platform_config={}, operations=[])

    contract = payload["resume_contract"]
    assert contract["resume_payload"]["action"] == "input | confirm | cancel"
    assert set(contract["resume_endpoints"]) == {"chat", "sandbox"}
