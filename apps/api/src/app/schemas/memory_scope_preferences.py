"""Explicit memory focus preferences; these never grant access permissions."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MemoryScopeKey = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=180)]
MemoryScopeKeys = Annotated[list[MemoryScopeKey], Field(max_length=60)]


class MemoryScopePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_scope_keys: MemoryScopeKeys = Field(default_factory=list)
