from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class HealthCheckResult:
    """Result of health check."""

    status: str  # "healthy" | "unhealthy" | "unknown"
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class RescanResult:
    """Result of local instance rescan."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
    errors: int = 0
