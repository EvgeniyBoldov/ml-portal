
"""
DEPRECATED: This module is kept for backwards import compatibility only.
Real authentication endpoints are now in routers/security.py under '/auth'.

This module does NOT define routes to avoid conflicts when 'security' 
is already mounted at '/auth' in the main router.

DO NOT USE THIS MODULE FOR NEW CODE.
"""
from fastapi import APIRouter

# Empty router for backwards compatibility
router = APIRouter()
