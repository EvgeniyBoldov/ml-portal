"""
Simple job storage for analyze operations
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from enum import Enum
import json
from app.core.redis import get_sync_redis
from app.core.logging import get_logger

logger = get_logger(__name__)

class JobStatus(str, Enum):
    """Job status enumeration"""
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

class JobStorage:
    """Simple job storage using Redis"""
    
    def __init__(self):
        self.redis = get_sync_redis()
        self.ttl_seconds = 24 * 3600  # 24 hours
    
    def create_job(self, job_id: str, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new job"""
        job = {
            "id": job_id,
            "status": JobStatus.QUEUED.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "data": job_data
        }
        
        key = f"job:{job_id}"
        self.redis.setex(key, self.ttl_seconds, json.dumps(job))
        logger.info(f"Created job {job_id}")
        return job
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID"""
        key = f"job:{job_id}"
        data = self.redis.get(key)
        if not data:
            return None
        
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode job {job_id}")
            return None
    
    def update_job_status(self, job_id: str, status: JobStatus, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> bool:
        """Update job status"""
        job = self.get_job(job_id)
        if not job:
            return False
        
        job["status"] = status.value
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        if result:
            job["result"] = result
        
        if error:
            job["error"] = error
        
        key = f"job:{job_id}"
        self.redis.setex(key, self.ttl_seconds, json.dumps(job))
        logger.info(f"Updated job {job_id} to status {status.value}")
        return True
    
    def delete_job(self, job_id: str) -> bool:
        """Delete job"""
        key = f"job:{job_id}"
        result = self.redis.delete(key)
        logger.info(f"Deleted job {job_id}")
        return bool(result)
    
    def list_jobs(self, status: Optional[JobStatus] = None, limit: int = 100) -> list[Dict[str, Any]]:
        """List jobs with optional status filter"""
        pattern = "job:*"
        keys = self.redis.keys(pattern)
        
        jobs = []
        for key in keys:
            data = self.redis.get(key)
            if data:
                try:
                    job = json.loads(data)
                    if not status or job.get("status") == status.value:
                        jobs.append(job)
                except json.JSONDecodeError:
                    continue
        
        # Sort by created_at descending
        jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jobs[:limit]

# Global job storage instance
job_storage = JobStorage()
