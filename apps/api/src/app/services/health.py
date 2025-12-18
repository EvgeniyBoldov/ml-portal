"""
Health service for business logic
"""
from __future__ import annotations
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.db import health_check
import os
import subprocess
from datetime import datetime


class HealthService:
    """Service for health check business logic"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def liveness(self) -> Dict[str, Any]:
        """Basic liveness check"""
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    async def readiness(self) -> Dict[str, Any]:
        """Readiness check with dependencies"""
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
    
    async def health(self) -> Dict[str, Any]:
        """Aggregated health check with detailed status"""
        try:
            # Get basic liveness status
            liveness = await self.liveness()
            
            # Get readiness status with dependencies
            readiness = await self.readiness()
            
            # Get version info
            version = await self.version()
            
            # Determine overall health status
            overall_status = "healthy"
            if readiness.get("status") != "ready":
                overall_status = "degraded"
            
            return {
                "status": overall_status,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "liveness": liveness,
                "readiness": readiness,
                "version": version,
                "uptime": "unknown",  # TODO: implement actual uptime tracking
                "checks": {
                    "database": readiness.get("dependencies", {}).get("database", "unknown"),
                    "api": readiness.get("dependencies", {}).get("api", "unknown")
                }
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "error": str(e)
            }
    
    async def version(self) -> Dict[str, Any]:
        """Version information"""
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
