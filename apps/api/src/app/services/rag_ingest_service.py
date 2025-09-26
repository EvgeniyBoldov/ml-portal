from __future__ import annotations
from typing import Dict, Any, Optional

class DocumentMeta(dict):
    pass

class RagIngestService:
    def __init__(self, emb_client: Any, storage: Any, index: Any):
        self._emb = emb_client
        self._storage = storage
        self._index = index

    def register_source(self, tenant_id: str, kind: str, uri: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"id": "src_001", "tenant_id": tenant_id, "kind": kind, "uri": uri, "meta": meta or {}}

    def ingest_document(self, tenant_id: str, source_id: str, uri_or_path: str, overwrite: bool = False) -> DocumentMeta:
        return DocumentMeta(id="doc_001", tenant_id=tenant_id, source_id=source_id, uri=uri_or_path)

    def reindex(self, tenant_id: str, source_id: Optional[str] = None) -> int:
        return 0
