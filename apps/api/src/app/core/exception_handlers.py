from __future__ import annotations
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from app.schemas.common import ProblemDetails

PROBLEM_CT = "application/problem+json"

def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        payload = ProblemDetails(
            title=exc.detail if isinstance(exc.detail, str) else "HTTP Error",
            status=exc.status_code,
            instance=str(request.url),
        ).model_dump()
        return JSONResponse(status_code=exc.status_code, content=payload, media_type=PROBLEM_CT)

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(request: Request, exc: Exception):
        payload = ProblemDetails(
            title="Internal Server Error",
            status=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
            instance=str(request.url),
        ).model_dump()
        return JSONResponse(status_code=HTTP_500_INTERNAL_SERVER_ERROR, content=payload, media_type=PROBLEM_CT)
