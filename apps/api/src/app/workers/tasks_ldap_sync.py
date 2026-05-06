"""
LDAP daily sync task.

Synchronizes user status with Active Directory:
- Deactivates users not found in AD
- Deactivates users disabled in AD (userAccountControl)
- Reactivates users that are now active
- Updates profile fields (email, full_name, ldap_groups)
"""
from __future__ import annotations

import time
from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import get_settings
from app.core.ldap_client import LDAPClient
from app.core.logging import get_logger
from app.services.ldap_user_service import LDAPUserService
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)

# In-memory metrics for LDAP monitoring (exposed via /metrics endpoint)
_ldap_metrics: dict[str, Any] = {
    "last_run_timestamp": 0,
    "last_success_timestamp": 0,
    "users_total": 0,
    "users_deactivated": 0,
    "errors_total": 0,
    "ldap_up": 0,
}


def get_ldap_metrics() -> dict[str, Any]:
    """Get current LDAP sync metrics (for health endpoint)."""
    return _ldap_metrics.copy()


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,  # 5 minutes
    time_limit=600,  # 10 minutes
    queue="maintenance.default",
)
def sync_ldap_users(self) -> dict[str, Any]:
    """
    Daily LDAP sync task.
    
    Runs through all LDAP users and syncs their status with AD.
    Scheduled via celery beat (AUTH_LDAP_SYNC_CRON, default 03:30 UTC).
    """
    settings = get_settings()
    
    if not settings.AUTH_LDAP_ENABLED:
        logger.debug("LDAP sync skipped: not enabled")
        return {"status": "skipped", "reason": "ldap_not_enabled"}
    
    if not settings.AUTH_LDAP_SYNC_ENABLED:
        logger.debug("LDAP sync skipped: sync disabled")
        return {"status": "skipped", "reason": "sync_disabled"}
    
    start_time = time.time()
    _ldap_metrics["last_run_timestamp"] = int(start_time)
    
    results = {
        "processed": 0,
        "deactivated_not_found": 0,
        "deactivated_disabled": 0,
        "reactivated": 0,
        "profile_updated": 0,
        "errors": 0,
        "skipped": 0,
    }
    
    try:
        async def _do_sync() -> None:
            async with get_worker_session() as session:
                ldap_client = LDAPClient(settings)
                ldap_service = LDAPUserService(session, settings)
                
                # Health check first
                health = await ldap_client.health_check()
                if not health.get("reachable"):
                    _ldap_metrics["ldap_up"] = 0
                    _ldap_metrics["errors_total"] += 1
                    raise Exception(f"LDAP not reachable: {health.get('error')}")
                
                _ldap_metrics["ldap_up"] = 1
                
                # Get all LDAP users
                from app.repositories.users_repo import AsyncUsersRepository
                users_repo = AsyncUsersRepository(session)
                ldap_users = await users_repo.list_by_auth_provider("ldap")
                
                _ldap_metrics["users_total"] = len(ldap_users)
                logger.info(f"Starting LDAP sync for {len(ldap_users)} users")
                
                deactivated_count = 0
                
                for user in ldap_users:
                    try:
                        sync_result = await ldap_service.sync_user_status(user)
                        results["processed"] += 1
                        
                        action = sync_result.get("action")
                        if action == "deactivated":
                            reason = sync_result.get("reason", "unknown")
                            if reason == "ldap_not_found":
                                results["deactivated_not_found"] += 1
                            elif reason == "ldap_disabled":
                                results["deactivated_disabled"] += 1
                            deactivated_count += 1
                        elif action == "reactivated":
                            results["reactivated"] += 1
                        elif action == "updated":
                            results["profile_updated"] += 1
                        elif action == "skipped":
                            results["skipped"] += 1
                            
                    except Exception as user_exc:
                        logger.warning(f"Failed to sync LDAP user {user.login}: {user_exc}")
                        results["errors"] += 1
                        _ldap_metrics["errors_total"] += 1
                
                _ldap_metrics["users_deactivated"] = deactivated_count
                
                # Commit all changes
                await session.commit()
        
        # Run async code in sync celery task
        import asyncio
        asyncio.run(_do_sync())
        
        _ldap_metrics["last_success_timestamp"] = int(time.time())
        
        duration = time.time() - start_time
        logger.info(
            f"LDAP sync completed in {duration:.1f}s: "
            f"processed={results['processed']}, "
            f"deactivated={results['deactivated_not_found'] + results['deactivated_disabled']}, "
            f"reactivated={results['reactivated']}, "
            f"errors={results['errors']}"
        )
        
        return {
            "status": "success",
            "duration_seconds": duration,
            **results,
        }
        
    except SoftTimeLimitExceeded:
        logger.error("LDAP sync hit soft time limit")
        _ldap_metrics["errors_total"] += 1
        raise
        
    except Exception as exc:
        logger.error(f"LDAP sync failed: {exc}")
        _ldap_metrics["errors_total"] += 1
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying LDAP sync (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=exc)
        
        return {
            "status": "error",
            "error": str(exc),
            **results,
        }


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=30,
    queue="health",
)
def ldap_health_check(self) -> dict[str, Any]:
    """
    Quick LDAP health check task (runs frequently, updates metrics).
    """
    settings = get_settings()
    
    if not settings.AUTH_LDAP_ENABLED:
        _ldap_metrics["ldap_up"] = 0
        return {"status": "disabled", "reachable": False}
    
    try:
        async def _do_check() -> dict[str, Any]:
            ldap_client = LDAPClient(settings)
            return await ldap_client.health_check()
        
        import asyncio
        health = asyncio.run(_do_check())
        
        is_up = health.get("reachable", False) and health.get("status") == "healthy"
        _ldap_metrics["ldap_up"] = 1 if is_up else 0
        
        if not is_up:
            logger.warning(f"LDAP health check failed: {health.get('error')}")
        
        return health
        
    except Exception as exc:
        _ldap_metrics["ldap_up"] = 0
        logger.warning(f"LDAP health check error: {exc}")
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        
        return {"status": "error", "reachable": False, "error": str(exc)}
