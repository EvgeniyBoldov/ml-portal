from __future__ import annotations

import json
import os
import uuid
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response

from helpers.secret_broker import SecretBrokerClient, extract_credential_access


app = FastAPI(title="ML Inference MCP Shim", version="1.0.0")

VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").lower() == "true"
ML_INFERENCE_CA_BUNDLE = (os.environ.get("ML_INFERENCE_CA_BUNDLE") or "").strip()
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("ML_INFERENCE_TIMEOUT_SECONDS", "30"))
BROKER_TIMEOUT_SECONDS = int(os.environ.get("MCP_SECRET_BROKER_TIMEOUT_SECONDS", "10"))
MAX_MODELS_PER_PAGE = int(os.environ.get("ML_INFERENCE_MAX_MODELS_PER_PAGE", "100"))
MAX_RESPONSE_BYTES = int(os.environ.get("ML_INFERENCE_MAX_RESPONSE_BYTES", "262144"))
MODELS_PATH = os.environ.get("ML_INFERENCE_MODELS_PATH", "/v1/models")
PREDICT_PATH = os.environ.get("ML_INFERENCE_PREDICT_PATH", "/v1/predict")
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "ml-inference-mcp-shim", "version": "1.0.0"}
SESSIONS: set[str] = set()


def _jsonrpc_ok(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _jsonrpc_err(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _normalize_base_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", "")).rstrip("/")


def _extract_base_url(payload: dict[str, Any], arguments: dict[str, Any]) -> str:
    for source in (payload, arguments):
        for key in ("ml_inference_url", "inference_url", "base_url", "url"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return _normalize_base_url(value)

    instance_context = arguments.get("instance_context")
    if isinstance(instance_context, dict):
        for key in ("data_instance_url", "provider_url", "base_url"):
            value = instance_context.get(key)
            if isinstance(value, str) and value.strip():
                return _normalize_base_url(value)
        config = instance_context.get("config")
        if isinstance(config, dict):
            for key in ("ml_inference_url", "inference_url", "base_url", "url"):
                value = config.get(key)
                if isinstance(value, str) and value.strip():
                    return _normalize_base_url(value)
    raise ValueError("No ML inference facade URL configured")


def _extract_auth(payload: dict[str, Any]) -> dict[str, str]:
    for key in ("token", "api_token", "access_token", "api_key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return {"Authorization": f"Bearer {value.strip()}"}
    return {}


async def _resolve_runtime_access(arguments: dict[str, Any]) -> tuple[str, dict[str, str]]:
    access = extract_credential_access(arguments)
    if access:
        resolved = await SecretBrokerClient(timeout_s=BROKER_TIMEOUT_SECONDS).resolve(access)
        return _extract_base_url(resolved.payload, arguments), _extract_auth(resolved.payload)

    instance_context = arguments.get("instance_context")
    if isinstance(instance_context, dict):
        credentials = instance_context.get("credentials")
        if isinstance(credentials, dict):
            return _extract_base_url(credentials, arguments), _extract_auth(credentials)
    # A facade protected by network policy/mTLS can intentionally have no token.
    return _extract_base_url({}, arguments), {}


def _limit(value: Any) -> int:
    try:
        requested = int(value or 20)
    except (TypeError, ValueError):
        requested = 20
    return max(1, min(requested, MAX_MODELS_PER_PAGE))


def _path_for_model(model_id: str) -> str:
    normalized = str(model_id or "").strip()
    if not normalized:
        raise ValueError("model_id is required")
    return f"{MODELS_PATH.rstrip('/')}/{quote(normalized, safe='')}"


def _assert_bounded(data: Any) -> Any:
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise ValueError("ML inference response exceeds the configured MCP result limit")
    return data


def _validate_info_response(data: Any, *, model_id: str | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("ML inference facade returned an invalid model info response")
    if model_id:
        if not isinstance(data.get("model_id"), str) or not isinstance(data.get("input_schema"), dict):
            raise ValueError("ML inference facade returned an invalid detailed model card")
    elif not isinstance(data.get("models"), list):
        raise ValueError("ML inference facade returned an invalid model catalog")
    return data


def _validate_predict_response(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or "prediction" not in data or not isinstance(data.get("model"), dict):
        raise ValueError("ML inference facade returned an invalid prediction response")
    return data


async def _facade_request(
    *,
    base_url: str,
    auth_headers: dict[str, str],
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    verify: bool | str = ML_INFERENCE_CA_BUNDLE if ML_INFERENCE_CA_BUNDLE else VERIFY_SSL
    headers = {"Accept": "application/json", **auth_headers}
    if body is not None:
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, verify=verify) as client:
        response = await client.request(method, f"{base_url}{path}", headers=headers, params=params, json=body)
    if response.status_code >= 400:
        raise ValueError(f"ML inference facade returned HTTP {response.status_code}")
    try:
        return _assert_bounded(response.json())
    except json.JSONDecodeError as exc:
        raise ValueError("ML inference facade returned a non-JSON response") from exc


def _tool_result(data: Any) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, separators=(",", ":"))}],
        "structuredContent": data,
        "isError": False,
    }


TOOLS = [
    {
        "name": "model.info",
        "description": (
            "List ML prediction capabilities, or inspect one by model_id. Use before prediction to learn "
            "the model's purpose, applicability, required input schema, output semantics, version and quality metadata."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Optional stable model identifier. Omit to list available models."},
                "limit": {"type": "integer", "default": 20, "description": "Maximum models for a catalog page."},
                "cursor": {"type": "string", "description": "Opaque cursor from a previous catalog response."},
            },
        },
        "outputSchema": {
            "type": "object",
            "oneOf": [
                {"required": ["models"]},
                {"required": ["model_id", "input_schema", "output_schema", "deployment", "quality"]},
            ],
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "model.predict",
        "description": (
            "Run one registered ML model on validated input data. Use model.info first. "
            "A model prediction is a bounded statistical signal and must be interpreted with returned warnings and applicability metadata."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Stable identifier returned by model.info."},
                "version": {"type": "string", "description": "Optional deployed version or alias such as production."},
                "inputs": {"type": "object", "description": "Model input that conforms to the input_schema returned by model.info."},
                "request_id": {"type": "string", "description": "Optional caller-provided idempotency and trace identifier."},
            },
            "required": ["model_id", "inputs"],
        },
        "outputSchema": {
            "type": "object",
            "required": ["prediction", "model", "request_id", "warnings"],
            "properties": {
                "prediction": {},
                "model": {
                    "type": "object",
                    "required": ["model_id", "version"],
                    "properties": {"model_id": {"type": "string"}, "version": {"type": "string"}},
                },
                "request_id": {"type": "string"},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": False},
    },
]


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/")
async def mcp_root(
    request: Request,
    response: Response,
    mcp_session_id: str | None = Header(default=None),
) -> dict[str, Any]:
    payload = await request.json()
    rpc_id, method, params = payload.get("id"), payload.get("method"), payload.get("params") or {}
    try:
        if method == "initialize":
            session_id = str(uuid.uuid4())
            SESSIONS.add(session_id)
            response.headers["mcp-session-id"] = session_id
            return _jsonrpc_ok(
                rpc_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                    "instructions": "ML inference MCP adapter. Inspect model applicability before using predictions.",
                },
            )
        if not mcp_session_id or mcp_session_id not in SESSIONS:
            return _jsonrpc_err(rpc_id, -32002, "Session not initialized")
        if method == "tools/list":
            return _jsonrpc_ok(rpc_id, {"tools": TOOLS})
        if method != "tools/call":
            return _jsonrpc_err(rpc_id, -32601, f"Method not found: {method}")

        tool_name, arguments = params.get("name"), params.get("arguments") or {}
        base_url, auth_headers = await _resolve_runtime_access(arguments)
        if tool_name == "model.info":
            model_id = arguments.get("model_id")
            if model_id is not None and str(model_id).strip():
                data = _validate_info_response(await _facade_request(
                    base_url=base_url, auth_headers=auth_headers, method="GET", path=_path_for_model(str(model_id))
                ), model_id=str(model_id).strip())
            else:
                request_params: dict[str, Any] = {"limit": _limit(arguments.get("limit"))}
                cursor = arguments.get("cursor")
                if isinstance(cursor, str) and cursor.strip():
                    request_params["cursor"] = cursor.strip()
                data = _validate_info_response(await _facade_request(
                    base_url=base_url, auth_headers=auth_headers, method="GET", path=MODELS_PATH, params=request_params
                ), model_id=None)
        elif tool_name == "model.predict":
            model_id = str(arguments.get("model_id") or "").strip()
            inputs = arguments.get("inputs")
            if not model_id:
                raise ValueError("model_id is required")
            if not isinstance(inputs, dict):
                raise ValueError("inputs must be an object")
            body: dict[str, Any] = {"model_id": model_id, "inputs": inputs}
            for key in ("version", "request_id"):
                value = arguments.get(key)
                if isinstance(value, str) and value.strip():
                    body[key] = value.strip()
            data = _validate_predict_response(await _facade_request(
                base_url=base_url, auth_headers=auth_headers, method="POST", path=PREDICT_PATH, body=body
            ))
        else:
            return _jsonrpc_err(rpc_id, -32601, f"Unknown tool: {tool_name}")
        return _jsonrpc_ok(rpc_id, _tool_result(data))
    except (ValueError, httpx.HTTPError):
        return _jsonrpc_err(rpc_id, -32000, "ML inference MCP request failed")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="ML inference MCP internal error") from exc
