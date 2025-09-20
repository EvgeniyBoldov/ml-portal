from typing import Any, Dict, Optional, Union
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uuid

class APIError(BaseModel):
    code: str
    message: str
    details: Optional[Union[Dict[str, Any], list, str]] = None
    request_id: Optional[str] = None
    http_status: Optional[int] = None
    
    def __str__(self) -> str:
        return self.message

class ErrorResponse(BaseModel):
    error: APIError
    request_id: Optional[str] = None
    timestamp: Optional[str] = None

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Union[Dict[str, Any], list, str]] = None

def create_error_response(
    message: str,
    code: str = "internal_error",
    *,
    status_code: int = 400,
    details: Optional[Union[Dict[str, Any], list, str]] = None,
    request_id: Optional[str] = None,
) -> ErrorResponse:
    from datetime import datetime
    return ErrorResponse(
        error=APIError(code=code, message=message, details=details, request_id=request_id),
        request_id=request_id,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )

def raise_bad_request(message: str, details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None, code: str = "bad_request") -> None:
    error_data = {
        "error": APIError(code=code, message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=400, detail=error_data)

def raise_unauthorized(message: str = "Unauthorized", details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    error_data = {
        "error": APIError(code="unauthorized", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=401, detail=error_data)

def raise_forbidden(message: str = "Forbidden", details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    error_data = {
        "error": APIError(code="forbidden", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=403, detail=error_data)

def raise_not_found(message: str = "Not found", details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    from datetime import datetime
    error_data = {
        "error": APIError(code="not_found", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    raise HTTPException(status_code=404, detail=error_data)

def raise_conflict(message: str = "Conflict", details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    error_data = {
        "error": APIError(code="conflict", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=409, detail=error_data)

def raise_unprocessable_entity(message: str = "Unprocessable Entity", details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    error_data = {
        "error": APIError(code="unprocessable_entity", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=422, detail=error_data)

def raise_unprocessable(message: str = "Unprocessable entity", details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    error_data = {
        "error": APIError(code="unprocessable", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=422, detail=error_data)

def raise_server_error(message: str = "Internal Server Error", details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    error_data = {
        "error": APIError(code="server_error", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=500, detail=error_data)

def raise_http_error(status_code: int, message: str, details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    """Универсальная функция для создания HTTP ошибок"""
    error_data = {
        "error": APIError(code="http_error", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=status_code, detail=error_data)

def raise_validation_error(message: str, details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    """Функция для создания ошибок валидации"""
    error_data = {
        "error": APIError(code="validation_error", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=422, detail=error_data)

def raise_internal_error(message: str = "Internal Server Error", details: Optional[Union[Dict[str, Any], list, str]] = None, *, request_id: Optional[str] = None) -> None:
    """Функция для создания внутренних ошибок сервера"""
    error_data = {
        "error": APIError(code="internal_error", message=message, details=details, request_id=request_id).model_dump(),
        "request_id": request_id
    }
    raise HTTPException(status_code=500, detail=error_data)

def _get_request_id(request: Request) -> str:
    rid = request.headers.get("X-Request-ID")
    return rid or str(uuid.uuid4())

def install_exception_handlers(app) -> None:
    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            # Already in new format
            payload = detail
            if "request_id" not in payload.get("error", {}):
                payload["error"]["request_id"] = _get_request_id(request)
        else:
            # Convert to format expected by tests: {"detail": {"code": ..., "message": ...}}
            payload = {
                "detail": {
                    "code": "http_error",
                    "message": str(detail),
                    "request_id": _get_request_id(request)
                }
            }
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def generic_exc_handler(request: Request, exc: Exception):
        error_response = ErrorResponse(
            error=APIError(
                code="server_error",
                message="Internal Server Error",
                details={"type": type(exc).__name__},
                request_id=_get_request_id(request)
            )
        )
        return JSONResponse(status_code=500, content=error_response.model_dump())
