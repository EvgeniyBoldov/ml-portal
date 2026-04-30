"""
Health and status endpoints for the API
"""
from __future__ import annotations
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session
from app.core.config import get_settings
from app.core.db import (
    get_pool_stats,
    health_check as db_health_check,
    is_startup_ready,
)
from app.adapters.s3_client import get_s3_client
from app.adapters.qdrant_client import get_qdrant_adapter
from app.core.cache import get_cache
import os
import subprocess
from datetime import datetime, timezone
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz")
def health_check_endpoint():
    """Health check endpoint - basic liveness probe"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/readyz")
async def readiness_check_endpoint(session: AsyncSession = Depends(db_session)):
    """Readiness check endpoint - checks infra and app-level dependencies.
    
    Returns 200 if all critical infra dependencies are ready.
    Returns 503 if any critical dependency is not ready.
    App-level checks are informational (degraded but not blocking).
    """
    now = datetime.now(timezone.utc).isoformat()
    
    try:
        infra = {}
        app_services = {}
        startup_ready = is_startup_ready()
        
        # ── Infra checks (critical — block readiness) ────────────
        
        # Database
        try:
            db_healthy = await db_health_check()
            infra["database"] = "ready" if db_healthy else "not_ready"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            infra["database"] = "not_ready"
        
        # Redis
        try:
            cache = await get_cache()
            infra["redis"] = "ready"
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            infra["redis"] = "not_ready"
        
        # S3/MinIO
        try:
            s3_client = get_s3_client()
            s3_healthy = await s3_client.health_check()
            infra["s3"] = "ready" if s3_healthy else "not_ready"
        except Exception as e:
            logger.error(f"S3 health check failed: {e}")
            infra["s3"] = "not_ready"
        
        # Qdrant
        try:
            qdrant_adapter = await get_qdrant_adapter()
            qdrant_healthy = await qdrant_adapter.health_check()
            infra["qdrant"] = "ready" if qdrant_healthy else "not_ready"
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            infra["qdrant"] = "not_ready"
        
        # ── App-level checks (informational — degraded mode) ─────
        
        # LLM service
        try:
            from app.core.di import get_llm_client
            llm = get_llm_client()
            # Simple list-models or chat probe with short timeout
            test_resp = await llm.chat(
                messages=[{"role": "user", "content": "ping"}],
                model=None,
                stream=False,
                max_tokens=1,
                temperature=0,
            )
            app_services["llm"] = "ready" if test_resp else "not_ready"
        except Exception as e:
            logger.warning(f"LLM health check failed: {e}")
            app_services["llm"] = "not_ready"
        
        # Embedding service
        try:
            from sqlalchemy import text
            from app.adapters.embeddings import EmbeddingServiceFactory

            result = await session.execute(
                text(
                    "SELECT alias FROM models "
                    "WHERE type = 'EMBEDDING' AND enabled = true AND status = 'AVAILABLE' "
                    "ORDER BY is_default DESC, alias ASC LIMIT 1"
                )
            )
            model_alias = result.scalar_one_or_none()
            if not model_alias:
                app_services["embedding"] = "not_ready"
            else:
                await EmbeddingServiceFactory.ensure_model_registered_async(session, model_alias)
                emb_service = EmbeddingServiceFactory.get_service(model_alias)
                test_emb = await asyncio.to_thread(emb_service.embed_texts, ["health check"])
                app_services["embedding"] = "ready" if test_emb else "not_ready"
        except Exception as e:
            logger.warning(f"Embedding health check failed: {e}")
            app_services["embedding"] = "not_ready"
        
        # Tool registry bootstrap
        try:
            from app.agents.registry import ToolRegistry
            tool_slugs = ToolRegistry.list_slugs()
            app_services["tool_registry"] = "ready" if tool_slugs else "not_ready"
        except Exception as e:
            logger.warning(f"Tool registry health check failed: {e}")
            app_services["tool_registry"] = "not_ready"
        
        # Agent runtime bootstrap — v3 RuntimePipeline readiness probe
        try:
            from app.core.di import get_llm_client
            llm = get_llm_client()
            app_services["agent_runtime"] = "ready" if llm is not None else "not_ready"
        except Exception as e:
            logger.warning(f"Agent runtime health check failed: {e}")
            app_services["agent_runtime"] = "not_ready"
        
        # Default agent resolution
        try:
            from app.services.agent_service import AgentService
            default_agent = await AgentService(session).get_default_agent_slug(None)
            app_services["default_agent"] = "ready" if default_agent else "not_ready"
        except Exception as e:
            logger.warning(f"Default agent health check failed: {e}")
            app_services["default_agent"] = "not_ready"
        
        # Celery worker
        try:
            from app.celery_app import app as celery_app
            loop = asyncio.get_event_loop()
            inspect_result = await loop.run_in_executor(
                None, lambda: celery_app.control.ping(timeout=2.0)
            )
            app_services["celery"] = "ready" if inspect_result else "not_ready"
        except Exception as e:
            logger.warning(f"Celery health check failed: {e}")
            app_services["celery"] = "not_ready"
        
        # ── Overall status ───────────────────────────────────────
        infra_ready = all(v == "ready" for v in infra.values())
        app_ready = all(v == "ready" for v in app_services.values())
        
        if infra_ready and app_ready:
            overall = "ready"
        elif infra_ready:
            overall = "degraded"
        else:
            overall = "not_ready"
        
        body = {
            "status": overall,
            "timestamp": now,
            "infra": infra,
            "startup_ready": startup_ready,
            "db_pool": get_pool_stats(),
            "app_services": app_services,
        }
        
        status_code = 200 if infra_ready else 503
        return JSONResponse(content=body, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            content={
                "status": "not_ready",
                "timestamp": now,
                "error": str(e),
            },
            status_code=503,
        )


@router.get("/version")
def version_endpoint():
    """Version information endpoint"""
    settings = get_settings()
    
    # Try to get git commit hash
    git_commit = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], 
            capture_output=True, 
            text=True, 
            cwd="/app"
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()[:8]  # Short hash
    except Exception:
        pass
    
    # Try to get build time from environment
    build_time = os.getenv("BUILD_TIME", "unknown")
    
    return {
        "version": getattr(settings, "VERSION", "1.0.0"),
        "build_time": build_time,
        "git_commit": git_commit,
        "environment": getattr(settings, "ENV", "development")
    }
