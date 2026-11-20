from __future__ import annotations

from dataclasses import dataclass



@dataclass
class CollectionGraphInfo:
    id: str
    slug: str
    name: str
    collection_type: str

