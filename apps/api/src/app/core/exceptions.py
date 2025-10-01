"""
Core exceptions for the application
"""
from __future__ import annotations
from typing import Optional, Dict, Any


class DomainException(Exception):
    """Base class for domain-specific exceptions."""
    
    def __init__(self, message: str, code: str = "DOMAIN_ERROR", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details if details is not None else {}
        super().__init__(message)


class DuplicateError(DomainException):
    """Raised when trying to create a duplicate entity."""
    
    def __init__(self, entity_type: str, field: str, value: Any, details: Optional[Dict[str, Any]] = None):
        message = f"Duplicate {entity_type} with {field}={value}"
        super().__init__(message, "DUPLICATE_ERROR", details)
        self.entity_type = entity_type
        self.field = field
        self.value = value


class NotFoundError(DomainException):
    """Raised when an entity is not found."""
    
    def __init__(self, entity_type: str, identifier: Any, details: Optional[Dict[str, Any]] = None):
        message = f"{entity_type} with identifier {identifier} not found"
        super().__init__(message, "NOT_FOUND_ERROR", details)
        self.entity_type = entity_type
        self.identifier = identifier


class ValidationError(DomainException):
    """Raised when validation fails."""
    
    def __init__(self, field: str, value: Any, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Validation failed for {field}={value}: {reason}"
        super().__init__(message, "VALIDATION_ERROR", details)
        self.field = field
        self.value = value
        self.reason = reason


class TenantRequiredError(DomainException):
    """Raised when tenant_id is required but not provided."""
    
    def __init__(self, operation: str, details: Optional[Dict[str, Any]] = None):
        message = f"Tenant ID is required for operation: {operation}"
        super().__init__(message, "TENANT_REQUIRED_ERROR", details)
        self.operation = operation
