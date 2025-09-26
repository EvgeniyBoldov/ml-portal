from __future__ import annotations
from typing import List, Dict, Any

class RagSearchService:
    def __init__(self, index: Any):
        self._index = index

    def search(self, tenant_id: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
        return []
