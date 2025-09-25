from __future__ import annotations
from typing import Iterable, Dict, Any, List

class LLMClient:
    def generate(self, messages: List[Dict[str, str]], model: str, **params) -> str:
        return ""

    def generate_stream(self, messages: List[Dict[str, str]], model: str, **params) -> Iterable[str]:
        yield from ()
