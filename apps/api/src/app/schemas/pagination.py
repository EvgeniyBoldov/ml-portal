from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field, validator

class PaginationQuery(BaseModel):
    """Query parameters for pagination"""
    limit: int = Field(default=20, ge=1, le=100, description="Number of items per page")
    cursor: Optional[str] = Field(default=None, description="Cursor for pagination")
    order: str = Field(default="desc", description="Sort order: asc or desc")
    
    @validator('order')
    def validate_order(cls, v):
        if v not in ['asc', 'desc']:
            raise ValueError('Order must be "asc" or "desc"')
        return v

class PaginatedResponse(BaseModel):
    """Paginated response schema"""
    items: List[Any] = Field(description="List of items")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for next page")
    prev_cursor: Optional[str] = Field(default=None, description="Cursor for previous page")
    total_count: Optional[int] = Field(default=None, description="Total number of items")

class PaginationMeta(BaseModel):
    """Pagination metadata"""
    limit: int
    order: str
    has_next: bool
    has_prev: bool
    total_count: Optional[int] = None
