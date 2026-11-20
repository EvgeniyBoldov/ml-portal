from __future__ import annotations
import json
from typing import Any, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

EVENT_META = "meta"
EVENT_TOKEN = "token"
EVENT_DONE = "done"

class SSEMessage:
    """Server-Sent Event message"""
    
    def __init__(self, data: Any, event: Optional[str] = None, id: Optional[str] = None, retry: Optional[int] = None):
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry
    
    def to_sse_format(self) -> str:
        """Convert to SSE format"""
        lines = []
        
        if self.event:
            lines.append(f"event: {self.event}")
        
        if self.id:
            lines.append(f"id: {self.id}")
        
        if self.retry:
            lines.append(f"retry: {self.retry}")
        
        # Handle data - can be string or dict
        if isinstance(self.data, dict):
            data_str = json.dumps(self.data)
        else:
            data_str = str(self.data)
        
        # Split data into multiple lines if needed
        for line in data_str.split('\n'):
            lines.append(f"data: {line}")
        
        # SSE messages must end with double newline (\n\n)
        return "\n".join(lines) + "\n\n"


def format_sse(data: Any, event: Optional[str] = None, id: Optional[str] = None) -> str:
    """Format data as SSE message"""
    message = SSEMessage(data=data, event=event, id=id)
    return message.to_sse_format()

