from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService


def test_build_paused_from_stop_waiting_confirmation_contains_canonical_fields():
    payload = RuntimeHitlProtocolService.build_paused_from_stop(
        {
            "reason": "waiting_confirmation",
            "run_id": "r-1",
            "question": "Apply changes?",
            "operation_fingerprint": "fp-1",
        }
    )

    assert payload["contract_version"] == 1
    assert payload["reason"] == "waiting_confirmation"
    assert payload["run_id"] == "r-1"
    assert payload["action"]["kind"] == "confirm"
    assert payload["action"]["type"] == "resume"
    assert payload["action"]["operation_fingerprint"] == "fp-1"
    assert payload["context"]["contract_version"] == 1


def test_extract_operation_fingerprint_falls_back_to_paused_context():
    fingerprint = RuntimeHitlProtocolService.extract_operation_fingerprint(
        paused_action={"kind": "confirm"},
        paused_context={"operation_fingerprint": "fp-ctx"},
    )
    assert fingerprint == "fp-ctx"


def test_build_paused_from_stop_waiting_input_sets_input_kind():
    payload = RuntimeHitlProtocolService.build_paused_from_stop(
        {"reason": "waiting_input", "question": "Need VLAN id"}
    )
    assert payload["action"]["kind"] == "input"
