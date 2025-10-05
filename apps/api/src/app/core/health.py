from __future__ import annotations
import asyncio
import time
from typing import Dict, Any, Optional
from enum import Enum
import logging
from core.config import get_settings
from core.resilience import resilience_manager

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

class HealthCheck:
    """Individual health check"""
    
    def __init__(self, name: str, check_func: callable, timeout: float = 5.0):
        self.name = name
        self.check_func = check_func
        self.timeout = timeout
        self.last_check_time = 0
        self.last_status = HealthStatus.UNHEALTHY
        self.last_error: Optional[str] = None
    
    async def check(self) -> Dict[str, Any]:
        """Run health check"""
        try:
            # Run check with timeout
            result = await asyncio.wait_for(
                self.check_func(),
                timeout=self.timeout
            )
            
            self.last_check_time = time.time()
            self.last_status = HealthStatus.HEALTHY
            self.last_error = None
            
            return {
                "status": "healthy",
                "response_time_ms": result.get("response_time_ms", 0),
                "details": result.get("details", {})
            }
            
        except asyncio.TimeoutError:
            self.last_check_time = time.time()
            self.last_status = HealthStatus.UNHEALTHY
            self.last_error = "Timeout"
            
            return {
                "status": "unhealthy",
                "error": "Timeout",
                "response_time_ms": self.timeout * 1000
            }
            
        except Exception as e:
            self.last_check_time = time.time()
            self.last_status = HealthStatus.UNHEALTHY
            self.last_error = str(e)
            
            return {
                "status": "unhealthy",
                "error": str(e),
                "response_time_ms": 0
            }

class HealthChecker:
    """Health checker for all services"""
    
    def __init__(self):
        self.settings = get_settings()
        self.checks: Dict[str, HealthCheck] = {}
        self._setup_checks()
    
    def _setup_checks(self):
        """Setup health checks"""
        # Database check
        self.checks['database'] = HealthCheck(
            "database",
            self._check_database,
            timeout=5.0
        )
        
        # Redis check
        self.checks['redis'] = HealthCheck(
            "redis",
            self._check_redis,
            timeout=3.0
        )
        
        # LLM service check
        self.checks['llm'] = HealthCheck(
            "llm",
            self._check_llm_service,
            timeout=10.0
        )
        
        # Embedding service check
        self.checks['emb'] = HealthCheck(
            "emb",
            self._check_emb_service,
            timeout=10.0
        )
        
        # MinIO check
        self.checks['minio'] = HealthCheck(
            "minio",
            self._check_minio,
            timeout=5.0
        )
        
        # Qdrant check
        self.checks['qdrant'] = HealthCheck(
            "qdrant",
            self._check_qdrant,
            timeout=5.0
        )
    
    async def _check_database(self) -> Dict[str, Any]:
        """Check database connectivity"""
        start_time = time.time()
        
        try:
            from app.core.db import get_async_session
            async for session in get_async_session():
                # Simple query to test connection
                result = await session.execute("SELECT 1")
                result.scalar()
                break
            
            response_time = (time.time() - start_time) * 1000
            return {
                "response_time_ms": response_time,
                "details": {"connection": "ok"}
            }
            
        except Exception as e:
            raise Exception(f"Database check failed: {e}")
    
    async def _check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity"""
        start_time = time.time()
        
        try:
            import redis
            client = redis.from_url(self.settings.REDIS_URL)
            
            # Test ping
            client.ping()
            
            response_time = (time.time() - start_time) * 1000
            return {
                "response_time_ms": response_time,
                "details": {"ping": "ok"}
            }
            
        except Exception as e:
            raise Exception(f"Redis check failed: {e}")
    
    async def _check_llm_service(self) -> Dict[str, Any]:
        """Check LLM service"""
        start_time = time.time()
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.settings.LLM_BASE_URL}/health")
                response.raise_for_status()
            
            response_time = (time.time() - start_time) * 1000
            return {
                "response_time_ms": response_time,
                "details": {"status_code": response.status_code}
            }
            
        except Exception as e:
            raise Exception(f"LLM service check failed: {e}")
    
    async def _check_emb_service(self) -> Dict[str, Any]:
        """Check embedding service"""
        start_time = time.time()
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.settings.EMB_BASE_URL}/health")
                response.raise_for_status()
            
            response_time = (time.time() - start_time) * 1000
            return {
                "response_time_ms": response_time,
                "details": {"status_code": response.status_code}
            }
            
        except Exception as e:
            raise Exception(f"Embedding service check failed: {e}")
    
    async def _check_minio(self) -> Dict[str, Any]:
        """Check MinIO connectivity"""
        start_time = time.time()
        
        try:
            from minio import Minio
            client = Minio(
                self.settings.S3_ENDPOINT,
                access_key=self.settings.S3_ACCESS_KEY,
                secret_key=self.settings.S3_SECRET_KEY,
                secure=self.settings.S3_SECURE
            )
            
            # List buckets to test connection
            client.list_buckets()
            
            response_time = (time.time() - start_time) * 1000
            return {
                "response_time_ms": response_time,
                "details": {"connection": "ok"}
            }
            
        except Exception as e:
            raise Exception(f"MinIO check failed: {e}")
    
    async def _check_qdrant(self) -> Dict[str, Any]:
        """Check Qdrant connectivity"""
        start_time = time.time()
        
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(url=self.settings.QDRANT_URL)
            
            # Get collections to test connection
            client.get_collections()
            
            response_time = (time.time() - start_time) * 1000
            return {
                "response_time_ms": response_time,
                "details": {"connection": "ok"}
            }
            
        except Exception as e:
            raise Exception(f"Qdrant check failed: {e}")
    
    async def check_all(self) -> Dict[str, Any]:
        """Run all health checks"""
        results = {}
        overall_status = HealthStatus.HEALTHY
        
        for name, check in self.checks.items():
            result = await check.check()
            results[name] = result
            
            # Determine overall status
            if result["status"] == "unhealthy":
                overall_status = HealthStatus.UNHEALTHY
            elif result["status"] == "degraded" and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED
        
        return {
            "status": overall_status.value,
            "timestamp": time.time(),
            "checks": results
        }
    
    async def check_critical(self) -> Dict[str, Any]:
        """Check only critical services"""
        critical_checks = ['database', 'redis']
        results = {}
        overall_status = HealthStatus.HEALTHY
        
        for name in critical_checks:
            if name in self.checks:
                result = await self.checks[name].check()
                results[name] = result
                
                if result["status"] == "unhealthy":
                    overall_status = HealthStatus.UNHEALTHY
        
        return {
            "status": overall_status.value,
            "timestamp": time.time(),
            "checks": results
        }

# Global health checker
health_checker = HealthChecker()
