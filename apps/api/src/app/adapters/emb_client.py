from __future__ import annotations
from typing import List

class EmbClient:
    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        return [[0.0] * 3 for _ in texts]
