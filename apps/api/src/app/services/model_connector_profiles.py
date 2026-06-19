from __future__ import annotations

from typing import Any, Mapping


LITELLM_HTTP_CONNECTOR = "litellm_http"


def get_extra_config(extra_config: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(extra_config, Mapping):
        return {}
    return dict(extra_config)
def build_model_auth_headers(
    connector: str | None,
    api_key: str | None,
    *,
    extra_config: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    if not api_key:
        return {}

    normalized = str(connector or "").strip().lower()
    extra = get_extra_config(extra_config)

    header_name = str(extra.get("auth_header_name") or "").strip()
    auth_scheme = str(extra.get("auth_scheme") or "").strip().lower()

    if not header_name:
        if normalized == LITELLM_HTTP_CONNECTOR:
            header_name = "x-litellm-api-key"
        else:
            header_name = "Authorization"

    if not auth_scheme:
        auth_scheme = "raw" if header_name.lower() != "authorization" else "bearer"

    if auth_scheme == "bearer":
        return {header_name: f"Bearer {api_key}"}
    return {header_name: api_key}


def get_healthcheck_paths(
    connector: str | None,
    *,
    extra_config: Mapping[str, Any] | None = None,
) -> list[str]:
    extra = get_extra_config(extra_config)
    configured = extra.get("healthcheck_paths")
    if isinstance(configured, list):
        values = [str(item).strip() for item in configured if str(item).strip()]
        if values:
            return values

    configured_single = str(extra.get("healthcheck_path") or "").strip()
    if configured_single:
        return [configured_single]

    normalized = str(connector or "").strip().lower()
    if normalized == LITELLM_HTTP_CONNECTOR:
        return ["/health/liveliness", "/health", "/models", "/v1/models"]
    return ["/health"]
