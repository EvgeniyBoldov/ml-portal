from __future__ import annotations

from types import SimpleNamespace

from app.services.sandbox_step_enrichment_service import SandboxStepEnrichmentService


def test_sanitize_step_payload_redacts_and_truncates_heavy_result():
    svc = SandboxStepEnrichmentService(SimpleNamespace())
    payload = {
        "result": {
            "credentials": {"api_key": "secret-123"},
            "blob": "x" * 5000,
        },
        "password": "super-secret",
    }

    out = svc.sanitize_step_payload(
        step_type="tool_result",
        step_data=payload,
        max_chars=200,
    )

    assert out["password"] == "***"
    assert isinstance(out["result"], dict)
    assert out["result"].get("_truncated") is True
    assert out["result"].get("total_length", 0) > 200
    assert "secret-123" not in str(out)


def test_sanitize_step_payload_truncates_llm_turn_payload():
    svc = SandboxStepEnrichmentService(SimpleNamespace())
    payload = {
        "messages": [
            {"role": "system", "content": "s" * 350},
            {"role": "user", "content": "u" * 350},
        ],
        "content": "c" * 350,
        "system_prompt": "p" * 350,
    }

    out = svc.sanitize_step_payload(
        step_type="llm_turn",
        step_data=payload,
        max_chars=200,
    )

    assert isinstance(out["messages"], dict)
    assert out["messages"].get("_truncated") is True
    assert out["messages"].get("total_length", 0) > 200
    assert isinstance(out["content"], str)
    assert out["content"].endswith("... [truncated]")
    assert isinstance(out["system_prompt"], str)
    assert out["system_prompt"].endswith("... [truncated]")
