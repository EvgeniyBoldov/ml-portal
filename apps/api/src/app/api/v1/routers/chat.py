from typing import AsyncGenerator, Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from core.sse import format_sse, wrap_sse_stream
from core.sse_protocol import EVENT_DONE
from api.deps import get_llm_client
from core.http.clients import LLMClientProtocol
import uuid

router = APIRouter(tags=["chat"])

# Mock data for development
MOCK_CHATS = [
    {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "Test Chat 1",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "tags": ["test", "demo"]
    },
    {
        "id": "550e8400-e29b-41d4-a716-446655440002", 
        "name": "Test Chat 2",
        "created_at": "2024-01-02T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "tags": ["test"]
    }
]

MOCK_MESSAGES = {
    "550e8400-e29b-41d4-a716-446655440001": [
        {
            "id": "msg-1",
            "chat_id": "550e8400-e29b-41d4-a716-446655440001",
            "role": "user",
            "content": "Hello!",
            "created_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": "msg-2",
            "chat_id": "550e8400-e29b-41d4-a716-446655440001", 
            "role": "assistant",
            "content": "Hi there! How can I help you?",
            "created_at": "2024-01-01T00:01:00Z"
        }
    ],
    "550e8400-e29b-41d4-a716-446655440002": [
        {
            "id": "msg-3",
            "chat_id": "550e8400-e29b-41d4-a716-446655440002",
            "role": "user", 
            "content": "What's the weather like?",
            "created_at": "2024-01-02T00:00:00Z"
        }
    ]
}

@router.get("")
async def list_chats(
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    q: Optional[str] = Query(None)
):
    """List chats with pagination and search"""
    chats = MOCK_CHATS.copy()
    
    # Simple search filter
    if q:
        chats = [chat for chat in chats if q.lower() in chat["name"].lower()]
    
    # Simple pagination
    start_idx = 0
    if cursor:
        try:
            start_idx = int(cursor)
        except ValueError:
            start_idx = 0
    
    end_idx = start_idx + limit
    paginated_chats = chats[start_idx:end_idx]
    
    return {
        "items": paginated_chats,
        "next_cursor": str(end_idx) if end_idx < len(chats) else None,
        "has_more": end_idx < len(chats)
    }

@router.post("")
async def create_chat(
    body: Dict[str, Any]
):
    """Create a new chat"""
    name = body.get("name", "New Chat")
    tags = body.get("tags", [])
    
    new_chat = {
        "id": str(uuid.uuid4()),
        "name": name,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z", 
        "tags": tags
    }
    
    MOCK_CHATS.append(new_chat)
    return {"chat_id": new_chat["id"]}

@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: str,
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None)
):
    """List messages for a chat"""
    messages = MOCK_MESSAGES.get(chat_id, [])
    
    # Simple pagination
    start_idx = 0
    if cursor:
        try:
            start_idx = int(cursor)
        except ValueError:
            start_idx = 0
    
    end_idx = start_idx + limit
    paginated_messages = messages[start_idx:end_idx]
    
    return {
        "items": paginated_messages,
        "next_cursor": str(end_idx) if end_idx < len(messages) else None,
        "has_more": end_idx < len(messages)
    }

@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    body: Dict[str, Any]
):
    """Send a message to a chat"""
    content = body.get("content", "")
    use_rag = body.get("use_rag", False)
    response_stream = body.get("response_stream", False)
    
    # Add user message
    user_message = {
        "id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "role": "user",
        "content": content,
        "created_at": "2024-01-01T00:00:00Z"
    }
    
    if chat_id not in MOCK_MESSAGES:
        MOCK_MESSAGES[chat_id] = []
    MOCK_MESSAGES[chat_id].append(user_message)
    
    # Generate assistant response
    assistant_message = {
        "id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "role": "assistant", 
        "content": f"Response to: {content}",
        "created_at": "2024-01-01T00:01:00Z"
    }
    
    MOCK_MESSAGES[chat_id].append(assistant_message)
    
    if response_stream:
        # Return streaming response
        async def _gen():
            yield f"data: {assistant_message['content']}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(_gen(), media_type="text/event-stream")
    else:
        return assistant_message

@router.patch("/{chat_id}")
async def update_chat(
    chat_id: str,
    body: Dict[str, Any]
):
    """Update chat name"""
    name = body.get("name", "")
    
    for chat in MOCK_CHATS:
        if chat["id"] == chat_id:
            chat["name"] = name
            chat["updated_at"] = "2024-01-01T00:00:00Z"
            return chat
    
    raise HTTPException(status_code=404, detail="Chat not found")

@router.put("/{chat_id}/tags")
async def update_chat_tags(
    chat_id: str,
    body: Dict[str, Any]
):
    """Update chat tags"""
    tags = body.get("tags", [])
    
    for chat in MOCK_CHATS:
        if chat["id"] == chat_id:
            chat["tags"] = tags
            chat["updated_at"] = "2024-01-01T00:00:00Z"
            return {"id": chat_id, "tags": tags}
    
    raise HTTPException(status_code=404, detail="Chat not found")

@router.delete("/{chat_id}")
async def delete_chat(chat_id: str):
    """Delete a chat"""
    for i, chat in enumerate(MOCK_CHATS):
        if chat["id"] == chat_id:
            MOCK_CHATS.pop(i)
            if chat_id in MOCK_MESSAGES:
                del MOCK_MESSAGES[chat_id]
            return {"id": chat_id, "deleted": True}
    
    raise HTTPException(status_code=404, detail="Chat not found")

@router.post("/stream")
async def chat_stream(
    payload: Dict[str, Any],
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> StreamingResponse:
    """Server-Sent Events streaming chat endpoint.

    Fix: do **not** emit a second `done` event — `wrap_sse_stream` already sends it.
    """
    messages: List[Dict[str, Any]] = payload.get("messages", [])
    params: Dict[str, Any] = payload.get("params", {})
    model: Optional[str] = payload.get("model")

    async def _gen() -> AsyncGenerator[str, None]:
        async for chunk in wrap_sse_stream(llm.chat_stream(messages, model=model, **params)):
            yield chunk
        # DO NOT yield EVENT_DONE here; wrap_sse_stream already does that.
    return StreamingResponse(_gen(), media_type="text/event-stream")

@router.post("")
async def chat(
    payload: Dict[str, Any],
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> JSONResponse:
    messages: List[Dict[str, Any]] = payload.get("messages", [])
    params: Dict[str, Any] = payload.get("params", {})
    model: Optional[str] = payload.get("model")
    try:
        result = await llm.chat(messages, model=model, **params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return JSONResponse(result)
