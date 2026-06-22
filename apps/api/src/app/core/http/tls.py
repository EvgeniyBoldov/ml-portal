from __future__ import annotations

from app.core.config import get_settings


def outbound_http_verify() -> bool | str:
    """
    Shared TLS verification policy for outbound HTTP integrations.

    Reuses the MCP HTTP settings so remote connectors can be relaxed by the
    same environment flag when working with self-signed/internal certificates.
    """
    settings = get_settings()
    ca_bundle = str(getattr(settings, "MCP_HTTP_CA_BUNDLE", "") or "").strip()
    if ca_bundle:
        return ca_bundle
    return bool(getattr(settings, "MCP_HTTP_VERIFY_SSL", True))
