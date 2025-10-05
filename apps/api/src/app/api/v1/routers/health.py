"""
Health and status endpoints for the API
"""
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from api.deps import db_session
from core.config import get_settings
from core.db import health_check
import os
import subprocess
from datetime import datetime

router = APIRouter(tags=["health"])


@router.get("/healthz")
def health_check_endpoint():
    """Health check endpoint - basic liveness probe"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/readyz")
def readiness_check_endpoint(session: Session = Depends(db_session)):
    """Readiness check endpoint - checks if service is ready to serve traffic"""
    try:
        # Check database connectivity
        db_healthy = health_check()
        
        # Check other dependencies if needed
        dependencies = {
            "database": "ready" if db_healthy else "not_ready",
            "api": "ready"
        }
        
        if db_healthy:
            return {
                "status": "ready",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "dependencies": dependencies
            }
        else:
            return {
                "status": "not_ready",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "dependencies": dependencies
            }
    except Exception as e:
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
