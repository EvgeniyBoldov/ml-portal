"""Strict JSON envelopes for machine-to-machine agent invocation."""
from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ShadowAgentRequest(BaseModel):
    agent: str = Field(min_length=1)
    data: dict[str, JsonValue]
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ShadowAgentResponse(BaseModel):
    agent: str = Field(min_length=1)
    result: dict[str, JsonValue]
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
