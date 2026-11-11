from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import json
from types import SimpleNamespace

import httpx

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

    async def fake_access(_arguments, **_kwargs):
        return "http://inference", {}, SimpleNamespace(credential_id="test", auth_type="token")

    async def fake_request(**kwargs):
        if kwargs["method"] == "GET":
            return _model_card({"type": "object"})
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

    async def fake_access(_arguments, **_kwargs):
        return "http://inference", {}, SimpleNamespace(credential_id="test", auth_type="token")

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


def _model_card(schema):
    return {
        "id": "NIMS", "object": "model", "input_schema": schema,
        "output_schema": {}, "deployment": {"version": "1", "status": "active"},
    }


@pytest.fixture
def prediction_call(monkeypatch):
    def call(inputs, schema, *, status=200, error=None):
        requests = []

        async def access(_arguments, **_kwargs):
            return "http://inference", {"Authorization": "Bearer secret-value"}, SimpleNamespace(
                credential_id="test", auth_type="token",
            )

        def handle(request):
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(200, json=_model_card(schema))
            if status >= 400:
                return httpx.Response(status, json=error)
            return httpx.Response(200, json={
                "id": "resp_test", "object": "response", "status": "completed", "output": [],
            })

        original_client = httpx.AsyncClient
        monkeypatch.setattr(ml_server, "_resolve_runtime_access", access)
        monkeypatch.setattr(ml_server.httpx, "AsyncClient", lambda **kwargs: original_client(
            **kwargs, transport=httpx.MockTransport(handle),
        ))
        with TestClient(ml_server.app) as client:
            initialized = client.post("/", json={"id": 1, "method": "initialize"})
            response = client.post("/", headers={
                "mcp-session-id": initialized.headers["mcp-session-id"],
                "x-portal-request-id": "regression-nims",
            }, json={"id": 2, "method": "tools/call", "params": {
                "name": "model.predict", "arguments": {"model_id": "NIMS", "inputs": inputs},
            }})
        return response.json(), requests
    return call


NIMS_SCHEMA = {
    "type": "object", "properties": {"header": {"type": "string"}, "description": {"type": "string"}},
    "required": ["header", "description"],
}


def test_nims_json_string_is_decoded_and_validated_before_predict(prediction_call):
    inputs = {"header": "МИРК", "description": "Отчеты"}
    result, requests = prediction_call(json.dumps(inputs), NIMS_SCHEMA)
    assert "result" in result
    assert [request.method for request in requests] == ["GET", "POST"]
    assert json.loads(requests[-1].content) == {"model": "NIMS", "input": inputs}


@pytest.mark.parametrize("inputs,schema", [
    ('{"header":"literal string"}', {"type": "string"}),
    ("123", {"type": ["string", "number"]}),
    ([1, 2], {"type": "array", "items": {"type": "integer"}}),
    (False, {"type": "boolean"}),
    (None, {"type": "null"}),
])
def test_valid_json_values_keep_their_type(prediction_call, inputs, schema):
    result, requests = prediction_call(inputs, schema)
    assert "result" in result
    assert json.loads(requests[-1].content)["input"] == inputs


@pytest.mark.parametrize("inputs", [
    '{"header":', {"header": "МИРК"}, {"header": 5, "description": "Отчеты"},
    '{"header":5,"description":"Отчеты"}', float("inf"),
])
def test_invalid_inputs_are_actionable_and_never_sent_to_prediction(prediction_call, inputs):
    # HTTP JSON cannot carry infinity; test finite-value validation separately below.
    if isinstance(inputs, float):
        with pytest.raises(ValueError):
            ml_server._normalize_prediction_inputs(inputs, NIMS_SCHEMA)
        return
    result, requests = prediction_call(inputs, NIMS_SCHEMA)
    failure = result["error"]["data"]
    assert failure["category"] == "input"
    assert failure["code"] == "SCHEMA_VALIDATION_ERROR"
    assert failure["request_id"] == "regression-nims"
    assert failure["stage"] == "input_validation"
    assert "inputs" in failure["message"]
    assert [request.method for request in requests] == ["GET"]


@pytest.mark.parametrize("status,category,code", [
    (400, "input", "SCHEMA_VALIDATION_ERROR"), (401, "auth", "INVALID_API_KEY"),
    (403, "access", "INSUFFICIENT_PERMISSIONS"), (429, "rate_limit", "http_429"),
    (503, "availability", "SERVICE_OVERLOADED"), (504, "availability", "MODEL_PREDICTION_TIMEOUT"),
])
def test_upstream_errors_reach_agent_with_safe_diagnostics(prediction_call, status, category, code):
    result, _ = prediction_call({"header": "МИРК", "description": "Отчеты"}, NIMS_SCHEMA,
        status=status, error={"error": {
            "code": code, "type": "invalid_request_error", "param": "input.header",
            "message": "secret-value http://private/internal traceback raw payload",
        }})
    failure = result["error"]["data"]
    assert failure["category"] == category
    assert failure["code"] == code
    assert failure["http_status"] == status
    assert failure["request_id"] == "regression-nims"
    assert "secret-value" not in json.dumps(result)
    assert "private/internal" not in json.dumps(result)


def test_failure_envelope_is_consumable_by_runtime(prediction_call):
    from app.agents.operation_executor import DirectOperationExecutor
    from app.agents.runtime.tools import OperationExecutionFacade

    response, _ = prediction_call({"header": 7, "description": "text"}, NIMS_SCHEMA)
    payload = DirectOperationExecutor._mcp_tool_result_or_raise(response)
    result = DirectOperationExecutor._tool_result_from_payload(payload)
    assert result.success is False

    observation = json.loads(OperationExecutionFacade.format_result_for_context(result))
    assert observation["failure"]["category"] == "input"
    assert observation["failure"]["details"]["param"] == "inputs.header"
    assert "Expected type: string" in observation["failure"]["message"]


@pytest.mark.parametrize("schema", [
    {"type": "invalid-schema-type"}, {"$ref": "http://private.example/schema"},
])
def test_broken_model_schema_returns_structured_failure_without_predict(prediction_call, schema):
    result, requests = prediction_call({"header": "text"}, schema)
    failure = result["error"]["data"]
    assert failure["category"] == "unknown"
    assert failure["kind"] == "protocol"
    assert failure["request_id"] == "regression-nims"
    assert [request.method for request in requests] == ["GET"]
    assert "private.example" not in json.dumps(result)


@pytest.mark.parametrize("inputs,schema,expected", [
    ("[1,2]", {"type": "array"}, [1, 2]),
    ("null", {"type": "null"}, None),
    ("42", {"type": "integer"}, 42),
    ('{"v":1}', {"$defs": {"payload": {"type": "object"}}, "$ref": "#/$defs/payload"}, {"v": 1}),
])
def test_encoded_json_values_are_validated_after_decoding(prediction_call, inputs, schema, expected):
    result, requests = prediction_call(inputs, schema)
    assert "result" in result
    assert json.loads(requests[-1].content)["input"] == expected


def test_inference_timeout_has_actionable_failure():
    result = ml_server._failure_response(1, httpx.ReadTimeout("secret upstream details"),
        request_id="timeout-test", stage="facade_request")
    failure = result["error"]["data"]
    assert failure["category"] == "availability"
    assert failure["kind"] == "transport"
    assert "timed out" in failure["message"]
    assert "secret upstream" not in json.dumps(result)
