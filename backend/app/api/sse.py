import asyncio
import json
from datetime import datetime
from starlette.responses import StreamingResponse

def sse_response(source, heartbeat_interval: int = 30):
    """
    Create SSE response with heartbeat
    
    Args:
        source: Generator/async generator that yields data
        heartbeat_interval: Heartbeat interval in seconds (default 30)
    """
    async def gen():
        last_heartbeat = datetime.now()
        
        try:
            async for item in source:
                # Send data
                data = item.get("data", "")
                if isinstance(data, dict):
                    data = json.dumps(data)
                yield f"data: {data}\n\n"
                
                # Update heartbeat timestamp
                last_heartbeat = datetime.now()
                
                # Check if we need to send heartbeat
                now = datetime.now()
                if (now - last_heartbeat).total_seconds() >= heartbeat_interval:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': now.isoformat()})}\n\n"
                    last_heartbeat = now
                    
        except asyncio.CancelledError:
            # Client disconnected
            pass
        except Exception as e:
            # Send error event
            error_data = json.dumps({
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            })
            yield f"data: {error_data}\n\n"
    
    return StreamingResponse(
        gen(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

def sse_heartbeat_response(heartbeat_interval: int = 30):
    """
    Create SSE response that only sends heartbeats
    
    Args:
        heartbeat_interval: Heartbeat interval in seconds
    """
    async def gen():
        while True:
            try:
                heartbeat_data = json.dumps({
                    "type": "heartbeat",
                    "timestamp": datetime.now().isoformat()
                })
                yield f"data: {heartbeat_data}\n\n"
                await asyncio.sleep(heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                error_data = json.dumps({
                    "type": "error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                yield f"data: {error_data}\n\n"
                break
    
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
