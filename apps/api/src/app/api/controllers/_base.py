"""
Base API controller with common functionality
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, TypeVar, Generic, Union
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.logging import get_logger
from app.services._base import BaseService, AsyncBaseService

logger = get_logger(__name__)

T = TypeVar('T', bound=BaseModel)

class BaseController(ABC):
    """Base API controller with common functionality"""
    
    def __init__(self, service: BaseService):
        self.service = service
        self.logger = get_logger(self.__class__.__name__)
    
    def _generate_request_id(self) -> str:
        """Generate a new request ID"""
        return str(uuid.uuid4())
    
    def _get_current_time(self) -> datetime:
        """Get current UTC time"""
        return datetime.now(timezone.utc)
    
    def _create_success_response(self, data: Any, message: Optional[str] = None, 
                                request_id: Optional[str] = None) -> Any:
        """Create success response - return data directly (no envelope)"""
        # Return data directly as per contract - no envelope
        return data
    
    def _create_error_response(self, error_code: str, message: str, 
                              details: Optional[Dict[str, Any]] = None,
                              request_id: Optional[str] = None) -> Dict[str, Any]:
        """Create standardized error response"""
        response = {
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "details": details or {}
            },
            "timestamp": self._get_current_time().isoformat()
        }
        
        if request_id:
            response["request_id"] = request_id
        
        return response
    
    def _handle_controller_error(self, operation: str, error: Exception, 
                                request_id: Optional[str] = None) -> HTTPException:
        """Handle controller errors and convert to HTTP exceptions"""
        error_data = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "controller": self.__class__.__name__
        }
        
        if request_id:
            error_data["request_id"] = request_id
        
        self.logger.error(f"Controller error in {operation}: {error}", extra=error_data)
        
        # Map common errors to HTTP status codes - use Problem format
        if isinstance(error, ValueError):
            return HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error)  # Let middleware handle Problem format
            )
        elif isinstance(error, PermissionError):
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"  # Let middleware handle Problem format
            )
        elif isinstance(error, FileNotFoundError):
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"  # Let middleware handle Problem format
            )
        else:
            return HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"  # Let middleware handle Problem format
            )
    
    def _validate_pagination_params(self, limit: int, offset: int) -> None:
        """Validate pagination parameters"""
        if limit < 1 or limit > 1000:
            raise ValueError("Limit must be between 1 and 1000")
        if offset < 0:
            raise ValueError("Offset must be non-negative")
    
    def _validate_uuid_param(self, param_value: str, param_name: str) -> None:
        """Validate UUID parameter"""
        try:
            uuid.UUID(param_value)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid {param_name} format")
    
    def _extract_user_info(self, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Extract user information from current user"""
        return {
            "user_id": current_user.get("id"),
            "user_login": current_user.get("login"),
            "user_role": current_user.get("role")
        }
    
    def _log_api_operation(self, operation: str, user_info: Dict[str, Any], 
                          request_id: Optional[str] = None, 
                          details: Optional[Dict[str, Any]] = None) -> None:
        """Log API operation"""
        log_data = {
            "operation": operation,
            "controller": self.__class__.__name__,
            **user_info
        }
        
        if request_id:
            log_data["request_id"] = request_id
        
        if details:
            log_data.update(details)
        
        self.logger.info(f"API operation: {operation}", extra=log_data)


class AsyncBaseController(ABC):
    """Async base API controller"""
    
    def __init__(self, service: AsyncBaseService):
        self.service = service
        self.logger = get_logger(self.__class__.__name__)
    
    def _generate_request_id(self) -> str:
        """Generate a new request ID"""
        return str(uuid.uuid4())
    
    def _get_current_time(self) -> datetime:
        """Get current UTC time"""
        return datetime.now(timezone.utc)
    
    def _create_success_response(self, data: Any, message: Optional[str] = None, 
                                request_id: Optional[str] = None) -> Any:
        """Create success response - return data directly (no envelope)"""
        # Return data directly as per contract - no envelope
        return data
    
    def _create_error_response(self, error_code: str, message: str, 
                              details: Optional[Dict[str, Any]] = None,
                              request_id: Optional[str] = None) -> Dict[str, Any]:
        """Create standardized error response"""
        response = {
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "details": details or {}
            },
            "timestamp": self._get_current_time().isoformat()
        }
        
        if request_id:
            response["request_id"] = request_id
        
        return response
    
    def _handle_controller_error(self, operation: str, error: Exception, 
                                request_id: Optional[str] = None) -> HTTPException:
        """Handle controller errors and convert to HTTP exceptions"""
        error_data = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "controller": self.__class__.__name__
        }
        
        if request_id:
            error_data["request_id"] = request_id
        
        self.logger.error(f"Controller error in {operation}: {error}", extra=error_data)
        
        # Map common errors to HTTP status codes - use Problem format
        if isinstance(error, ValueError):
            return HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error)  # Let middleware handle Problem format
            )
        elif isinstance(error, PermissionError):
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"  # Let middleware handle Problem format
            )
        elif isinstance(error, FileNotFoundError):
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"  # Let middleware handle Problem format
            )
        else:
            return HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"  # Let middleware handle Problem format
            )
    
    def _validate_pagination_params(self, limit: int, offset: int) -> None:
        """Validate pagination parameters"""
        if limit < 1 or limit > 1000:
            raise ValueError("Limit must be between 1 and 1000")
        if offset < 0:
            raise ValueError("Offset must be non-negative")
    
    def _validate_uuid_param(self, param_value: str, param_name: str) -> None:
        """Validate UUID parameter"""
        try:
            uuid.UUID(param_value)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid {param_name} format")
    
    def _extract_user_info(self, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Extract user information from current user"""
        return {
            "user_id": current_user.get("id"),
            "user_login": current_user.get("login"),
            "user_role": current_user.get("role")
        }
    
    def _log_api_operation(self, operation: str, user_info: Dict[str, Any], 
                          request_id: Optional[str] = None, 
                          details: Optional[Dict[str, Any]] = None) -> None:
        """Log API operation"""
        log_data = {
            "operation": operation,
            "controller": self.__class__.__name__,
            **user_info
        }
        
        if request_id:
            log_data["request_id"] = request_id
        
        if details:
            log_data.update(details)
        
        self.logger.info(f"API operation: {operation}", extra=log_data)


class PaginatedResponse(BaseModel):
    """Paginated response model"""
    items: List[Any]
    total: int
    limit: int
    offset: int
    has_more: bool
    next_cursor: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = False
    error: Dict[str, Any]
    timestamp: str
    request_id: Optional[str] = None


class SuccessResponse(BaseModel):
    """Success response model"""
    success: bool = True
    data: Any
    message: Optional[str] = None
    timestamp: str
    request_id: Optional[str] = None
