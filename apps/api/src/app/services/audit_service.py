from __future__ import annotations
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import Request

from app.models.user import AuditLogs
from app.api.schemas.users import AuditAction


class AuditService:
    def __init__(self, session: Session):
        self.session = session

    def log_action(
        self,
        action: str,
        actor_user_id: Optional[str] = None,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """Log an audit action."""
        audit_log = AuditLogs(
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            meta=meta,
            request_id=request_id,
        )
        
        if request:
            # Extract IP and User-Agent from request
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                audit_log.ip = forwarded_for.split(",")[0].strip()
            else:
                audit_log.ip = request.client.host if request.client else None
            
            audit_log.user_agent = request.headers.get("User-Agent")
        
        self.session.add(audit_log)
        self.session.commit()

    def log_user_action(
        self,
        action: AuditAction,
        target_user_id: str,
        actor_user_id: Optional[str] = None,
        request: Optional[Request] = None,
        request_id: Optional[str] = None,
        **meta
    ) -> None:
        """Log a user-related action."""
        self.log_action(
            action=action.value,
            actor_user_id=actor_user_id,
            object_type="user",
            object_id=target_user_id,
            meta=meta,
            request=request,
            request_id=request_id,
        )

    def log_token_action(
        self,
        action: AuditAction,
        token_id: str,
        user_id: str,
        actor_user_id: Optional[str] = None,
        request: Optional[Request] = None,
        request_id: Optional[str] = None,
        **meta
    ) -> None:
        """Log a token-related action."""
        self.log_action(
            action=action.value,
            actor_user_id=actor_user_id,
            object_type="token",
            object_id=token_id,
            meta={"user_id": user_id, **meta},
            request=request,
            request_id=request_id,
        )

    def log_auth_action(
        self,
        action: AuditAction,
        user_id: str,
        request: Optional[Request] = None,
        request_id: Optional[str] = None,
        **meta
    ) -> None:
        """Log an authentication-related action."""
        self.log_action(
            action=action.value,
            actor_user_id=user_id,
            object_type="auth",
            object_id=user_id,
            meta=meta,
            request=request,
            request_id=request_id,
        )
