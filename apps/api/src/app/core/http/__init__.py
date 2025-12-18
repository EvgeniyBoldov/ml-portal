"""
HTTP clients for external services.
"""
from .clients import (
    LLMClientProtocol,
    EmbClientProtocol,
    HTTPLLMClient,
    HTTPEmbClient,
)

__all__ = [
    "LLMClientProtocol",
    "EmbClientProtocol",
    "HTTPLLMClient",
    "HTTPEmbClient",
]
