from __future__ import annotations

from typing import Any, Dict, Optional


DOCUMENT_ARTIFACT_KINDS = {"original", "extracted", "canonical", "chunks"}

_LEGACY_META_KEYS = {
    "filename",
    "title",
    "content_type",
    "size",
    "size_bytes",
    "language",
    "source",
    "scope",
    "tags",
    "s3_key",
    "extracted_key",
    "canonical_key",
    "chunks_key",
    "collection_id",
    "collection_row_id",
    "qdrant_collection_name",
}


def normalize_document_source_meta(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize Source.meta into an explicit document artifact contract.

    New canonical shape:
    - document: file and semantic metadata
    - collection: collection binding context
    - artifacts: original/extracted/canonical/chunks storage artifacts

    Legacy top-level keys are lifted into this shape and dropped from the
    normalized result so new writes stay deterministic.
    """
    raw = dict(meta or {})

    document = dict(raw.get("document") or {})
    collection = dict(raw.get("collection") or {})
    artifacts = dict(raw.get("artifacts") or {})

    if raw.get("filename") and "filename" not in document:
        document["filename"] = raw["filename"]
    if raw.get("title") and "title" not in document:
        document["title"] = raw["title"]
    if raw.get("content_type") and "content_type" not in document:
        document["content_type"] = raw["content_type"]
    if raw.get("language") and "language" not in document:
        document["language"] = raw["language"]
    if raw.get("source") and "source" not in document:
        document["source"] = raw["source"]
    if raw.get("scope") and "scope" not in document:
        document["scope"] = raw["scope"]
    if raw.get("tags") is not None and "tags" not in document:
        document["tags"] = raw["tags"]

    size_bytes = raw.get("size_bytes", raw.get("size"))
    if size_bytes is not None and "size_bytes" not in document:
        document["size_bytes"] = size_bytes

    if raw.get("collection_id") and "id" not in collection:
        collection["id"] = raw["collection_id"]
    if raw.get("collection_row_id") and "row_id" not in collection:
        collection["row_id"] = raw["collection_row_id"]
    if raw.get("qdrant_collection_name") and "qdrant_collection_name" not in collection:
        collection["qdrant_collection_name"] = raw["qdrant_collection_name"]

    original = dict(artifacts.get("original") or {})
    if raw.get("s3_key") and "key" not in original:
        original["key"] = raw["s3_key"]
    if document.get("filename") and "filename" not in original:
        original["filename"] = document["filename"]
    if document.get("content_type") and "content_type" not in original:
        original["content_type"] = document["content_type"]
    if document.get("size_bytes") is not None and "size_bytes" not in original:
        original["size_bytes"] = document["size_bytes"]
    if original.get("key"):
        original.setdefault("available", True)

    extracted = dict(artifacts.get("extracted") or {})
    if raw.get("extracted_key") and "key" not in extracted:
        extracted["key"] = raw["extracted_key"]
    if extracted.get("key"):
        extracted.setdefault("content_type", "text/plain")
        extracted.setdefault("available", True)

    canonical = dict(artifacts.get("canonical") or {})
    if raw.get("canonical_key") and "key" not in canonical:
        canonical["key"] = raw["canonical_key"]
    if canonical.get("key"):
        canonical.setdefault("content_type", "application/json")
        canonical.setdefault("format", "canonical_document_v1")
        canonical.setdefault("available", True)

    chunks = dict(artifacts.get("chunks") or {})
    if raw.get("chunks_key") and "key" not in chunks:
        chunks["key"] = raw["chunks_key"]
    if chunks.get("key"):
        chunks.setdefault("content_type", "application/x-ndjson")
        chunks.setdefault("available", True)

    normalized = {
        key: value
        for key, value in raw.items()
        if key not in _LEGACY_META_KEYS and key not in {"document", "collection", "artifacts"}
    }
    normalized["document"] = document
    normalized["collection"] = collection
    normalized["artifacts"] = {
        "original": original,
        "extracted": extracted,
        "canonical": canonical,
        "chunks": chunks,
    }
    return normalized


def build_document_source_meta(
    *,
    filename: str,
    title: Optional[str],
    content_type: Optional[str],
    size_bytes: int,
    original_key: str,
    collection_id: Optional[str] = None,
    row_id: Optional[str] = None,
    qdrant_collection_name: Optional[str] = None,
    source: Optional[str] = None,
    scope: Optional[str] = None,
    tags: Optional[list[str]] = None,
    language: str = "en",
) -> Dict[str, Any]:
    meta = normalize_document_source_meta(None)
    meta["document"] = {
        "filename": filename,
        "title": title or filename,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "language": language,
        "source": source,
        "scope": scope,
        "tags": tags or [],
    }
    meta["collection"] = {
        "id": collection_id,
        "row_id": row_id,
        "qdrant_collection_name": qdrant_collection_name,
    }
    meta["artifacts"]["original"] = {
        "key": original_key,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "available": True,
    }
    return meta


def upsert_document_artifact(
    meta: Optional[Dict[str, Any]],
    kind: str,
    artifact: Dict[str, Any],
) -> Dict[str, Any]:
    if kind not in DOCUMENT_ARTIFACT_KINDS:
        raise ValueError(f"Unsupported document artifact kind: {kind}")

    normalized = normalize_document_source_meta(meta)
    merged = dict(normalized["artifacts"].get(kind) or {})
    merged.update(artifact)
    if merged.get("key"):
        merged["available"] = True
    normalized["artifacts"][kind] = merged
    return normalized


def get_document_artifact(meta: Optional[Dict[str, Any]], kind: str) -> Dict[str, Any]:
    if kind not in DOCUMENT_ARTIFACT_KINDS:
        raise ValueError(f"Unsupported document artifact kind: {kind}")
    normalized = normalize_document_source_meta(meta)
    return dict(normalized["artifacts"].get(kind) or {})


def get_document_artifact_key(meta: Optional[Dict[str, Any]], kind: str) -> Optional[str]:
    artifact = get_document_artifact(meta, kind)
    return artifact.get("key")
