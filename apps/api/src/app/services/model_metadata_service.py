"""Provider discovery and edit protection for the model registry."""
from __future__ import annotations
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import httpx
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.model_registry import Model
from app.core.logging import get_logger
from app.core.http.tls import outbound_http_verify
from app.services.credential_service import CredentialService, CredentialError
from app.services.model_connector_profiles import build_model_auth_headers, get_healthcheck_paths
logger = get_logger(__name__)

def _map_modality_to_model_type(modality: str | None) -> Optional[str]:
    raw = str(modality or "").strip().lower()
    if not raw:
        return None
    if "embed" in raw:
        return "embedding"
    if "rerank" in raw:
        return "reranker"
    if "chat" in raw or "llm" in raw:
        return "llm_chat"
    return None


async def _resolve_model_api_key(model: Model, session: AsyncSession) -> Optional[str]:
    if model.instance_id:
        try:
            decrypted = await CredentialService(session).resolve_credentials(
                instance_id=model.instance_id,
                strategy="PLATFORM_FIRST",
            )
            if decrypted:
                payload = decrypted.payload or {}
                if decrypted.auth_type in {"api_key", "litellm_api_key"}:
                    return payload.get("api_key")
                if decrypted.auth_type == "token":
                    return payload.get("token")
                if decrypted.auth_type == "basic":
                    return payload.get("password")
        except CredentialError as exc:
            logger.warning("Failed to resolve model credentials for %s: %s", model.alias, exc)

    return None


async def _probe_manifest(
    base_url: str,
    *,
    connector: str | None = None,
    api_key: str | None = None,
    extra_config: Dict[str, Any] | None = None,
    provider_model_name: str | None = None,
) -> Tuple[Dict[str, Any], str]:
    normalized = base_url.rstrip("/")
    health_status = "unavailable"
    health_payload: Dict[str, Any] = {}
    headers = build_model_auth_headers(connector, api_key, extra_config=extra_config)
    async with httpx.AsyncClient(timeout=8.0, verify=outbound_http_verify()) as client:
        for path in get_healthcheck_paths(connector, extra_config=extra_config):
            try:
                started = time.perf_counter()
                health = await client.get(f"{normalized}/{path.lstrip('/')}", headers=headers)
                if health.status_code == 200:
                    health_status = "healthy"
                    if health.headers.get("content-type", "").startswith("application/json"):
                        health_payload.update(health.json())
                    if (health_payload.get("model_loaded") is False
                            or health_payload.get("status") in {"unavailable", "unhealthy", "error"}):
                        health_status = "unavailable"
                    health_payload["latency_ms"] = round((time.perf_counter() - started) * 1000)
                    break
            except Exception:
                continue

        first: Dict[str, Any] | None = None
        try:
            desc_resp = await client.get(f"{normalized}/description", headers=headers)
            if desc_resp.status_code == 200:
                desc_data = desc_resp.json()
                if isinstance(desc_data, dict):
                    first = desc_data
        except Exception:
            first = None

        if first is not None and provider_model_name and provider_model_name not in {first.get("alias"), first.get("name"), first.get("id")}:
            first = None
        if first is None:
            model_paths = ["/models"]
            if str(connector or "").strip().lower() == "litellm_http":
                model_paths = ["/v1/models", "/models"]

            resp = None
            last_error: str | None = None
            for path in model_paths:
                try:
                    candidate = await client.get(f"{normalized}/{path.lstrip('/')}", headers=headers)
                except Exception as exc:
                    last_error = str(exc)
                    continue
                if candidate.status_code < 400:
                    resp = candidate
                    break
                if candidate.status_code == 401:
                    raise ValueError("Authentication failed while probing model manifest")
                if candidate.status_code == 403:
                    raise ValueError("Access forbidden while probing model manifest")
                try:
                    body = candidate.json()
                    if isinstance(body, dict):
                        error = body.get("error")
                        if isinstance(error, dict):
                            last_error = str(error.get("message") or error.get("code") or candidate.text[:200])
                        else:
                            last_error = str(error or body.get("message") or candidate.text[:200])
                    else:
                        last_error = candidate.text[:200]
                except Exception:
                    last_error = candidate.text[:200]
            if resp is None:
                raise ValueError(last_error or "models_manifest_unreachable")
            resp.raise_for_status()
            data = resp.json()
            entries = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
            if not entries:
                raise ValueError("models_manifest_empty")
            if provider_model_name:
                first = next((item for item in entries if isinstance(item, dict) and provider_model_name in
                              {item.get("alias"), item.get("name"), item.get("id")}), None)
                if first is None:
                    raise ValueError("Selected deployment not found in model manifest")
            elif len(entries) == 1:
                first = entries[0]
            else:
                raise ValueError("Provider exposes multiple models; select provider_model_name before probing")
            if not isinstance(first, dict):
                raise ValueError("models_manifest_invalid")
        first["_health"] = health_payload
        return first, health_status


def _resolve_connector(model: Model) -> str:
    connector = getattr(model, "connector", None)
    if connector:
        return connector

    provider = (model.provider or "").lower()
    model_type = model.type.value if hasattr(model.type, "value") else str(model.type)
    if provider == "local" and model_type == "embedding":
        return "local_emb_http"
    if provider == "local" and model_type == "reranker":
        return "local_rerank_http"
    if provider == "local" and model_type == "llm_chat":
        return "local_llm_http"
    if provider == "litellm":
        return "litellm_http"
    if provider == "azure":
        return "azure_openai_http"
    return "openai_http"


def _resolve_base_url(model: Model) -> Optional[str]:
    if getattr(model, "base_url", None):
        return model.base_url
    state = inspect(model)
    if "instance" not in state.unloaded and model.instance is not None and getattr(model.instance, "url", None):
        return model.instance.url
    if model.extra_config and model.extra_config.get("base_url"):
        return model.extra_config.get("base_url")
    return None


def discovered_characteristics(manifest: dict, kind: str) -> dict:
    result = {}
    version = manifest.get("version")
    if isinstance(version, str) and version.strip():
        result["model_version"] = version
    mapping = {"context_window_tokens": "context_window_tokens"} if kind == "llm_chat" else {"max_input_tokens": "max_tokens"}
    if kind == "embedding":
        mapping["embedding_dimensions"] = "dimensions"
    for field, source in mapping.items():
        value = manifest.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            result[field] = value
    if kind == "embedding" and isinstance(manifest.get("normalized"), bool):
        result["vector_normalized"] = manifest["normalized"]
    return result


class ModelMetadataService:
    @staticmethod
    async def prepare_write(session: AsyncSession, data: dict, existing: Model | None = None) -> dict:
        data = dict(data)
        kind = str(getattr(existing.type, "value", existing.type)) if existing else str(data.get("type"))
        old_extra = dict(existing.extra_config or {}) if existing else {}
        old_manifest = old_extra.get("manifest") or {}
        incoming_extra = dict(data.get("extra_config") or old_extra)
        identity_changed = existing is not None and any(
            key in data and str(data[key] or "") != str(getattr(existing, key, None) or "")
            for key in ("provider_model_name", "base_url", "instance_id", "connector"))
        # A draft probe is informational. Re-observe it on save rather than
        # trusting a client-supplied manifest as service provenance.
        draft_manifest = incoming_extra.get("manifest")
        if "manifest" in incoming_extra and (existing is None or draft_manifest != old_manifest):
            candidate = Model(type=kind, provider=data.get("provider", ""),
                connector=data.get("connector", getattr(existing, "connector", None)),
                provider_model_name=data.get("provider_model_name", getattr(existing, "provider_model_name", "")),
                base_url=data.get("base_url", getattr(existing, "base_url", None)),
                instance_id=data.get("instance_id", getattr(existing, "instance_id", None)), extra_config=incoming_extra)
            if candidate.instance_id:
                candidate.instance_id = uuid.UUID(str(candidate.instance_id))
            base_url = candidate.base_url
            if not base_url and candidate.instance_id:
                from app.repositories.tool_instance_repository import ToolInstanceRepository
                instance = await ToolInstanceRepository(session).get_by_id(uuid.UUID(str(candidate.instance_id)))
                base_url = instance.url if instance else None
            try:
                if not base_url:
                    raise ValueError("No endpoint for model discovery")
                manifest, _ = await _probe_manifest(base_url, connector=candidate.connector,
                    api_key=await _resolve_model_api_key(candidate, session), extra_config=incoming_extra,
                    provider_model_name=candidate.provider_model_name)
            except (ValueError, httpx.HTTPError):
                manifest = {}
            manifest.pop("important_params", None)
            data.update(discovered_characteristics(manifest, kind))
            incoming_extra["manifest"] = manifest
            data["extra_config"] = incoming_extra
            data["capabilities_checked_at"] = datetime.now(timezone.utc) if manifest else None
            return data
        if identity_changed:
            incoming_extra.pop("manifest", None)
            data["extra_config"] = incoming_extra
            data["capabilities_checked_at"] = None
        else:
            for field in discovered_characteristics(old_manifest, kind):
                if field in data and data[field] != getattr(existing, field, None):
                    raise ValueError(f"{field} is supplied by the service; use Verify to refresh it")
            if "extra_config" in data and old_manifest:
                incoming_extra["manifest"] = old_manifest
                data["extra_config"] = incoming_extra
        return data
