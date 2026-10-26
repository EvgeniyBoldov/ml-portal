from __future__ import annotations

import json
import os
import re
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
MAX_RESPONSE_BYTES = int(os.environ.get("ML_INFERENCE_MAX_RESPONSE_BYTES", "262144"))
MODELS_PATH = os.environ.get("ML_INFERENCE_MODELS_PATH", "/v1/models")
PREDICT_PATH = os.environ.get("ML_INFERENCE_PREDICT_PATH", "/v1/responses")
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


def _path_for_model(model_id: str) -> str:
    normalized = str(model_id or "").strip()
    # Keep this in sync with ResponseRequest.model in ML-Inference-Service.
    # Its path parameter cannot represent slashes, and deployment names are
    # restricted to this identifier alphabet.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}", normalized):
        raise ValueError("model_id must be a valid deployed model identifier")
    return f"{MODELS_PATH.rstrip('/')}/{quote(normalized, safe='._-')}"


def _assert_bounded(data: Any) -> Any:
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise ValueError("ML inference response exceeds the configured MCP result limit")
    return data


def _validate_info_response(data: Any, *, model_id: str | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("ML inference facade returned an invalid model info response")
    if model_id:
        deployment = data.get("deployment")
        if (
            data.get("object") != "model"
            or not isinstance(data.get("id"), str)
            or not isinstance(data.get("input_schema"), dict)
            or not isinstance(data.get("output_schema"), dict)
            or not isinstance(deployment, dict)
            or not isinstance(deployment.get("version"), str)
        ):
            raise ValueError("ML inference facade returned an invalid detailed model card")
    else:
        models = data.get("data")
        if data.get("object") != "list" or not isinstance(models, list):
            raise ValueError("ML inference facade returned an invalid model catalog")
        for model in models:
            if (
                not isinstance(model, dict)
                or not isinstance(model.get("id"), str)
                or not isinstance(model.get("input_schema"), dict)
                or not isinstance(model.get("output_schema"), dict)
            ):
                raise ValueError("ML inference facade returned a model without input/output contracts")
    return data


def _validate_predict_response(data: Any) -> dict[str, Any]:
    if (
        not isinstance(data, dict)
        or data.get("object") != "response"
        or not isinstance(data.get("id"), str)
        or data.get("status") != "completed"
        or not isinstance(data.get("output"), list)
    ):
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
    headers = {"Accept": "application/json", "Content-Type": "application/json", **auth_headers}
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
            "List active ML models with their input_schema and output_schema contracts, or inspect one by model_id "
            "to get its description and deployed version. Use the returned input_schema to construct model.predict inputs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$",
                    "description": "Optional stable model identifier. Omit to list available models.",
                },
            },
        },
        "outputSchema": {
            "type": "object",
            "oneOf": [
                {
                    "required": ["object", "data"],
                    "properties": {
                        "object": {"const": "list"},
                        "data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["id", "input_schema", "output_schema", "version"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "input_schema": {"type": "object"},
                                    "output_schema": {"type": "object"},
                                    "version": {"type": "string"},
                                    "deployment": {"type": ["object", "null"]},
                                },
                            },
                        },
                    },
                },
                {
                    "required": ["id", "object", "input_schema", "output_schema", "deployment"],
                    "properties": {
                        "id": {"type": "string"},
                        "object": {"const": "model"},
                        "input_schema": {"type": "object"},
                        "output_schema": {"type": "object"},
                        "deployment": {
                            "type": "object",
                            "required": ["version", "status"],
                            "properties": {"version": {"type": "string"}, "status": {"type": "string"}},
                        },
                    },
                },
            ],
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "model.predict",
        "description": (
            "Run one registered ML model by its model_id, passing inputs as JSON that conforms to the input_schema from model.info. "
            "The facade selects the active deployed version."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$",
                    "description": "Stable identifier returned by model.info.",
                },
                # ML-Inference-Service accepts input: Any. Keep the tool
                # contract open and let the model's input_schema define shape.
                "inputs": {"description": "JSON input conforming to input_schema returned by model.info."},
            },
            "required": ["model_id", "inputs"],
        },
        "outputSchema": {
            "type": "object",
            "required": ["id", "object", "created_at", "status", "model", "model_version", "output"],
            "properties": {
                "id": {"type": "string"},
                "object": {"const": "response"},
                "created_at": {"type": "number"},
                "status": {"type": "string"},
                "model": {"type": "string"},
                "model_version": {"type": "string"},
                "output": {"type": "array"},
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
                data = _validate_info_response(await _facade_request(
                    base_url=base_url, auth_headers=auth_headers, method="GET", path=MODELS_PATH
                ), model_id=None)
        elif tool_name == "model.predict":
            model_id = str(arguments.get("model_id") or "").strip()
            if "inputs" not in arguments:
                raise ValueError("inputs is required")
            if not model_id:
                raise ValueError("model_id is required")
            _path_for_model(model_id)
            inputs = arguments["inputs"]
            body: dict[str, Any] = {"model": model_id, "input": inputs}
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
