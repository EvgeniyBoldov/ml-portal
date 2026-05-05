"""Base contracts for health monitoring system."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from app.core.logging import get_logger

logger = get_logger(__name__)


class HealthStatus(str, Enum):
    """Health status of a system component."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthProbeResult:
    """Result of a health check probe."""
    status: HealthStatus
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    
    def is_healthy(self) -> bool:
        """Check if the result indicates healthy status."""
        return self.status == HealthStatus.HEALTHY


@runtime_checkable
class HealthCheckAdapter(Protocol):
    """Protocol for health check adapters."""
    
    async def probe(self, target: Any) -> HealthProbeResult:
        """Perform health check on the target.
        
        Args:
            target: The entity to check (ToolInstance, Model, etc.)
            
        Returns:
            HealthProbeResult with status and optional details.
        """
        ...


@dataclass
class BackoffPolicy:
    """Backoff policy for health checks."""
    base_interval: timedelta
    max_interval: timedelta
    failure_threshold: int  # Number of failures before switching to backoff
    
    def compute_next_check(
        self, 
        status: HealthStatus, 
        consecutive_failures: int,
        last_check: datetime
    ) -> datetime:
        """Compute next check timestamp based on status and failure count."""
        if status == HealthStatus.HEALTHY:
            # Reset to base interval when healthy
            return last_check + self.base_interval
        
        if consecutive_failures < self.failure_threshold:
            # Still in fast-check phase
            return last_check + self.base_interval
        
        # Apply exponential backoff
        backoff_factor = min(2 ** (consecutive_failures - self.failure_threshold), 10)
        backoff_interval = self.base_interval * backoff_factor
        capped_interval = min(backoff_interval, self.max_interval)
        
        return last_check + capped_interval


# Default backoff policies for different check intervals
BACKOFF_POLICY_1M = BackoffPolicy(
    base_interval=timedelta(minutes=1),
    max_interval=timedelta(minutes=5),
    failure_threshold=10,  # First 10 failures every 1m, then backoff
)

BACKOFF_POLICY_10M = BackoffPolicy(
    base_interval=timedelta(minutes=10),
    max_interval=timedelta(minutes=30),
    failure_threshold=3,  # First 3 failures every 10m, then backoff
)


def add_jitter(next_check: datetime, jitter_percent: float = 0.25) -> datetime:
    """Add random jitter to prevent thundering herd.
    
    Args:
        next_check: Base next check timestamp
        jitter_percent: Percentage of interval to jitter (0.0 to 1.0)
        
    Returns:
        Timestamp with jitter applied
    """
    import random
    
    jitter_range = (next_check - next_check.replace(second=0, microsecond=0)) * jitter_percent
    jitter_seconds = random.uniform(-jitter_range.total_seconds(), jitter_range.total_seconds())
    
    return next_check + timedelta(seconds=jitter_seconds)


class HealthCheckTarget:
    """Base class for health check targets."""
    
    def __init__(
        self,
        id: str,
        type: str,
        is_active: bool,
        consecutive_failures: int = 0,
        next_check_at: Optional[datetime] = None,
        last_error: Optional[str] = None,
    ):
        self.id = id
        self.type = type
        self.is_active = is_active
        self.consecutive_failures = consecutive_failures
        self.next_check_at = next_check_at
        self.last_error = last_error
    
    def should_check(self, now: datetime) -> bool:
        """Check if this target is due for health check."""
        if not self.is_active:
            return False
        
        if self.next_check_at is None:
            return True  # Never checked before
        
        return now >= self.next_check_at
    
    def __repr__(self) -> str:
        return f"<HealthCheckTarget {self.type}:{self.id} status={'active' if self.is_active else 'inactive'}>"
