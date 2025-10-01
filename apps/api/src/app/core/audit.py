"""
Centralized audit logging system
"""
from __future__ import annotations
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from app.core.logging import get_logger
from app.core.middleware import get_request_id

logger = get_logger(__name__)

class AuditAction(str, Enum):
    """Audit action types"""
    # Authentication
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    REFRESH_TOKEN = "REFRESH_TOKEN"
    REFRESH_TOKEN_FAILED = "REFRESH_TOKEN_FAILED"
    
    # Password management
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_SUCCESS = "PASSWORD_RESET_SUCCESS"
    PASSWORD_RESET_FAILED = "PASSWORD_RESET_FAILED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    
    # User management
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_DELETED = "USER_DELETED"
    ROLE_CHANGED = "ROLE_CHANGED"
    
    # File operations
    FILE_UPLOADED = "FILE_UPLOADED"
    FILE_DELETED = "FILE_DELETED"
    FILE_DOWNLOADED = "FILE_DOWNLOADED"
    
    # Admin operations
    ADMIN_ACTION = "ADMIN_ACTION"
    TENANT_CREATED = "TENANT_CREATED"
    TENANT_UPDATED = "TENANT_UPDATED"
    TENANT_DELETED = "TENANT_DELETED"
    
    # API operations
    API_ACCESS = "API_ACCESS"
    RATE_LIMIT_HIT = "RATE_LIMIT_HIT"

class AuditLogger:
    """Centralized audit logger"""
    
    @staticmethod
    def log(
        action: AuditAction,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Log audit event"""
        request_id = get_request_id()
        
        audit_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "action": action.value,
            "success": success,
            "user_id": user_id,
            "email": email,
            "tenant_id": tenant_id,
            "details": details or {},
            "error_message": error_message
        }
        
        # Log as structured JSON
        logger.info(
            "AUDIT_EVENT",
            extra={"audit": audit_data}
        )
    
    @staticmethod
    def log_auth_event(
        action: AuditAction,
        email: Optional[str] = None,
        user_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log authentication-related event"""
        AuditLogger.log(
            action=action,
            user_id=user_id,
            email=email,
            success=success,
            error_message=error_message,
            details=details
        )
    
    @staticmethod
    def log_file_event(
        action: AuditAction,
        file_name: str,
        file_size: Optional[int] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Log file-related event"""
        AuditLogger.log(
            action=action,
            user_id=user_id,
            tenant_id=tenant_id,
            success=success,
            error_message=error_message,
            details={
                "file_name": file_name,
                "file_size": file_size
            }
        )
    
    @staticmethod
    def log_admin_event(
        action: AuditAction,
        admin_user_id: str,
        target_user_id: Optional[str] = None,
        target_tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Log admin-related event"""
        AuditLogger.log(
            action=action,
            user_id=admin_user_id,
            tenant_id=target_tenant_id,
            success=success,
            error_message=error_message,
            details={
                "target_user_id": target_user_id,
                "target_tenant_id": target_tenant_id,
                **(details or {})
            }
        )

# Convenience functions
def log_login_success(email: str, user_id: str) -> None:
    """Log successful login"""
    AuditLogger.log_auth_event(
        action=AuditAction.LOGIN_SUCCESS,
        email=email,
        user_id=user_id,
        success=True
    )

def log_login_failed(email: str, error_message: str) -> None:
    """Log failed login attempt"""
    AuditLogger.log_auth_event(
        action=AuditAction.LOGIN_FAILED,
        email=email,
        success=False,
        error_message=error_message
    )

def log_password_reset_requested(email: str, user_id: str) -> None:
    """Log password reset request"""
    AuditLogger.log_auth_event(
        action=AuditAction.PASSWORD_RESET_REQUESTED,
        email=email,
        user_id=user_id,
        success=True
    )

def log_password_reset_failed(email: str, error_message: str) -> None:
    """Log failed password reset"""
    AuditLogger.log_auth_event(
        action=AuditAction.PASSWORD_RESET_FAILED,
        email=email,
        success=False,
        error_message=error_message
    )

def log_file_upload(file_name: str, file_size: int, user_id: str, tenant_id: str, success: bool = True, error_message: Optional[str] = None) -> None:
    """Log file upload event"""
    AuditLogger.log_file_event(
        action=AuditAction.FILE_UPLOADED,
        file_name=file_name,
        file_size=file_size,
        user_id=user_id,
        tenant_id=tenant_id,
        success=success,
        error_message=error_message
    )
