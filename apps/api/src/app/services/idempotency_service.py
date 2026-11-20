"""
Idempotency service implementation
"""
from __future__ import annotations
from typing import Dict, Any, Optional
import json
import hashlib
import uuid

from app.repositories.idempotency_repo import AsyncIdempotencyRepository


class IdempotencyService:
    """Service for handling idempotency keys and cached responses"""
    
    def __init__(self, idempotency_repo: AsyncIdempotencyRepository):
        self.idempotency_repo = idempotency_repo
    
    def _compute_request_hash(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        tenant_id: uuid.UUID,
        user_id: Optional[uuid.UUID]
    ) -> str:
        """Compute hash for request to detect duplicates"""
        # Normalize headers (exclude non-idempotent headers)
        normalized_headers = {
            k.lower(): v for k, v in headers.items()
            if k.lower() not in ['authorization', 'x-request-id', 'user-agent']
        }
        
        # Create hashable content
        content = {
            'method': method.upper(),
            'path': path,
            'headers': normalized_headers,
            'body': body,
            'tenant_id': str(tenant_id),
            'user_id': str(user_id) if user_id else None
        }
        
        # Compute hash
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()
    
