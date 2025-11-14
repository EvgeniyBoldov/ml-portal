"""
Idempotency service implementation
"""
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
import json
import hashlib
import uuid
from datetime import datetime, timezone, timedelta

from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.common import ProblemDetails
from app.core.exceptions import DuplicateError


class IdempotencyService:
    """Service for handling idempotency keys and cached responses"""
    
    def __init__(self, idempotency_repo: IdempotencyRepository):
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
    
    def check_or_store_response(
        self,
        tenant_id: uuid.UUID,
        user_id: Optional[uuid.UUID],
        key: str,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        response_status: int,
        response_body: Dict[str, Any],
        response_headers: Dict[str, str],
        ttl_seconds: int = 3600
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Check if request is idempotent or store new response
        
        Returns:
            Tuple[cached_response, is_new_request]
            - cached_response: None for new requests, dict for cached responses
            - is_new_request: True if this is a new request, False if cached
        """
        # Compute request hash
        req_hash = self._compute_request_hash(
            method, path, headers, body, tenant_id, user_id
        )
        
        # Calculate TTL
        ttl_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        
        try:
            # Try to create new idempotency key (atomic operation)
            idempotency_record = self.idempotency_repo.create_idempotency_key(
                tenant_id=tenant_id,
                user_id=user_id,
                key=key,
                req_hash=req_hash,
                response_status=response_status,
                response_body=response_body,
                response_headers=response_headers,
                ttl_at=ttl_at
            )
            
            # New request - return None to indicate processing needed
            return None, True
            
        except DuplicateError:
            # Request already exists - get cached response
            cached_record = self.idempotency_repo.get_by_key(tenant_id, user_id, key)
            
            if not cached_record:
                # Race condition - record was deleted between check and get
                # This is very rare, treat as new request
                return None, True
            
            # Check if TTL expired
            if cached_record.ttl_at < datetime.now(timezone.utc):
                # Expired - delete and treat as new request
                self.idempotency_repo.delete_by_key(tenant_id, user_id, key)
                return None, True
            
            # Return cached response
            cached_response = {
                'status': cached_record.response_status,
                'body': cached_record.response_body,
                'headers': cached_record.response_headers,
                'idempotent_replay': True
            }
            
            return cached_response, False
    
    def store_response(
        self,
        tenant_id: uuid.UUID,
        user_id: Optional[uuid.UUID],
        key: str,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        response_status: int,
        response_body: Dict[str, Any],
        response_headers: Dict[str, str],
        ttl_seconds: int = 3600
    ) -> None:
        """Store response for idempotency (called after successful processing)"""
        # Only store successful responses (2xx)
        if not (200 <= response_status < 300):
            return
        
        # Limit response size to prevent storage bloat
        response_size = len(json.dumps(response_body))
        if response_size > 256 * 1024:  # 256KB limit
            return
        
        # Compute request hash
        req_hash = self._compute_request_hash(
            method, path, headers, body, tenant_id, user_id
        )
        
        # Calculate TTL
        ttl_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        
        try:
            # Update existing record with response
            self.idempotency_repo.update_response(
                tenant_id=tenant_id,
                user_id=user_id,
                key=key,
                response_status=response_status,
                response_body=response_body,
                response_headers=response_headers,
                ttl_at=ttl_at
            )
        except Exception:
            # If update fails, try to create new record
            # This handles race conditions where record was deleted
            try:
                self.idempotency_repo.create_idempotency_key(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    key=key,
                    req_hash=req_hash,
                    response_status=response_status,
                    response_body=response_body,
                    response_headers=response_headers,
                    ttl_at=ttl_at
                )
            except DuplicateError:
                # Another request processed simultaneously - ignore
                pass
    
    def cleanup_expired_keys(self) -> int:
        """Clean up expired idempotency keys"""
        return self.idempotency_repo.cleanup_expired()