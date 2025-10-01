"""
SSE protocol stability and contract enforcement
"""
from __future__ import annotations
from typing import Dict, Any, Optional, AsyncGenerator
import json
import asyncio
from datetime import datetime
from fastapi.responses import StreamingResponse

from app.schemas.common import Usage


class SSEEventType:
    """Standard SSE event types"""
    TOKEN = "token"
    PING = "ping" 
    SOURCES = "sources"
    DONE = "done"
    ERROR = "error"


class SSEProtocol:
    """SSE protocol handler with stable contract"""
    
    @staticmethod
    def send_token(text: str, is_final: bool = False) -> str:
        """Send token event"""
        return f"event: {SSEEventType.TOKEN}\ndata: {json.dumps({'text': text, 'final': is_final})}\n\n"
    
    @staticmethod
    def send_ping(timestamp: Optional[datetime] = None) -> str:
        """Send ping event for keep-alive"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        return f"event: {SSEEventType.PING}\ndata: {json.dumps({'timestamp': timestamp.isoformat()})}\n\n"
    
    @staticmethod
    def send_sources(sources: list[Dict[str, Any]]) -> str:
        """Send sources event for RAG"""
        return f"event: {SSEEventType.SOURCES}\ndata: {json.dumps({'sources': sources})}\n\n"
    
    @staticmethod
    def send_done(usage: Optional[Usage] = None, success: bool = True, error: Optional[str] = None) -> str:
        """Send done event - ALWAYS sent at end"""
        data = {
            'success': success,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if usage:
            data['usage'] = usage.model_dump()
        
        if error:
            data['error'] = error
            
        return f"event: {SSEEventType.DONE}\ndata: {json.dumps(data)}\n\n"
    
    @staticmethod
    def send_error(error: str, code: Optional[str] = None) -> str:
        """Send error event"""
        data = {
            'error': error,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if code:
            data['code'] = code
            
        return f"event: {SSEEventType.ERROR}\ndata: {json.dumps(data)}\n\n"


class SSEStreamer:
    """SSE streamer with stable protocol and error handling"""
    
    def __init__(self, ping_interval: int = 30):
        self.ping_interval = ping_interval
        self.last_ping = datetime.utcnow()
    
    async def stream_tokens(
        self, 
        text: str, 
        chunk_size: int = 1,
        include_sources: bool = False,
        sources: Optional[list[Dict[str, Any]]] = None,
        usage: Optional[Usage] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream tokens with stable SSE protocol
        
        Args:
            text: Text to stream
            chunk_size: Number of words per chunk
            include_sources: Whether to include sources
            sources: RAG sources to include
            usage: Usage statistics
        """
        try:
            words = text.split()
            current_text = ""
            
            # Send initial ping
            yield SSEProtocol.send_ping().encode("utf-8")
            
            # Stream tokens
            for i, word in enumerate(words):
                current_text += word + " "
                
                # Send token chunk
                if (i + 1) % chunk_size == 0 or i == len(words) - 1:
                    is_final = i == len(words) - 1
                    yield SSEProtocol.send_token(current_text.strip(), is_final).encode("utf-8")
                    current_text = ""
                
                # Send ping every ping_interval words
                if (i + 1) % self.ping_interval == 0:
                    yield SSEProtocol.send_ping().encode("utf-8")
                
                # Small delay for realistic streaming
                await asyncio.sleep(0.05)
            
            # Send sources if provided
            if include_sources and sources:
                yield SSEProtocol.send_sources(sources).encode("utf-8")
            
            # ALWAYS send done event
            yield SSEProtocol.send_done(usage=usage, success=True).encode("utf-8")
            
        except Exception as e:
            # Send error event
            yield SSEProtocol.send_error(str(e), "streaming_error").encode("utf-8")
            # ALWAYS send done event even on error
            yield SSEProtocol.send_done(success=False, error=str(e)).encode("utf-8")
    
    async def stream_error(self, error: str, code: Optional[str] = None) -> AsyncGenerator[bytes, None]:
        """Stream error with proper protocol"""
        try:
            # Send error event
            yield SSEProtocol.send_error(error, code).encode("utf-8")
            # ALWAYS send done event
            yield SSEProtocol.send_done(success=False, error=error).encode("utf-8")
        except Exception as e:
            # Fallback error handling
            yield SSEProtocol.send_error(f"Streaming error: {str(e)}", "streaming_fatal").encode("utf-8")
            yield SSEProtocol.send_done(success=False, error=f"Streaming error: {str(e)}").encode("utf-8")


def create_sse_response(
    streamer: SSEStreamer,
    stream_func,
    *args,
    **kwargs
) -> StreamingResponse:
    """Create SSE response with proper headers"""
    return StreamingResponse(
        stream_func(*args, **kwargs),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
