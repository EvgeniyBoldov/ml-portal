"""Per-call credential resolution and explicit upstream authentication profiles."""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from helpers.observability import normalize_request_id, safe_target
from helpers.secret_broker import ResolvedCredential, SecretBrokerClient, extract_credential_access

logger = logging.getLogger("mcp.adapter_auth")


def _log_atom(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.:/@+-]", "_", str(value or "-"))[:120]


@dataclass(frozen=True)
class AuthProfile:
    kind: str = "standard"
    token_header: str = "Authorization"
    token_scheme: str = "Bearer"
    api_key_header: str = "X-API-Key"
    target_url_header: str = ""


def _value(payload: dict[str, Any], *keys: str, strip: bool = True) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip() if strip else value
            if normalized:
                return normalized
    raise ValueError("Credential is missing a required authentication field")


def _header(name: str, value: str) -> dict[str, str]:
    if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
        raise ValueError("Invalid authentication header name")
    if name.lower() in {"host", "content-length", "connection", "transfer-encoding"}:
        raise ValueError("Unsupported authentication header name")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Invalid authentication header value")
    return {name: value}


async def resolve_request_credential(
    arguments: dict[str, Any], *, timeout_s: int = 10, allow_raw: bool = False,
    request_id: str = "", server: str = "mcp", tool: str = "",
    trusted_broker_url: str | None = None,
) -> ResolvedCredential:
    access = extract_credential_access(arguments)
    request_id = normalize_request_id(request_id)
    context = arguments.get("instance_context")
    context = context if isinstance(context, dict) else {}
    nested_access = context.get("credential_access")
    top_level_access = arguments.get("credential_access")
    logger.info(
        "mcp_credential_context_received request_id=%s server=%s tool=%s access_present=%s "
        "top_level_access_type=%s nested_access_type=%s instance_context_type=%s "
        "token_present=%s resolve_url_present=%s data_instance_id=%s provider_instance_id=%s",
        request_id,
        _log_atom(server),
        _log_atom(tool),
        access is not None,
        type(top_level_access).__name__ if top_level_access is not None else "missing",
        type(nested_access).__name__ if nested_access is not None else "missing",
        type(arguments.get("instance_context")).__name__ if arguments.get("instance_context") is not None else "missing",
        bool(access and str(access.get("token") or "").strip()),
        bool(access and str(access.get("resolve_url") or "").strip()),
        _log_atom(context.get("data_instance_id")),
        _log_atom(context.get("provider_instance_id")),
    )
    if access is not None:
        if trusted_broker_url is not None and access.get("resolve_url") != trusted_broker_url:
            raise ValueError("Credential reference does not target the configured Portal broker")
        # Broker failure must never select a different credential or raw payload.
        return await SecretBrokerClient(timeout_s=timeout_s).resolve(
            access,
            request_id=request_id,
            server=server,
            tool=tool,
            data_instance_id=str(context.get("data_instance_id") or ""),
            provider_instance_id=str(context.get("provider_instance_id") or ""),
        )
    context = arguments.get("instance_context")
    if allow_raw and os.environ.get("ENV", "production").lower() in {"local", "dev", "development"}:
        if isinstance(context, dict) and isinstance(context.get("credentials"), dict):
            return ResolvedCredential(
                credential_id="", instance_id="", auth_type=str(context.get("auth_type") or ""),
                owner_type="", payload=dict(context["credentials"]), expires_at=0,
            )
    logger.warning(
        "mcp_credential_context_missing request_id=%s server=%s tool=%s "
        "top_level_access_type=%s nested_access_type=%s instance_context_type=%s",
        request_id,
        _log_atom(server),
        _log_atom(tool),
        type(top_level_access).__name__ if top_level_access is not None else "missing",
        type(nested_access).__name__ if nested_access is not None else "missing",
        type(arguments.get("instance_context")).__name__ if arguments.get("instance_context") is not None else "missing",
    )
    raise ValueError("A broker credential_access context is required")


def upstream_auth_headers(
    credential: ResolvedCredential, *, profile: AuthProfile = AuthProfile(),
    tool_name: str = "", target_url: str = "",
) -> dict[str, str]:
    """Never infer an authentication scheme from unrelated payload fields."""
    if profile.kind not in {"standard", "atlassian"}:
        raise ValueError("Unsupported authentication profile")
    payload = credential.payload
    auth_type = credential.auth_type.strip().lower()
    product = "Confluence" if tool_name.startswith("confluence_") else "Jira"
    if auth_type == "token":
        token = _value(
            payload, f"{product.lower()}_personal_token", "token", "pat",
            "personal_token", "personal_access_token", "api_token",
        )
        if profile.kind == "atlassian":
            if not target_url:
                raise ValueError("Atlassian authentication requires a data source URL")
            headers = _header(f"X-Atlassian-{product}-Personal-Token", token)
        else:
            headers = _header(profile.token_header, f"{profile.token_scheme} {token}".strip())
    elif auth_type in {"oauth", "bearer"}:
        headers = _header("Authorization", "Bearer " + _value(payload, "access_token", "token"))
    elif auth_type == "basic":
        username = _value(payload, "username", "email")
        password = _value(payload, "password", "api_token", strip=False)
        if ":" in username:
            raise ValueError("Basic authentication username cannot contain a colon")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers = {"Authorization": "Basic " + encoded}
    elif auth_type == "api_key":
        headers = _header(profile.api_key_header, _value(payload, "api_key"))
    else:
        raise ValueError("Unsupported credential auth_type")
    if profile.kind == "atlassian" and target_url:
        headers.update(_header(f"X-Atlassian-{product}-Url", target_url))
    elif profile.target_url_header:
        if not target_url:
            raise ValueError("Authentication profile requires a data source URL")
        headers.update(_header(profile.target_url_header, target_url))
    return headers


def data_source_url(arguments: dict[str, Any], payload: dict[str, Any], *, tool_name: str = "") -> str:
    context = arguments.get("instance_context")
    context = context if isinstance(context, dict) else {}
    config = context.get("config")
    config = config if isinstance(config, dict) else {}
    product_key = "confluence_url" if tool_name.startswith("confluence_") else "jira_url"
    for source, keys in (
        (context, ("data_instance_url",)),
        (config, (product_key, "base_url", "url")),
        (payload, (product_key, "base_url", "url")),
    ):
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().rstrip("/")
    return ""


def log_authentication_request(
    credential: ResolvedCredential, *, profile: AuthProfile, headers: dict[str, str],
    request_id: str, tool_name: str, target_url: str,
) -> None:
    """Allowlisted auth metadata and a masked preview, never arbitrary payloads."""
    product = "confluence" if tool_name.startswith("confluence_") else "jira"
    aliases = {
        "token": (f"{product}_personal_token", "token", "pat", "personal_token", "personal_access_token", "api_token"),
        "basic": ("username", "email", "password", "api_token"),
        "oauth": ("access_token", "token"),
        "bearer": ("access_token", "token"),
        "api_key": ("api_key",),
    }.get(credential.auth_type.strip().lower(), ())
    fields_present = {
        key: isinstance(credential.payload.get(key), str) and bool(credential.payload[key])
        for key in aliases
    }
    preview = {}
    for name, value in headers.items():
        if name.lower() == "authorization":
            # Scheme is chosen by the adapter, never take arbitrary text from a token.
            scheme = value.partition(" ")[0]
            preview[name] = f"{scheme} ***" if scheme in {"Basic", "Bearer", "Token"} else "***"
        elif name.lower() in {"x-atlassian-jira-url", "x-atlassian-confluence-url"}:
            preview[name] = safe_target(value)
        else:
            preview[name] = "***"
    username = "-"
    if credential.auth_type.strip().lower() == "basic":
        username = _log_atom(_value(credential.payload, "username", "email"))
    logger.info(
        "mcp_authentication_request request_id=%s tool=%s credential_id=%s profile=%s "
        "auth_type=%s target=%s username=%s credential_fields_present=%s "
        "headers=%s auth_in_body=false",
        normalize_request_id(request_id), _log_atom(tool_name), _log_atom(credential.credential_id),
        _log_atom(profile.kind), _log_atom(credential.auth_type), safe_target(target_url), username,
        json.dumps(fields_present, sort_keys=True), json.dumps(preview, sort_keys=True),
    )
