"""
Storage path utilities for ML Portal
"""
from typing import List
from uuid import UUID
import hashlib


def get_tenant_prefix(tenant_id: UUID) -> str:
    """Get tenant prefix for storage paths"""
    return f"{tenant_id}"


def get_document_prefix(tenant_id: UUID, source_id: UUID) -> str:
    """Get document prefix for storage paths"""
    return f"{get_tenant_prefix(tenant_id)}/{source_id}"


def get_origin_path(tenant_id: UUID, source_id: UUID, filename: str, checksum: str, version: str = "v1") -> str:
    """Get origin file path with checksum for deduplication"""
    # Extract file extension
    if '.' in filename:
        name_part, ext = filename.rsplit('.', 1)
        return f"{get_document_prefix(tenant_id, source_id)}/original/{name_part}_{checksum}_{version}.{ext}"
    else:
        return f"{get_document_prefix(tenant_id, source_id)}/original/{filename}_{checksum}_{version}"


def get_extracted_path(tenant_id: UUID, source_id: UUID, checksum: str, version: str = "v1") -> str:
    """Get extracted text file path with checksum"""
    return f"{get_document_prefix(tenant_id, source_id)}/extracted/{checksum}_{version}.txt"


def get_canonical_path(tenant_id: UUID, source_id: UUID, checksum: str, version: str = "v1") -> str:
    """Get canonical file path with checksum"""
    return f"{get_document_prefix(tenant_id, source_id)}/canonical/{checksum}_{version}.jsonl"


def get_chunks_path(tenant_id: UUID, source_id: UUID, checksum: str, version: str = "v1") -> str:
    """Get chunks file path with checksum"""
    return f"{get_document_prefix(tenant_id, source_id)}/chunks/{checksum}_{version}.jsonl"


def get_embeddings_path(tenant_id: UUID, source_id: UUID, model_alias: str, checksum: str, version: str = "v1", batch_num: int = 0) -> str:
    """Get embeddings file path with checksum"""
    return f"{get_document_prefix(tenant_id, source_id)}/embeddings/{model_alias}/{checksum}_{version}/batch_{batch_num}.jsonl"


def get_embeddings_manifest_path(tenant_id: UUID, source_id: UUID, model_alias: str, checksum: str, version: str = "v1") -> str:
    """Get embeddings manifest path with checksum"""
    return f"{get_document_prefix(tenant_id, source_id)}/embeddings/{model_alias}/{checksum}_{version}/manifest.json"


def get_temp_path(tenant_id: UUID, source_id: UUID, step: str) -> str:
    """Get temporary file path"""
    return f"{get_document_prefix(tenant_id, source_id)}/temp/{step}"


def get_lock_key(tenant_id: UUID, source_id: UUID, step: str, model_alias: str = None) -> str:
    """Get Redis lock key"""
    if model_alias:
        return f"lock:{tenant_id}:{source_id}:{step}:{model_alias}"
    return f"lock:{tenant_id}:{source_id}:{step}"


def get_idempotency_key(tenant_id: UUID, source_id: UUID, step: str, model_alias: str = None, content_hash: str = None) -> str:
    """Get idempotency key"""
    parts = [str(tenant_id), str(source_id), step]
    if model_alias:
        parts.append(model_alias)
    if content_hash:
        parts.append(content_hash)
    return ":".join(parts)


def calculate_file_checksum(content: bytes) -> str:
    """Calculate SHA256 checksum for file content"""
    return hashlib.sha256(content).hexdigest()[:16]  # Use first 16 chars for shorter filenames


def calculate_text_checksum(text: str) -> str:
    """Calculate SHA256 checksum for text content"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
