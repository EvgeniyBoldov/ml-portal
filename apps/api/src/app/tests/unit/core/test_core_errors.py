"""
Unit tests for core/errors.py
"""
import pytest
from fastapi import HTTPException
from app.core.errors import (
    format_problem_payload,
    HTTP_STATUS_TO_CODE,
    APIError,
    http_exception_handler,
    fastapi_http_exception_handler,
    unhandled_exception_handler
)


def test_http_status_to_code_mapping():
    """Test HTTP status to error code mapping"""
    assert HTTP_STATUS_TO_CODE[400] == "VALIDATION_ERROR"
    assert HTTP_STATUS_TO_CODE[401] == "AUTH_REQUIRED"
    assert HTTP_STATUS_TO_CODE[403] == "FORBIDDEN"
    assert HTTP_STATUS_TO_CODE[404] == "NOT_FOUND"
    assert HTTP_STATUS_TO_CODE[409] == "IDEMPOTENCY_REPLAYED"
    assert HTTP_STATUS_TO_CODE[413] == "PAYLOAD_TOO_LARGE"
    assert HTTP_STATUS_TO_CODE[422] == "UNPROCESSABLE_ENTITY"
    assert HTTP_STATUS_TO_CODE[429] == "RATE_LIMITED"
    assert HTTP_STATUS_TO_CODE[500] == "INTERNAL_ERROR"


def test_format_problem_payload():
    """Test format_problem_payload function"""
    payload = format_problem_payload(
        code="NOT_FOUND",
        message="Resource not found",
        http_status=404
    )
    
    assert payload["status"] == 404
    assert payload["detail"] == "Resource not found"
    assert payload["code"] == "NOT_FOUND"
    assert payload["type"] == "about:blank"
    assert "trace_id" in payload


def test_format_problem_payload_with_details():
    """Test format_problem_payload with custom details"""
    payload = format_problem_payload(
        code="CUSTOM_ERROR",
        message="Custom error",
        http_status=400,
        details={"field": "value"}
    )
    
    assert payload["status"] == 400
    assert payload["code"] == "CUSTOM_ERROR"


def test_api_error():
    """Test APIError exception"""
    error = APIError(
        code="API_ERROR",
        message="API error",
        http_status=400
    )
    
    assert error.http_status == 400
    assert str(error) == "API error"
    assert error.code == "API_ERROR"


def test_error_response_structure():
    """Test error response has all required fields"""
    payload = format_problem_payload(
        code="TEST_ERROR",
        message="Test error",
        http_status=400
    )
    
    required_fields = ["type", "title", "status", "code", "detail", "trace_id"]
    
    for field in required_fields:
        assert field in payload, f"Missing field: {field}"
    
    # Check field types
    assert isinstance(payload["status"], int)
    assert isinstance(payload["code"], str)
    assert isinstance(payload["detail"], str)
    assert isinstance(payload["trace_id"], str)
