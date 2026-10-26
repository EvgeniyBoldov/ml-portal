from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


_HERE = Path(__file__).resolve()
_SERVER_PATH = next(
    (parent / "mcp" / "ml_inference" / "server.py" for parent in _HERE.parents if (parent / "mcp" / "ml_inference" / "server.py").exists()),
    None,
)
if _SERVER_PATH is None:
    pytest.skip("ML inference MCP shim is unavailable", allow_module_level=True)
_MCP_ROOT = _SERVER_PATH.parents[1]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
_SPEC = spec_from_file_location("ml_inference_mcp_server_module", _SERVER_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Cannot load ML inference MCP shim from {_SERVER_PATH}")
ml_server = module_from_spec(_SPEC)
_SPEC.loader.exec_module(ml_server)


def test_ml_inference_tools_expose_catalog_and_prediction_contracts():
    tools = {tool["name"]: tool for tool in ml_server.TOOLS}

    assert set(tools) == {"model.info", "model.predict"}
    assert tools["model.info"]["annotations"]["readOnlyHint"] is True
    assert tools["model.predict"]["annotations"]["readOnlyHint"] is True
    assert tools["model.predict"]["inputSchema"]["required"] == ["model_id", "inputs"]
    assert "limit" not in tools["model.info"]["inputSchema"]["properties"]
    assert "cursor" not in tools["model.info"]["inputSchema"]["properties"]
    assert "type" not in tools["model.predict"]["inputSchema"]["properties"]["inputs"]


def test_model_id_is_encoded_before_it_becomes_a_facade_path_segment():
    assert ml_server._path_for_model("risk.model_1") == "/v1/models/risk.model_1"


def test_model_id_validation_matches_inference_service_identifier_contract():
    with pytest.raises(ValueError, match="valid deployed model identifier"):
        ml_server._path_for_model("risk/model")


def test_instance_context_is_the_default_facade_url_source():
    url = ml_server._extract_base_url({}, {"instance_context": {"data_instance_url": "https://inference.example/"}})

    assert url == "https://inference.example"


def test_linked_data_connector_url_wins_over_mcp_provider_url():
    url = ml_server._extract_base_url(
        {},
        {
            "instance_context": {
                "data_instance_url": "http://host.docker.internal:18000",
                "provider_url": "http://ml-inference-mcp:8080/",
            }
        },
    )

    assert url == "http://host.docker.internal:18000"


def test_mcp_rejects_oversized_facade_results():
    original = ml_server.MAX_RESPONSE_BYTES
    ml_server.MAX_RESPONSE_BYTES = 8
    try:
        with pytest.raises(ValueError, match="result limit"):
            ml_server._assert_bounded({"prediction": "too large"})
    finally:
        ml_server.MAX_RESPONSE_BYTES = original


def test_facade_contract_uses_openai_style_model_and_response_shapes():
    catalog = {
        "object": "list",
        "data": [
            {
                "id": "credit-scoring",
                "object": "model",
                "version": "18",
                "input_schema": {"type": "object", "required": ["income"]},
                "output_schema": {"type": "object", "properties": {"risk": {"type": "number"}}},
            }
        ],
    }
    card = {
        "id": "credit-scoring",
        "object": "model",
        "input_schema": {},
        "output_schema": {},
        "deployment": {"version": "18", "status": "active"},
    }
    response = {
        "id": "resp_abc123",
        "object": "response",
        "created_at": 1787750100,
        "status": "completed",
        "model": "credit-scoring",
        "model_version": "18",
        "output": [{"type": "prediction", "content": {"prediction": 1}}],
    }

    assert ml_server._validate_info_response(catalog, model_id=None) == catalog
    assert ml_server._validate_info_response(card, model_id="credit-scoring") == card
    assert ml_server._validate_predict_response(response) == response


def test_facade_contract_rejects_legacy_prediction_shape():
    with pytest.raises(ValueError, match="invalid prediction response"):
        ml_server._validate_predict_response(
            {"prediction": 1, "model": {"model_id": "credit-scoring", "version": "18"}}
        )


def test_prediction_forwards_json_input_without_changing_its_shape(monkeypatch):
    captured = {}

    async def fake_access(_arguments):
        return "http://inference", {}

    async def fake_request(**kwargs):
        captured.update(kwargs)
        return {
            "id": "resp_abc123",
            "object": "response",
            "created_at": 1787750100,
            "status": "completed",
            "model": "credit-scoring",
            "model_version": "18",
            "output": [{"type": "prediction", "content": {"prediction": 1}}],
        }

    monkeypatch.setattr(ml_server, "_resolve_runtime_access", fake_access)
    monkeypatch.setattr(ml_server, "_facade_request", fake_request)
    client = TestClient(ml_server.app)
    initialized = client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    session_id = initialized.headers["mcp-session-id"]

    response = client.post(
        "/",
        headers={"mcp-session-id": session_id},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "model.predict",
                "arguments": {"model_id": "credit-scoring", "inputs": {"income": 125000, "region": "north"}},
            },
        },
    )

    assert response.status_code == 200
    assert captured["body"] == {
        "model": "credit-scoring",
        "input": {"income": 125000, "region": "north"},
    }


def test_model_catalog_request_does_not_send_unsupported_pagination(monkeypatch):
    captured = {}

    async def fake_access(_arguments):
        return "http://inference", {}

    async def fake_request(**kwargs):
        captured.update(kwargs)
        return {
            "object": "list",
            "data": [
                {
                    "id": "credit-scoring",
                    "object": "model",
                    "version": "18",
                    "input_schema": {"type": "object", "required": ["income"]},
                    "output_schema": {"type": "object", "properties": {"risk": {"type": "number"}}},
                }
            ],
        }

    monkeypatch.setattr(ml_server, "_resolve_runtime_access", fake_access)
    monkeypatch.setattr(ml_server, "_facade_request", fake_request)
    client = TestClient(ml_server.app)
    initialized = client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    session_id = initialized.headers["mcp-session-id"]

    response = client.post(
        "/",
        headers={"mcp-session-id": session_id},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "model.info", "arguments": {}}},
    )

    assert response.status_code == 200
    assert captured["path"] == "/v1/models"
    assert captured.get("params") is None
    result = response.json()["result"]["structuredContent"]
    model = result["data"][0]
    assert model["input_schema"]["required"] == ["income"]
    assert model["output_schema"]["properties"]["risk"]["type"] == "number"
