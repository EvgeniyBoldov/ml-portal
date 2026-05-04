from __future__ import annotations

from uuid import uuid4

from app.storage.paths import get_embeddings_path


def test_embeddings_path_uses_jsonl_extension():
    tenant_id = uuid4()
    source_id = uuid4()
    key = get_embeddings_path(tenant_id, source_id, "emb.mini.l6", "abc123", "v1", 0)
    assert key.endswith(".jsonl")
    assert "/embeddings/emb.mini.l6/" in key
