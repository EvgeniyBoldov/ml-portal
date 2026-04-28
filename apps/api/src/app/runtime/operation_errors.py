"""Typed runtime errors for operation validation/execution."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class RuntimeErrorCode(str, Enum):
    OPERATION_UNAVAILABLE = "operation_unavailable"
    OPERATION_AMBIGUOUS = "operation_ambiguous"
    OPERATION_INVALID_ARGS = "operation_invalid_args"
    OPERATION_TIMEOUT = "operation_timeout"
    OPERATION_EXECUTION_FAILED = "operation_execution_failed"
    OPERATION_CONFIRMATION_REQUIRED = "operation_confirmation_required"
    AGENT_WALL_TIME_EXCEEDED = "agent_wall_time_exceeded"
    AGENT_REQUIRED_OPERATION_CALL_MISSING = "agent_required_operation_call_missing"
    AGENT_MAX_TOOL_CALLS_EXCEEDED = "agent_max_tool_calls_exceeded"
    AGENT_NON_RETRYABLE_OPERATION_FAILURE = "agent_non_retryable_operation_failure"
    AGENT_NO_SUCCESSFUL_OPERATION_RESULT = "agent_no_successful_operation_result"
    AGENT_RUNTIME_EXCEPTION = "agent_runtime_exception"
    AGENT_PRECHECK_FAILED = "agent_precheck_failed"
    AGENT_UNAVAILABLE = "agent_unavailable"
    AGENT_NO_OPERATIONS = "agent_no_operations"


@dataclass(frozen=True)
class OperationValidationError:
    code: RuntimeErrorCode
    message: str
    field_path: Optional[str] = None
    retryable: bool = True

    def to_metadata(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "error_code": self.code.value,
            "retryable": self.retryable,
        }
        if self.field_path:
            payload["field_path"] = self.field_path
        return payload

    def to_user_message(self) -> str:
        if self.field_path:
            return f"{self.message} (field: {self.field_path})"
        return self.message


@dataclass(frozen=True)
class OperationExecutionError:
    code: RuntimeErrorCode
    message: str
    retryable: bool

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "error_code": self.code.value,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class OperationResultEnvelope:
    operation_slug: str
    call_id: str
    success: bool
    error_code: Optional[RuntimeErrorCode] = None
    safe_message: Optional[str] = None
    retryable: Optional[bool] = None
    data: Optional[Dict[str, Any]] = None

    def to_metadata(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "operation_slug": self.operation_slug,
            "call_id": self.call_id,
            "success": self.success,
        }
        if self.error_code is not None:
            payload["error_code"] = self.error_code.value
        if self.safe_message is not None:
            payload["safe_message"] = self.safe_message
        if self.retryable is not None:
            payload["retryable"] = self.retryable
        if self.data is not None:
            payload["data"] = self.data
        return payload
