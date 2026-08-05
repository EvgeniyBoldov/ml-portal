"""
HTTP clients for external services.
"""
from .clients import (
    LLMClientProtocol,
    EmbClientProtocol,
    HTTPEmbClient,
)

__all__ = [
    "LLMClientProtocol",
    "EmbClientProtocol",
    "HTTPEmbClient",
]
