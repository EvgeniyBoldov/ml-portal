"""
PAT (Personal Access Token) scope validation
"""
from __future__ import annotations
from typing import List, Set, Optional
from fastapi import HTTPException, status

# Valid scope patterns
VALID_SCOPE_PATTERNS = {
    "api:read",      # Read API access
    "api:write",     # Write API access
    "api:admin",     # Admin API access
    "rag:read",      # Read RAG documents
    "rag:write",     # Write RAG documents
    "rag:admin",     # Admin RAG operations
    "chat:read",     # Read chat history
    "chat:write",    # Send messages
    "chat:admin",    # Admin chat operations
    "users:read",    # Read user data
    "users:write",   # Write user data
    "users:admin",   # Admin user operations
}

# Scope hierarchy (higher scopes include lower ones)
SCOPE_HIERARCHY = {
    "api:admin": ["api:read", "api:write"],
    "api:write": ["api:read"],
    "rag:admin": ["rag:read", "rag:write"],
    "rag:write": ["rag:read"],
    "chat:admin": ["chat:read", "chat:write"],
    "chat:write": ["chat:read"],
    "users:admin": ["users:read", "users:write"],
    "users:write": ["users:read"],
}

def validate_scopes(scopes: Optional[List[str]]) -> List[str]:
    """
    Validate and normalize PAT scopes
    
    Args:
        scopes: List of scope strings
        
    Returns:
        Normalized list of valid scopes
        
    Raises:
        HTTPException: If scopes are invalid
    """
    if not scopes:
        return []
    
    if not isinstance(scopes, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scopes must be a list"
        )
    
    # Check for invalid scopes
    invalid_scopes = []
    for scope in scopes:
        if not isinstance(scope, str):
            invalid_scopes.append(str(scope))
        elif scope not in VALID_SCOPE_PATTERNS:
            invalid_scopes.append(scope)
    
    if invalid_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scopes: {', '.join(invalid_scopes)}. Valid scopes: {', '.join(sorted(VALID_SCOPE_PATTERNS))}"
        )
    
    # Expand hierarchical scopes
    expanded_scopes = set(scopes)
    for scope in scopes:
        if scope in SCOPE_HIERARCHY:
            expanded_scopes.update(SCOPE_HIERARCHY[scope])
    
    return sorted(list(expanded_scopes))

def check_scope_permission(user_scopes: List[str], required_scope: str) -> bool:
    """
    Check if user has permission for required scope
    
    Args:
        user_scopes: List of user's scopes
        required_scope: Required scope to check
        
    Returns:
        True if user has permission
    """
    if not user_scopes:
        return False
    
    # Direct scope match
    if required_scope in user_scopes:
        return True
    
    # Check if user has a higher-level scope that includes this one
    for user_scope in user_scopes:
        if user_scope in SCOPE_HIERARCHY and required_scope in SCOPE_HIERARCHY[user_scope]:
            return True
    
    return False

def get_scope_description(scope: str) -> str:
    """Get human-readable description for a scope"""
    descriptions = {
        "api:read": "Read API access",
        "api:write": "Write API access", 
        "api:admin": "Admin API access",
        "rag:read": "Read RAG documents",
        "rag:write": "Write RAG documents",
        "rag:admin": "Admin RAG operations",
        "chat:read": "Read chat history",
        "chat:write": "Send messages",
        "chat:admin": "Admin chat operations",
        "users:read": "Read user data",
        "users:write": "Write user data",
        "users:admin": "Admin user operations",
    }
    return descriptions.get(scope, scope)

def format_scopes_for_display(scopes: List[str]) -> List[dict]:
    """Format scopes for API response with descriptions"""
    return [
        {
            "scope": scope,
            "description": get_scope_description(scope)
        }
        for scope in sorted(scopes)
    ]
