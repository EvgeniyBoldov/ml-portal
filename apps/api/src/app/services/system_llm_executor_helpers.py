"""
Pure helper functions for SystemLLMExecutor.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict

from app.core.exceptions import SystemLLMExecutorError


def normalize_planner_response(response: dict) -> dict:
    if not isinstance(response, dict):
        return response
    steps = response.get("steps", [])
    normalized_steps = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        ns = dict(step)
        ref_source = None
        for alt_ref in ("operation", "operation_slug", "agent", "agent_slug"):
            if "ref" not in ns and alt_ref in ns:
                ns["ref"] = ns.pop(alt_ref)
                ref_source = alt_ref
                break
        for alt_op in ("operation", "action", "method"):
            if "op" not in ns and alt_op in ns:
                ns["op"] = ns.pop(alt_op)
                break
        for alt_input in ("args", "arguments", "params", "parameters"):
            if "input" not in ns and alt_input in ns:
                ns["input"] = ns.pop(alt_input)
                break
        if "input" not in ns:
            known_keys = {"kind", "ref", "op", "title", "step_id", "requires_confirmation", "risk_level", "on_fail", "text"}
            extra = {k: v for k, v in ns.items() if k not in known_keys}
            if extra:
                ns["input"] = extra
                for k in extra:
                    del ns[k]
        if "kind" not in ns:
            if ref_source in ("agent", "agent_slug"):
                ns["kind"] = "agent"
            elif ns.get("ref"):
                ns["kind"] = "operation"
            elif "text" in ns or "description" in ns:
                ns["kind"] = "llm"
            else:
                ns["kind"] = "llm"
        if "title" not in ns:
            ns["title"] = ns.get("ref", ns.get("kind", f"step_{i+1}"))
        if "step_id" not in ns:
            ns["step_id"] = f"s{i+1}"
        normalized_steps.append(ns)
    response["steps"] = normalized_steps
    return response


def planner_plan_to_next_action(plan) -> Any:
    from app.agents.contracts import (
        ActionType,
        NextAction,
        ActionIntent,
        OperationActionPayload,
        AgentActionPayload,
        AskUserPayload,
        FinalPayload,
        ActionMeta,
    )

    if not plan.steps:
        return NextAction(
            type=ActionType.ASK_USER,
            ask_user=AskUserPayload(question="No steps available in plan. What would you like me to do?"),
            meta=ActionMeta(why="Empty plan received"),
        )

    step = plan.steps[0]
    step_meta = ActionMeta(
        why=step.title,
        phase_id=(step.input or {}).get("phase_id"),
        phase_title=(step.input or {}).get("phase_title"),
    )

    if step.kind == "agent":
        agent_slug = step.ref or "unknown"
        return NextAction(
            type=ActionType.AGENT_CALL,
            agent=AgentActionPayload(agent_slug=agent_slug, input=step.input or {}),
            meta=ActionMeta(
                why=f"Delegate to agent {agent_slug}: {step.title}",
                phase_id=step_meta.phase_id,
                phase_title=step_meta.phase_title,
            ),
        )

    if step.kind == "operation" and step.ref and step.op:
        return NextAction(
            type=ActionType.OPERATION_CALL,
            operation=OperationActionPayload(
                intent=ActionIntent(operation_slug=step.ref, op=step.op),
                input=step.input or {},
            ),
            meta=ActionMeta(
                why=f"Execute {step.ref}.{step.op}: {step.title}",
                phase_id=step_meta.phase_id,
                phase_title=step_meta.phase_title,
            ),
        )

    if step.kind == "ask_user":
        return NextAction(type=ActionType.ASK_USER, ask_user=AskUserPayload(question=step.title), meta=step_meta)

    if step.kind == "llm":
        return NextAction(type=ActionType.FINAL, final=FinalPayload(answer=step.title), meta=step_meta)

    return NextAction(
        type=ActionType.ASK_USER,
        ask_user=AskUserPayload(
            question=f"Unsupported step type: {step.kind}. Please clarify what you want me to do."
        ),
        meta=ActionMeta(
            why=f"Unsupported step type: {step.kind}",
            phase_id=step_meta.phase_id,
            phase_title=step_meta.phase_title,
        ),
    )


def extract_result_summary(response: Dict[str, Any]) -> str:
    resp_type = response.get("type", "unknown")
    if resp_type == "final" and response.get("answer"):
        return response["answer"][:100] + ("..." if len(response["answer"]) > 100 else "")
    if resp_type == "clarify" and response.get("clarify_prompt"):
        return f"Clarify: {response['clarify_prompt'][:100]}"
    if resp_type == "orchestrate" and response.get("goal"):
        return f"Orchestrate: {response['goal'][:100]}"
    if response.get("steps"):
        return f"Plan with {len(response['steps'])} steps"
    if response.get("question"):
        return response["question"][:100] + ("..." if len(response["question"]) > 100 else "")
    return f"Response type: {resp_type}"


def extract_json(content: str) -> Dict[str, Any]:
    content = content.strip()
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        pass

    if "```" in content:
        json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass

    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(content[first_brace:last_brace + 1])
        except (json.JSONDecodeError, ValueError):
            pass

    raise json.JSONDecodeError(
        f"No valid JSON found in response ({len(content)} chars): {content[:200]}",
        content,
        0,
    )


def validate_contract(response: Dict[str, Any], schema: Dict[str, Any]) -> None:
    required_fields = schema.get("required", [])
    for field in required_fields:
        if field not in response:
            raise SystemLLMExecutorError(f"Missing required field: {field}")

    properties = schema.get("properties", {})
    for field, value in response.items():
        if field in properties:
            validate_field(field, value, properties[field])


def validate_field(field: str, value: Any, schema: Dict[str, Any]) -> None:
    field_type = schema.get("type")
    if field_type == "string":
        if not isinstance(value, str):
            raise SystemLLMExecutorError(f"Field {field} must be string")
    elif field_type == "number":
        if not isinstance(value, (int, float)):
            raise SystemLLMExecutorError(f"Field {field} must be number")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            raise SystemLLMExecutorError(f"Field {field} must be >= {minimum}")
        if maximum is not None and value > maximum:
            raise SystemLLMExecutorError(f"Field {field} must be <= {maximum}")
    elif field_type == "array":
        if not isinstance(value, list):
            raise SystemLLMExecutorError(f"Field {field} must be array")
    elif field_type == "object":
        if not isinstance(value, dict):
            raise SystemLLMExecutorError(f"Field {field} must be object")

    enum_values = schema.get("enum")
    if enum_values and value not in enum_values:
        raise SystemLLMExecutorError(f"Field {field} must be one of {enum_values}")


def smart_triage_mapping(response: Dict[str, Any]) -> Dict[str, Any]:
    mapped: Dict[str, Any] = {
        "type": "final",
        "confidence": 0.7,
        "reason": "Mapped from non-standard response",
        "answer": "",
    }

    if not isinstance(response, dict):
        mapped["answer"] = str(response)
        return mapped

    message_content = response.get("message") or response.get("content") or response.get("text")
    action = (response.get("action") or response.get("type") or response.get("next_step") or "").lower()

    if action in {"final", "answer", "respond"}:
        mapped.update({"type": "final", "answer": response.get("answer") or message_content or ""})
    elif action in {"clarify", "ask_user", "question"}:
        mapped.update({
            "type": "clarify",
            "clarify_prompt": response.get("clarify_prompt") or response.get("question") or message_content or "Could you clarify?",
        })
    elif action in {"orchestrate", "plan", "planner", "multi_step", "agent", "delegate", "route"}:
        mapped.update({
            "type": "orchestrate",
            "goal": response.get("goal") or response.get("task") or message_content or "General assistance",
            "inputs": response.get("inputs") or response.get("context") or {},
        })
    elif message_content:
        mapped.update({
            "type": "final",
            "answer": str(message_content),
            "confidence": 0.9,
            "reason": "Direct response from LLM",
        })

    if "confidence" in response:
        try:
            mapped["confidence"] = float(response["confidence"])
        except (TypeError, ValueError):
            pass

    if response.get("reason"):
        mapped["reason"] = str(response["reason"])

    return mapped
