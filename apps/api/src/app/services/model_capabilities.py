"""Canonical encoder/reranker attributes and stable vector-space identity."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelCapabilities(BaseModel):
    embedding_dimensions: int | None = Field(None, ge=1)
    max_input_tokens: int | None = Field(None, ge=1)
    vector_normalized: bool | None = None
    model_version: str | None = None
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    @classmethod
    def from_model(cls, model: Any) -> "ModelCapabilities":
        extra = getattr(model, "extra_config", None) or {}
        manifest = extra.get("manifest") or {}
        return cls(
            embedding_dimensions=getattr(model, "embedding_dimensions", None) or extra.get("vector_dim") or extra.get("dimensions"),
            max_input_tokens=getattr(model, "max_input_tokens", None) or extra.get("max_tokens") or manifest.get("max_tokens"),
            vector_normalized=getattr(model, "vector_normalized", None),
            model_version=getattr(model, "model_version", None) or manifest.get("version"),
        )

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any], *, embedding: bool) -> "ModelCapabilities":
        return cls(
            embedding_dimensions=manifest.get("dimensions") if embedding else None,
            max_input_tokens=manifest.get("max_tokens"),
            vector_normalized=manifest.get("normalized") if embedding else None,
            model_version=str(manifest.get("version") or "") or None,
        )


def embedding_fingerprint(model: Any, capabilities: ModelCapabilities | None = None, *, include_input_policy: bool = True) -> str:
    caps = capabilities or ModelCapabilities.from_model(model)
    if not caps.embedding_dimensions:
        raise ValueError(f"Embedding dimensions are unknown for '{model.alias}'; verify the model or configure them explicitly")
    from app.services.bounded_embeddings import INPUT_POLICY_VERSION
    from app.core.config import get_settings
    identity = {
        "input_policy": INPUT_POLICY_VERSION, "token_reserve": get_settings().EMB_INPUT_TOKEN_RESERVE,
        "model_id": str(model.id), "provider_model": model.provider_model_name,
        "dimensions": caps.embedding_dimensions, "version": caps.model_version,
        "normalized": caps.vector_normalized, "max_input_tokens": caps.max_input_tokens, "revision": (getattr(model, "extra_config", None) or {}).get("revision"),
    }
    if not include_input_policy:
        identity.pop("input_policy")
        identity.pop("token_reserve")
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]


def normalize_capability_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate legacy writes once; the typed fields remain authoritative."""
    result = dict(payload)
    kind = str(getattr(result.get("type"), "value", result.get("type")))
    if kind not in {"embedding", "reranker"}:
        return result
    extra = dict(result.get("extra_config") or {})
    legacy = {"embedding_dimensions": extra.get("vector_dim") or extra.get("dimensions"),
              "max_input_tokens": extra.get("max_tokens")}
    for field, value in legacy.items():
        if result.get(field) is None and value is not None and (field != "embedding_dimensions" or kind == "embedding"):
            result[field] = value
    caps = ModelCapabilities(**{key: result.get(key) for key in ModelCapabilities.model_fields})
    if kind != "embedding" and caps.embedding_dimensions is not None:
        raise ValueError("Only embedding models have embedding_dimensions")
    result.update({key: value for key, value in caps.model_dump().items() if key in result or value is not None})
    for key in ["vector_dim", "dimensions", "max_tokens"]:
        extra.pop(key, None)
    result["extra_config"] = extra or None
    return result
