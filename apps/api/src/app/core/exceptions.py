"""
core/exceptions.py — единый каталог domain exceptions.

Каждый exception несёт http_status, чтобы error handler мог автоматически
маппить domain errors → HTTP responses без ручных except-блоков в каждом роутере.

Иерархия:
    AppError                     — base для всех domain exceptions
    ├── NotFoundError            — 404
    ├── AlreadyExistsError       — 409
    ├── ValidationError          — 400
    ├── ForbiddenError           — 403
    ├── UnauthorizedError        — 401
    ├── ConflictError            — 409
    ├── NotEditableError         — 409  (entity in non-editable state)
    ├── ProtectedError           — 409  (entity is protected / pinned)
    ├── InUseError               — 409  (entity is referenced by another)
    ├── UnavailableError         — 503  (dependency unavailable)
    ├── ExternalServiceError     — 502  (upstream call failed)
    │   └── CircuitBreakerOpen   — 503
    ├── UploadValidationError    — 422  (file intake policy)
    └── RuntimeError             — 500  (agent/planner runtime failure)

Usage in services:
    from app.core.exceptions import NotFoundError
    raise NotFoundError("Agent", agent_id)

Usage in routers — ничего не нужно: exception handler ловит AppError автоматически.
"""
from __future__ import annotations

from typing import Any, Optional
from typing import Dict

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from .middleware import get_request_id
from .logging import get_logger


# ──────────────────────────────────────────────────────────────────────────────
# BASE
# ──────────────────────────────────────────────────────────────────────────────

class AppError(Exception):
    """Base class for all domain exceptions.

    Subclasses MUST define ``http_status`` at class level.
    They MAY override ``code`` for a machine-readable error identifier.
    """

    http_status: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}


# ──────────────────────────────────────────────────────────────────────────────
# 4xx — CLIENT ERRORS
# ──────────────────────────────────────────────────────────────────────────────

class NotFoundError(AppError):
    """Entity does not exist — HTTP 404."""

    http_status = 404
    code = "NOT_FOUND"

    def __init__(self, entity: str = "Resource", entity_id: Any = None) -> None:
        msg = f"{entity} not found"
        if entity_id is not None:
            msg = f"{entity} '{entity_id}' not found"
        super().__init__(msg)


class AlreadyExistsError(AppError):
    """Entity with given identifier already exists — HTTP 409."""

    http_status = 409
    code = "ALREADY_EXISTS"

    def __init__(self, entity: str = "Resource", identifier: Any = None) -> None:
        msg = f"{entity} already exists"
        if identifier is not None:
            msg = f"{entity} '{identifier}' already exists"
        super().__init__(msg)


class ValidationError(AppError):
    """Invalid input / business rule violation — HTTP 400."""

    http_status = 400
    code = "VALIDATION_ERROR"


class ForbiddenError(AppError):
    """Caller lacks permission — HTTP 403."""

    http_status = 403
    code = "FORBIDDEN"


class UnauthorizedError(AppError):
    """Missing or invalid credentials — HTTP 401."""

    http_status = 401
    code = "UNAUTHORIZED"


class ConflictError(AppError):
    """State conflict (e.g. idempotency replay) — HTTP 409."""

    http_status = 409
    code = "CONFLICT"


class NotEditableError(AppError):
    """Entity is not in an editable state (e.g. published/archived) — HTTP 409."""

    http_status = 409
    code = "NOT_EDITABLE"

    def __init__(self, entity: str = "Resource", state: str = "") -> None:
        suffix = f" (current state: {state})" if state else ""
        super().__init__(f"{entity} is not editable{suffix}")


class ProtectedError(AppError):
    """Entity is protected / pinned and cannot be modified or deleted — HTTP 409."""

    http_status = 409
    code = "PROTECTED"


class InUseError(AppError):
    """Entity is referenced by another entity and cannot be removed — HTTP 409."""

    http_status = 409
    code = "IN_USE"


# ──────────────────────────────────────────────────────────────────────────────
# 422 — UNPROCESSABLE
# ──────────────────────────────────────────────────────────────────────────────

class UploadValidationError(AppError):
    """Uploaded file does not satisfy intake policy — HTTP 422."""

    http_status = 422
    code = "UPLOAD_INVALID"


# ──────────────────────────────────────────────────────────────────────────────
# 5xx — SERVER / UPSTREAM ERRORS
# ──────────────────────────────────────────────────────────────────────────────

class ExternalServiceError(AppError):
    """Upstream service call failed — HTTP 502."""

    http_status = 502
    code = "EXTERNAL_SERVICE_ERROR"


class CircuitBreakerOpen(ExternalServiceError):
    """Circuit breaker is open — service temporarily unavailable — HTTP 503."""

    http_status = 503
    code = "CIRCUIT_BREAKER_OPEN"


class UnavailableError(AppError):
    """Required dependency is unavailable — HTTP 503."""

    http_status = 503
    code = "SERVICE_UNAVAILABLE"


class AgentRuntimeError(AppError):
    """Agent / planner runtime failure — HTTP 500."""

    http_status = 500
    code = "RUNTIME_ERROR"


class SystemLLMExecutorError(AgentRuntimeError):
    """System LLM executor failure."""
    code = "LLM_EXECUTOR_ERROR"


class StatusTransitionError(ConflictError):
    """Invalid state machine transition."""
    code = "INVALID_STATUS_TRANSITION"


class CryptoError(AppError):
    """Cryptographic operation failure."""
    http_status = 500
    code = "CRYPTO_ERROR"


# ──────────────────────────────────────────────────────────────────────────────
# DOMAIN ALIASES
# Typed subclasses so services can raise semantically named errors while
# routers / handlers never need to inspect individual service modules.
# ──────────────────────────────────────────────────────────────────────────────

# — Agents ────────────────────────────────────────────────────────────────────

class AgentNotFoundError(NotFoundError):
    def __init__(self, agent_id: Any = None) -> None:
        super().__init__("Agent", agent_id)


class AgentAlreadyExistsError(AlreadyExistsError):
    def __init__(self, slug: Any = None) -> None:
        super().__init__("Agent", slug)


class AgentVersionNotFoundError(NotFoundError):
    def __init__(self, version: Any = None) -> None:
        super().__init__("AgentVersion", version)


class AgentVersionNotEditableError(NotEditableError):
    def __init__(self, state: str = "") -> None:
        super().__init__("AgentVersion", state)


class AgentUnavailableError(UnavailableError):
    """Agent cannot be executed due to missing requirements."""

    code = "AGENT_UNAVAILABLE"

    def __init__(
        self,
        message: str,
        missing: Any = None,
        *,
        reason_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.missing = missing
        self.reason_code = reason_code
        self.details = details or {}


# — Tools ─────────────────────────────────────────────────────────────────────

class ToolNotFoundError(NotFoundError):
    def __init__(self, tool_id: Any = None) -> None:
        super().__init__("Tool", tool_id)


class ReleaseNotFoundError(NotFoundError):
    def __init__(self, release_id: Any = None) -> None:
        super().__init__("ToolRelease", release_id)


class BackendReleaseNotFoundError(NotFoundError):
    def __init__(self, release_id: Any = None) -> None:
        super().__init__("BackendRelease", release_id)


class ReleaseNotEditableError(NotEditableError):
    def __init__(self, state: str = "") -> None:
        super().__init__("ToolRelease", state)


class ReleasePinnedError(ProtectedError):
    def __init__(self, release_id: Any = None) -> None:
        super().__init__(
            f"ToolRelease '{release_id}' is pinned in agent bindings and cannot be archived"
            if release_id else "ToolRelease is pinned and cannot be archived"
        )


# — Tool Instances ─────────────────────────────────────────────────────────────

class ToolInstanceNotFoundError(NotFoundError):
    def __init__(self, instance_id: Any = None) -> None:
        super().__init__("ToolInstance", instance_id)


class LocalInstanceProtectedError(ProtectedError):
    """Local instances cannot be manually created or deleted."""


class InstanceInUseError(InUseError):
    """Instance is referenced and cannot be deleted."""


# — Collections ───────────────────────────────────────────────────────────────

class CollectionNotFoundError(NotFoundError):
    def __init__(self, collection_id: Any = None) -> None:
        super().__init__("Collection", collection_id)


class CollectionAlreadyExistsError(AlreadyExistsError):
    def __init__(self, slug: Any = None) -> None:
        super().__init__("Collection", slug)


class InvalidSchemaError(ValidationError):
    """Invalid collection schema definition."""


class RowValidationError(ValidationError):
    """Invalid row payload for collection schema."""


# — Credentials ───────────────────────────────────────────────────────────────

class CredentialNotFoundError(NotFoundError):
    def __init__(self, cred_id: Any = None) -> None:
        super().__init__("Credential", cred_id)


# — RBAC ──────────────────────────────────────────────────────────────────────

class RbacRuleNotFoundError(NotFoundError):
    def __init__(self, rule_id: Any = None) -> None:
        super().__init__("RbacRule", rule_id)


class RbacRuleDuplicateError(AlreadyExistsError):
    def __init__(self, identifier: Any = None) -> None:
        super().__init__("RbacRule", identifier)


# — Limits ────────────────────────────────────────────────────────────────────

class LimitNotFoundError(NotFoundError):
    def __init__(self, limit_id: Any = None) -> None:
        super().__init__("Limit", limit_id)


class LimitVersionNotFoundError(NotFoundError):
    def __init__(self, version: Any = None) -> None:
        super().__init__("LimitVersion", version)


class LimitAlreadyExistsError(AlreadyExistsError):
    def __init__(self, slug: Any = None) -> None:
        super().__init__("Limit", slug)


class LimitVersionNotEditableError(NotEditableError):
    def __init__(self, state: str = "") -> None:
        super().__init__("LimitVersion", state)


# — Policies ──────────────────────────────────────────────────────────────────

class PolicyNotFoundError(NotFoundError):
    def __init__(self, policy_id: Any = None) -> None:
        super().__init__("Policy", policy_id)


class PolicyVersionNotFoundError(NotFoundError):
    def __init__(self, version: Any = None) -> None:
        super().__init__("PolicyVersion", version)


class PolicyAlreadyExistsError(AlreadyExistsError):
    def __init__(self, slug: Any = None) -> None:
        super().__init__("Policy", slug)


class PolicyVersionNotEditableError(NotEditableError):
    def __init__(self, state: str = "") -> None:
        super().__init__("PolicyVersion", state)


# — System LLM Roles ──────────────────────────────────────────────────────────

class SystemLLMRoleNotFoundError(NotFoundError):
    def __init__(self, role: Any = None) -> None:
        super().__init__("SystemLLMRole", role)


class SystemLLMRoleValidationError(ValidationError):
    """SystemLLMRole configuration is invalid."""


# — Files / Uploads ───────────────────────────────────────────────────────────

class ChatAttachmentNotFoundError(NotFoundError):
    def __init__(self, attachment_id: Any = None) -> None:
        super().__init__("ChatAttachment", attachment_id)


class FileDeliveryNotFoundError(NotFoundError):
    def __init__(self, file_id: Any = None) -> None:
        super().__init__("File", file_id)


# — Document Upload ───────────────────────────────────────────────────────────

class CollectionDocumentUploadError(AppError):
    """Base error for collection document upload operations."""
    http_status = 400
    code = "DOCUMENT_UPLOAD_ERROR"


class NotDocumentCollectionError(CollectionDocumentUploadError):
    """Collection is not a document-type collection."""
    code = "NOT_DOCUMENT_COLLECTION"


class CSVValidationError(AppError):
    """CSV validation failed."""
    http_status = 400
    code = "CSV_VALIDATION_ERROR"

    def __init__(self, message: str, errors: list | None = None) -> None:
        super().__init__(message)
        self.details = {"errors": errors or []}


# — Adapters ──────────────────────────────────────────────────────────────────

class ConnectorError(ExternalServiceError):
    """Generic connector / adapter error."""


class UpstreamError(ConnectorError):
    """Upstream returned an error response."""


# ──────────────────────────────────────────────────────────────────────────────
# BACKWARD-COMPAT ALIASES
# Old names that may be imported elsewhere — keep until cleaned up.
# ──────────────────────────────────────────────────────────────────────────────

NotFoundException = NotFoundError
ValidationException = ValidationError
DuplicateError = AlreadyExistsError


# ──────────────────────────────────────────────────────────────────────────────
# Exception handlers (migrated from core/errors.py)
# ──────────────────────────────────────────────────────────────────────────────

logger = get_logger(__name__)


class APIError(Exception):
    """Legacy explicit-code exception for backward compatibility."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.details = details or {}


_HTTP_STATUS_CODE: Dict[int, str] = {
    400: "VALIDATION_ERROR",
    401: "INVALID_CREDENTIALS",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
    504: "GATEWAY_TIMEOUT",
}


def _problem(code: str, message: str, http_status: int, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "type": "about:blank",
        "title": message,
        "status": http_status,
        "code": code,
        "detail": message,
        "trace_id": get_request_id() or "",
    }
    if details:
        body["details"] = details
    return body


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=_problem(exc.code, str(exc), exc.http_status, exc.details or None),
        media_type="application/problem+json",
    )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=_problem(exc.code, str(exc), exc.http_status, exc.details or None),
        media_type="application/problem+json",
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = _HTTP_STATUS_CODE.get(exc.status_code, "UNKNOWN_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content=_problem(code, str(exc.detail), exc.status_code),
        media_type="application/problem+json",
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_problem("INTERNAL_ERROR", "Internal Server Error", 500),
        media_type="application/problem+json",
    )


def install_exception_handlers(app) -> None:
    """Register global handlers for domain/HTTP/unhandled exceptions."""
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
