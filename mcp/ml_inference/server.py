from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import httpx
from fastapi import FastAPI, Header, Request, Response
from jsonschema import SchemaError
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import Unresolvable

from portal_mcp_contract import MCPFailure, MCPFailureCategory, MCPFailureKind, public_user_message, safe_diagnostic

from helpers.adapter_auth import AuthProfile, resolve_request_credential, upstream_auth_headers
from helpers.observability import (
    UpstreamHTTPError,
    log_mcp_event,
    normalize_request_id,
    safe_error_detail,
    safe_target,
)


app = FastAPI(title="ML Inference MCP Shim", version="1.0.0")
logger = logging.getLogger("mcp.ml_inference")

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


def _jsonrpc_err(
    rpc_id: Any, code: int, message: str, data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": rpc_id, "error": error}


class PredictionInputError(ValueError):
    def __init__(self, message: str, *, param: str = "inputs", validator: str = "json") -> None:
        super().__init__(message)
        self.details = {"param": param, "validator": validator}


# Only expose known service codes with static messages. Provider messages may
# contain the input value (jsonschema), stack traces or credential material.
_FACADE_ERRORS = {
    "SCHEMA_VALIDATION_ERROR": "Model input does not match input_schema. Inspect model.info and correct inputs.",
    "MODEL_NOT_FOUND": "The requested model has no active deployment. Inspect model.info.",
    "INVALID_API_KEY": "The inference service rejected authentication credentials.",
    "INSUFFICIENT_PERMISSIONS": "The inference account lacks permission for this operation.",
    "SERVICE_OVERLOADED": "Inference prediction capacity is exhausted. Try again later.",
    "MODEL_PREDICTION_TIMEOUT": "Model prediction timed out.",
    "MODEL_PREDICTION_FAILED": "Model prediction failed in the inference service.",
    "MODEL_SIGNATURE_INVALID": "The deployed model schema is invalid.",
    "MODEL_OUTPUT_VALIDATION_FAILED": "Model output does not match its schema.",
    "RUNTIME_UNAVAILABLE": "The model runtime is unavailable.",
}


def _normalize_prediction_inputs(inputs: Any, schema: dict[str, Any]) -> Any:
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    # Never fetch schema references over the network from provider metadata.
    validator = validator_class(schema, registry=Registry())
    try:
        json.dumps(inputs, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise PredictionInputError("inputs must contain finite JSON values.") from exc
    errors = list(validator.iter_errors(inputs))
    if not errors:
        return inputs
    if isinstance(inputs, str):
        try:
            decoded = json.loads(inputs)
            json.dumps(decoded, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise PredictionInputError(
                "inputs does not match input_schema and is not valid encoded JSON. "
                "Pass the JSON value required by model.info."
            ) from exc
        errors = list(validator.iter_errors(decoded))
        if not errors:
            return decoded
    error = errors[0]
    param = "inputs" + "".join(f".{part}" for part in error.absolute_path)
    rule = str(error.validator)
    hint = ""
    if rule == "type":
        hint = f" Expected type: {error.validator_value}."
    elif rule == "required":
        missing = [key for key in error.validator_value if key not in error.instance]
        hint = f" Missing required fields: {', '.join(missing)}."
    raise PredictionInputError(
        str(safe_diagnostic(f"{param}: input_schema validation failed ({rule}).{hint} Correct inputs using model.info."))[:2000],
        param=str(safe_diagnostic(param))[:300], validator=rule,
    )


def _failure_response(rpc_id: Any, exc: Exception, *, request_id: str, stage: str) -> dict[str, Any]:
    status = getattr(exc, "status_code", None)
    category = {
        400: MCPFailureCategory.INPUT, 422: MCPFailureCategory.INPUT,
        401: MCPFailureCategory.AUTH, 403: MCPFailureCategory.ACCESS,
        429: MCPFailureCategory.RATE_LIMIT,
    }.get(status, MCPFailureCategory.AVAILABILITY if status and status >= 500 else MCPFailureCategory.UNKNOWN)
    code: str = f"http_{status}" if status else type(exc).__name__
    message = "ML inference MCP request failed."
    details = None
    if isinstance(exc, PredictionInputError):
        category, code, message, details = MCPFailureCategory.INPUT, "SCHEMA_VALIDATION_ERROR", str(exc), exc.details
    elif isinstance(exc, UpstreamHTTPError):
        code = getattr(exc, "service_code", None) or code
        message = _FACADE_ERRORS.get(code, f"Inference service returned HTTP {status}.")
        details = getattr(exc, "details", None)
    elif isinstance(exc, httpx.TimeoutException):
        category, message = MCPFailureCategory.AVAILABILITY, "Inference service request timed out."
    elif isinstance(exc, httpx.HTTPError):
        category, message = MCPFailureCategory.AVAILABILITY, "Could not reach the inference service."
    elif isinstance(exc, (SchemaError, Unresolvable)) or stage in {"model_schema", "response_validation", "facade_request"}:
        message = "Inference service returned an invalid model contract or response."
    kind = MCPFailureKind.TOOL
    if status:
        kind = MCPFailureKind.HTTP
    elif isinstance(exc, httpx.HTTPError):
        kind = MCPFailureKind.TRANSPORT
    elif isinstance(exc, (SchemaError, Unresolvable)) or stage in {"model_schema", "response_validation", "facade_request"}:
        kind = MCPFailureKind.PROTOCOL
    rpc_code = -32602 if isinstance(exc, PredictionInputError) else -32000
    failure = MCPFailure(
        kind=kind,
        category=category, code=code, message=message, details=details,
        request_id=request_id, stage=stage, http_status=status, rpc_code=rpc_code,
        user_message=public_user_message(category),
    ).bounded_dump()
    return _jsonrpc_err(rpc_id, rpc_code, message, failure)


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


async def _resolve_runtime_access(
    arguments: dict[str, Any], *, request_id: str, tool_name: str,
) -> tuple[str, dict[str, str], Any]:
    resolved = await resolve_request_credential(
        arguments, timeout_s=BROKER_TIMEOUT_SECONDS,
        allow_raw=os.environ.get("MCP_ADAPTER_ALLOW_RAW_CREDENTIALS", "false").lower() == "true",
        request_id=request_id,
        server="ml-inference",
        tool=tool_name,
    )
    base_url = _extract_base_url(resolved.payload, arguments)
    auth_headers = upstream_auth_headers(
        resolved, profile=AuthProfile(),
    )
    context = arguments.get("instance_context")
    context = context if isinstance(context, dict) else {}
    log_mcp_event(
        logger,
        outcome="completed",
        request_id=request_id,
        server="ml-inference",
        method="tools/call",
        tool=tool_name,
        stage="upstream_authentication",
        target=safe_target(base_url),
        data_instance_id=str(context.get("data_instance_id") or resolved.instance_id),
        provider_instance_id=str(context.get("provider_instance_id") or ""),
        credential_id=resolved.credential_id,
        auth_type=resolved.auth_type,
        auth_headers=",".join(sorted(auth_headers)),
    )
    return base_url, auth_headers, resolved


def _path_for_model(model_id: str) -> str:
    normalized = str(model_id or "").strip()
    # Keep this in sync with ResponseRequest.model in ML-Inference-Service.
    # Its path parameter cannot represent slashes, and deployment names are
    # restricted to this identifier alphabet.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}", normalized):
        raise PredictionInputError("model_id must be a valid deployed model identifier", param="model_id")
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
    request_id: str,
    tool_name: str,
    route_name: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    verify: bool | str = ML_INFERENCE_CA_BUNDLE if ML_INFERENCE_CA_BUNDLE else VERIFY_SSL
    headers = {"Accept": "application/json", "Content-Type": "application/json", **auth_headers}
    started = time.monotonic()
    target = safe_target(base_url)
    logger.info(
        "ml_inference_facade_request_started request_id=%s tool=%s method=%s route=%s target=%s auth_headers=%s",
        request_id,
        tool_name,
        method,
        route_name,
        target,
        ",".join(sorted(auth_headers)),
    )
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, verify=verify) as client:
            response = await client.request(method, f"{base_url}{path}", headers=headers, params=params, json=body)
    except httpx.HTTPError as exc:
        logger.warning(
            "ml_inference_facade_request_failed request_id=%s tool=%s method=%s route=%s target=%s "
            "duration_ms=%s error_type=%s error_detail=%s",
            request_id,
            tool_name,
            method,
            route_name,
            target,
            int((time.monotonic() - started) * 1000),
            type(exc).__name__,
            safe_error_detail(exc),
        )
        raise
    logger.info(
        "ml_inference_facade_response_received request_id=%s tool=%s method=%s route=%s target=%s "
        "status=%s response_bytes=%s duration_ms=%s",
        request_id,
        tool_name,
        method,
        route_name,
        target,
        response.status_code,
        len(response.content),
        int((time.monotonic() - started) * 1000),
    )
    if response.status_code >= 400:
        error = UpstreamHTTPError(response.status_code)
        # Read only the bounded error contract; never forward arbitrary bodies.
        if len(response.content) <= MAX_RESPONSE_BYTES:
            try:
                envelope = response.json()
                source = envelope.get("error") if isinstance(envelope, dict) else None
                if isinstance(source, dict) and source.get("code") in _FACADE_ERRORS:
                    error.service_code = source["code"]
                    error.details = {"source_code": source["code"]}
                    param = source.get("param")
                    if isinstance(param, str) and re.fullmatch(r"input(?:\.[A-Za-z_][A-Za-z0-9_]*|\.[0-9]+)*", param) and len(param) <= 200:
                        error.details["param"] = "inputs" + param[5:]
            except (ValueError, TypeError):
                pass
        raise error
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
            "x-runtime": {"risk_level": "safe"},
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
            "x-runtime": {"risk_level": "safe"},
            "properties": {
                "model_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$",
                    "description": "Stable identifier returned by model.info.",
                },
                # ML-Inference-Service accepts input: Any. Keep the tool
                # contract open and let the model's input_schema define shape.
                "inputs": {"description": "Pass the JSON value required by model.info input_schema (for objects, pass an object, not JSON text). Encoded JSON strings are decoded only when the original string fails that schema."},
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
    x_portal_request_id: str | None = Header(default=None),
) -> dict[str, Any]:
    started = time.monotonic()
    request_id = normalize_request_id(x_portal_request_id)
    method = "unknown"
    tool_name = ""
    stage = "request_parse"
    rpc_id: Any = None
    context: dict[str, Any] = {}
    try:
        payload = await request.json()
        rpc_id, method, params = payload.get("id"), payload.get("method"), payload.get("params") or {}
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
            log_mcp_event(
                logger,
                outcome="failed",
                request_id=request_id,
                server="ml-inference",
                method=str(method),
                stage="session_validation",
                duration_ms=int((time.monotonic() - started) * 1000),
                error_type="SessionNotInitialized",
                rpc_code=-32002,
            )
            return _jsonrpc_err(rpc_id, -32002, "Session not initialized")
        if method == "tools/list":
            return _jsonrpc_ok(rpc_id, {"tools": TOOLS})
        if method != "tools/call":
            log_mcp_event(
                logger,
                outcome="failed",
                request_id=request_id,
                server="ml-inference",
                method=str(method),
                stage="method_dispatch",
                duration_ms=int((time.monotonic() - started) * 1000),
                error_type="MethodNotFound",
                rpc_code=-32601,
            )
            return _jsonrpc_err(rpc_id, -32601, f"Method not found: {method}")

        tool_name, arguments = params.get("name"), params.get("arguments") or {}
        tool_name = str(tool_name or "")
        context = arguments.get("instance_context") if isinstance(arguments, dict) else None
        context = context if isinstance(context, dict) else {}
        log_mcp_event(
            logger,
            outcome="started",
            request_id=request_id,
            server="ml-inference",
            method=str(method),
            tool=tool_name,
            stage="tool_call_received",
            target=safe_target(str(context.get("data_instance_url") or "")),
            data_instance_id=str(context.get("data_instance_id") or ""),
            provider_instance_id=str(context.get("provider_instance_id") or ""),
        )
        stage = "credential_resolution"
        base_url, auth_headers, resolved = await _resolve_runtime_access(
            arguments, request_id=request_id, tool_name=tool_name,
        )
        stage = "facade_request"
        if tool_name == "model.info":
            model_id = arguments.get("model_id")
            if model_id is not None and str(model_id).strip():
                raw_data = await _facade_request(
                    base_url=base_url, auth_headers=auth_headers, method="GET", path=_path_for_model(str(model_id)),
                    request_id=request_id, tool_name=tool_name, route_name="model.info.detail",
                )
            else:
                raw_data = await _facade_request(
                    base_url=base_url, auth_headers=auth_headers, method="GET", path=MODELS_PATH,
                    request_id=request_id, tool_name=tool_name, route_name="model.info.catalog",
                )
            stage = "response_validation"
            normalized_model_id = (
                str(model_id).strip()
                if model_id is not None and str(model_id).strip()
                else None
            )
            data = _validate_info_response(raw_data, model_id=normalized_model_id)
        elif tool_name == "model.predict":
            model_id = str(arguments.get("model_id") or "").strip()
            stage = "input_validation"
            if "inputs" not in arguments:
                raise PredictionInputError("inputs is required")
            if not model_id:
                raise PredictionInputError("model_id is required", param="model_id")
            _path_for_model(model_id)
            stage = "model_schema"
            card = _validate_info_response(await _facade_request(
                base_url=base_url, auth_headers=auth_headers, method="GET", path=_path_for_model(model_id),
                request_id=request_id, tool_name=tool_name, route_name="model.predict.schema",
            ), model_id=model_id)
            stage = "input_validation"
            inputs = _normalize_prediction_inputs(arguments["inputs"], card["input_schema"])
            stage = "facade_request"
            body: dict[str, Any] = {"model": model_id, "input": inputs}
            raw_data = await _facade_request(
                base_url=base_url, auth_headers=auth_headers, method="POST", path=PREDICT_PATH, body=body,
                request_id=request_id, tool_name=tool_name, route_name="model.predict",
            )
            stage = "response_validation"
            data = _validate_predict_response(raw_data)
        else:
            log_mcp_event(
                logger,
                outcome="failed",
                request_id=request_id,
                server="ml-inference",
                method=str(method),
                tool=tool_name,
                stage="tool_dispatch",
                duration_ms=int((time.monotonic() - started) * 1000),
                error_type="ToolNotFound",
                rpc_code=-32601,
            )
            return _jsonrpc_err(rpc_id, -32601, f"Unknown tool: {tool_name}")
        log_mcp_event(
            logger,
            outcome="completed",
            request_id=request_id,
            server="ml-inference",
            method=str(method),
            tool=tool_name,
            stage="completed",
            duration_ms=int((time.monotonic() - started) * 1000),
            target=safe_target(base_url),
            data_instance_id=str(context.get("data_instance_id") or ""),
            provider_instance_id=str(context.get("provider_instance_id") or ""),
            credential_id=resolved.credential_id,
            auth_type=resolved.auth_type,
            response_bytes=len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
        )
        return _jsonrpc_ok(rpc_id, _tool_result(data))
    except (ValueError, httpx.HTTPError) as exc:
        status_code = getattr(exc, "status_code", None)
        if status_code is None:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
        log_mcp_event(
            logger,
            outcome="failed",
            request_id=request_id,
            server="ml-inference",
            method=str(method),
            tool=tool_name,
            stage=stage,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__,
            http_status=status_code,
            rpc_code=-32602 if isinstance(exc, PredictionInputError) else -32000,
            target=safe_target(base_url) if "base_url" in locals() else "",
            data_instance_id=str(context.get("data_instance_id") or ""),
            provider_instance_id=str(context.get("provider_instance_id") or ""),
            credential_id=resolved.credential_id if "resolved" in locals() else "",
            auth_type=resolved.auth_type if "resolved" in locals() else "",
            error_detail=type(exc).__name__ if isinstance(exc, SchemaError) else safe_error_detail(exc),
        )
        return _failure_response(rpc_id, exc, request_id=request_id, stage=stage)
    except Exception as exc:
        log_mcp_event(
            logger,
            outcome="failed",
            request_id=request_id,
            server="ml-inference",
            method=str(method),
            tool=tool_name,
            stage=stage,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_type=type(exc).__name__,
            rpc_code=-32603,
            target=safe_target(base_url) if "base_url" in locals() else "",
            data_instance_id=str(context.get("data_instance_id") or ""),
            provider_instance_id=str(context.get("provider_instance_id") or ""),
            credential_id=resolved.credential_id if "resolved" in locals() else "",
            auth_type=resolved.auth_type if "resolved" in locals() else "",
            error_detail=type(exc).__name__ if isinstance(exc, SchemaError) else safe_error_detail(exc),
        )
        return _failure_response(rpc_id, exc, request_id=request_id, stage=stage)
