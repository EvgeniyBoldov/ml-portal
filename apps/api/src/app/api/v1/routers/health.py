"""
Health and status endpoints for the API
"""
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.core.config import get_settings
from app.core.db import health_check as db_health_check
from app.adapters.s3_client import get_s3_client
from app.adapters.qdrant_client import get_qdrant_adapter
from app.core.cache import get_cache
import os
import subprocess
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz")
def health_check_endpoint():
    """Health check endpoint - basic liveness probe"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/readyz")
async def readiness_check_endpoint(session: AsyncSession = Depends(get_db)):
    """Readiness check endpoint - checks if service is ready to serve traffic"""
    try:
        dependencies = {}
        
        # Check database connectivity
        try:
            db_healthy = await db_health_check()
            dependencies["database"] = "ready" if db_healthy else "not_ready"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            dependencies["database"] = "not_ready"
        
        # Check Redis connectivity
        try:
            cache = await get_cache()
            dependencies["redis"] = "ready"
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            dependencies["redis"] = "not_ready"
        
        # Check S3/MinIO connectivity
        try:
            s3_client = get_s3_client()
            s3_healthy = await s3_client.health_check()
            dependencies["s3"] = "ready" if s3_healthy else "not_ready"
        except Exception as e:
            logger.error(f"S3 health check failed: {e}")
            dependencies["s3"] = "not_ready"
        
        # Check Qdrant connectivity
        try:
            qdrant_adapter = await get_qdrant_adapter()
            qdrant_healthy = await qdrant_adapter.health_check()
            dependencies["qdrant"] = "ready" if qdrant_healthy else "not_ready"
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            dependencies["qdrant"] = "not_ready"
        
        # Overall status
        all_ready = all(status == "ready" for status in dependencies.values())
        
        return {
            "status": "ready" if all_ready else "not_ready",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "dependencies": dependencies
        }
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error": str(e)
        }


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
    except:
        pass
    
    # Try to get build time from environment
    build_time = os.getenv("BUILD_TIME", "unknown")
    
    return {
        "version": getattr(settings, "VERSION", "1.0.0"),
        "build_time": build_time,
        "git_commit": git_commit,
        "environment": getattr(settings, "ENV", "development")
    }
