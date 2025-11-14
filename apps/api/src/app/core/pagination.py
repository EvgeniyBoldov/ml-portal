from __future__ import annotations
import base64
import json
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import uuid

@dataclass
class Cursor:
    """Cursor for pagination"""
    id: str
    created_at: datetime
    direction: str  # 'next' or 'prev'

@dataclass
class PaginationParams:
    """Pagination parameters"""
    limit: int = 20
    cursor: Optional[str] = None
    order: str = "desc"  # 'asc' or 'desc'

@dataclass
class PaginatedResponse:
    """Paginated response"""
    items: List[Any]
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    total_count: Optional[int] = None

def encode_cursor(cursor: Cursor) -> str:
    """Encode cursor to opaque string"""
    data = {
        "id": cursor.id,
        "created_at": cursor.created_at.isoformat(),
        "direction": cursor.direction
    }
    json_str = json.dumps(data)
    return base64.b64encode(json_str.encode()).decode()

def decode_cursor(cursor_str: str) -> Cursor:
    """Decode cursor from opaque string"""
    try:
        json_str = base64.b64decode(cursor_str.encode()).decode()
        data = json.loads(json_str)
        return Cursor(
            id=data["id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            direction=data["direction"]
        )
    except Exception as e:
        raise ValueError(f"Invalid cursor format: {e}")

def create_cursor_from_item(item: Any, direction: str = "next") -> Cursor:
    """Create cursor from item (assuming item has id and created_at)"""
    return Cursor(
        id=str(item.id),
        created_at=item.created_at,
        direction=direction
    )

def validate_pagination_params(limit: int, cursor: Optional[str] = None, order: str = "desc") -> PaginationParams:
    """Validate pagination parameters"""
    if limit < 1 or limit > 100:
        raise ValueError("Limit must be between 1 and 100")
    
    if order not in ["asc", "desc"]:
        raise ValueError("Order must be 'asc' or 'desc'")
    
    decoded_cursor = None
    if cursor:
        try:
            decoded_cursor = decode_cursor(cursor)
        except ValueError as e:
            raise ValueError(f"Invalid cursor: {e}")
    
    return PaginationParams(limit=limit, cursor=decoded_cursor, order=order)

def build_pagination_response(
    items: List[Any], 
    has_next: bool = False, 
    has_prev: bool = False,
    total_count: Optional[int] = None
) -> PaginatedResponse:
    """Build paginated response with cursors"""
    next_cursor = None
    prev_cursor = None
    
    if items:
        if has_next:
            next_cursor = encode_cursor(create_cursor_from_item(items[-1], "next"))
        if has_prev:
            prev_cursor = encode_cursor(create_cursor_from_item(items[0], "prev"))
    
    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        total_count=total_count
    )
