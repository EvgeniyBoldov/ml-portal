from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.core.jwt_keys import load_jwks

router = APIRouter(prefix="", tags=["security"])

@router.get("/.well-known/jwks.json")
async def jwks():
    return JSONResponse(load_jwks())
