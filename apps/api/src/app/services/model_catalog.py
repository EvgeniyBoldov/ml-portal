from __future__ import annotations
from typing import List

class ModelCatalog:
    def list_llm(self, tenant_id: str | None = None) -> List[str]:
        return []

    def list_embeddings(self, tenant_id: str | None = None) -> List[str]:
        return []
