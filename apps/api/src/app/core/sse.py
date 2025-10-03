from __future__ import annotations
import asyncio
import json
from typing import Any, AsyncGenerator, Dict, Optional, Callable
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
import logging

logger = logging.getLogger(__name__)

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
        
        lines.append("")  # Empty line to end message
        return "\n".join(lines)

class SSEStream:
    """Server-Sent Events stream handler"""
    
    def __init__(self, heartbeat_interval: int = 30):
        self.heartbeat_interval = heartbeat_interval
        self._closed = False
    
    async def stream(self, generator: AsyncGenerator[SSEMessage, None]) -> StreamingResponse:
        """Create streaming response from generator"""
        
        async def event_generator():
            try:
                async for message in generator:
                    if self._closed:
                        break
                    yield message.to_sse_format()
                
                # Send final done event
                if not self._closed:
                    done_message = SSEMessage(data="done", event="done")
                    yield done_message.to_sse_format()
                    
            except Exception as e:
                logger.error(f"SSE stream error: {e}")
                error_message = SSEMessage(
                    data={"error": str(e)}, 
                    event="error"
                )
                yield error_message.to_sse_format()
            finally:
                self._closed = True
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control"
            }
        )
    
    def close(self):
        """Close the stream"""
        self._closed = True

async def create_sse_stream(generator: AsyncGenerator[SSEMessage, None], heartbeat_interval: int = 30) -> StreamingResponse:
    """Create SSE stream from generator"""
    sse_stream = SSEStream(heartbeat_interval)
    return await sse_stream.stream(generator)

async def heartbeat_generator(interval: int = 30) -> AsyncGenerator[SSEMessage, None]:
    """Generator that sends heartbeat messages"""
    while True:
        await asyncio.sleep(interval)
        yield SSEMessage(data="heartbeat", event="heartbeat")

async def progress_generator(task_id: str, progress_callback) -> AsyncGenerator[SSEMessage, None]:
    """Generator for progress updates"""
    try:
        # Send initial message
        yield SSEMessage(
            data={"task_id": task_id, "status": "started"},
            event="progress",
            id=task_id
        )
        
        # Get progress updates
        async for progress in progress_callback():
            yield SSEMessage(
                data={"task_id": task_id, "progress": progress},
                event="progress",
                id=task_id
            )
            
            # Check if task is complete
            if progress.get("status") == "completed":
                break
        
        # Send completion message
        yield SSEMessage(
            data={"task_id": task_id, "status": "completed"},
            event="done",
            id=task_id
        )
        
    except Exception as e:
        logger.error(f"Progress generator error: {e}")
        yield SSEMessage(
            data={"task_id": task_id, "error": str(e)},
            event="error",
            id=task_id
        )

def validate_sse_request(request) -> bool:
    """Validate that request can handle SSE"""
    accept_header = request.headers.get("Accept", "")
    return "text/event-stream" in accept_header or "*/*" in accept_header

async def _data_to_sse_generator(data: dict, event: Optional[str], serialize_func: Callable) -> AsyncGenerator[str, None]:
    """Convert data to SSE generator"""
    try:
        message_data = serialize_func(data)
        message = SSEMessage(data=message_data, event=event)
        yield message.to_sse_format()
    except Exception as e:
        logger.error(f"SSE generator error: {e}")
        error_message = SSEMessage(
            data={"error": str(e)}, 
            event="error"
        )
        yield error_message.to_sse_format()

def wrap_sse_stream(generator: AsyncGenerator[SSEMessage, None], heartbeat_interval: int = 30) -> StreamingResponse:
    """Wrap generator in SSE stream"""
    return StreamingResponse(
        _sse_generator(generator, heartbeat_interval),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

async def _sse_generator(generator: AsyncGenerator[SSEMessage, None], heartbeat_interval: int):
    """Internal SSE generator with heartbeat"""
    last_heartbeat = asyncio.get_event_loop().time()
    
    try:
        async for message in generator:
            yield message.to_sse_format()
            last_heartbeat = asyncio.get_event_loop().time()
        
        # Send final done event
        done_message = SSEMessage(data="done", event="done")
        yield done_message.to_sse_format()
        
    except Exception as e:
        logger.error(f"SSE stream error: {e}")
        error_message = SSEMessage(
            data={"error": str(e)}, 
            event="error"
        )
        yield error_message.to_sse_format()

def format_sse(data: Any, event: Optional[str] = None, id: Optional[str] = None) -> str:
    """Format data as SSE message"""
    message = SSEMessage(data=data, event=event, id=id)
    return message.to_sse_format()

def sse_response(data: dict, event: Optional[str] = None, serialize_func: Callable = json.dumps) -> Response:
    """Create SSE response from data"""
    return StreamingResponse(
        _data_to_sse_generator(data, event, serialize_func),
        media_type="text/event-stream"
    )