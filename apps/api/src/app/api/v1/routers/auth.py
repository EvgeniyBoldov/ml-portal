
"""Deprecated shim: real endpoints live in routers/security.py under '/auth'.
This module keeps a router object for backwards import compatibility, but does NOT define routes
to avoid conflicts when 'security' is already mounted at '/auth'.
"""
from fastapi import APIRouter
router = APIRouter()
