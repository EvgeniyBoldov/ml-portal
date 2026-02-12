from typing import AsyncGenerator, Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.core.sse import format_sse
from app.api.deps import get_llm_client, db_session, get_current_user, get_redis
from app.core.security import UserCtx
from app.repositories.factory import get_async_repository_factory
from app.core.http.clients import LLMClientProtocol
from app.repositories.factory import AsyncRepositoryFactory
from app.services.chat_stream_service import ChatStreamService
import uuid
from app.core.logging import get_logger
import json

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)

@router.get("/models")
async def list_llm_models():
    """Get list of available LLM models"""
    from app.core.config import get_settings
    settings = get_settings()
    
    # Return available models based on provider
    models = []
    if settings.LLM_PROVIDER == "groq":
        models = [
            {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B", "provider": "groq"},
            {"id": "llama-3.1-70b-versatile", "name": "Llama 3.1 70B", "provider": "groq"},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "provider": "groq"},
        ]
    elif settings.LLM_PROVIDER == "openai":
        models = [
            {"id": "gpt-4-turbo-preview", "name": "GPT-4 Turbo", "provider": "openai"},
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "openai"},
        ]
    else:
        # Local or custom provider
        models = [
            {"id": "default", "name": "Default Model", "provider": settings.LLM_PROVIDER},
        ]
    
    return {"models": models}


@router.get("/agents")
async def list_chat_agents(
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user)
):
    """Get list of available agents for chat selection"""
    from app.services.agent_service import AgentService
    
    service = AgentService(session)
    agents, _ = await service.list_agents(limit=50)
    
    # Return agents with basic info (v2: no is_active/tools on container)
    return {
        "agents": [
            {
                "slug": agent.slug,
                "name": agent.name,
                "description": agent.description,
            }
            for agent in agents
        ]
    }

@router.get("")
async def list_chats(
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """List chats with pagination and search"""
    chats_repo = repo_factory.get_chats_repository()
    chats = await chats_repo.get_user_chats(
        user_id=str(current_user.id),
        limit=limit
    )
    
    # Simple pagination for now
    next_cursor = None
    if len(chats) == limit:
        next_cursor = str(len(chats))
    
    # Convert to dict format for API response
    items = []
    for chat in chats:
        items.append({
            "id": str(chat.id),
            "name": chat.name,
            "created_at": chat.created_at.isoformat() + "Z" if chat.created_at else None,
            "updated_at": chat.updated_at.isoformat() + "Z" if chat.updated_at else None,
            "tags": chat.tags or []
        })
    
    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None
    }

@router.post("")
async def create_chat(
    body: Dict[str, Any],
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Create a new chat"""
    name = body.get("name", "New Chat")
    tags = body.get("tags", [])
    
    chats_repo = repo_factory.get_chats_repository()
    chat = await chats_repo.create_chat(
        owner_id=uuid.UUID(current_user.id),
        name=name,
        tags=tags
    )
    
    return {
        "chat_id": str(chat.id)
    }

@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: str,
    limit: int = Query(50, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """List messages for a chat with keyset pagination (cursor = ISO timestamp)"""
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")
    
    messages_repo = repo_factory.get_chat_messages_repository()
    
    # Use keyset pagination with cursor
    messages = await messages_repo.get_chat_messages(
        chat_id=str(chat_uuid),
        limit=limit,
        cursor=cursor
    )
    
    # Convert to dict format for API response
    items = []
    for message in messages:
        # Extract text content from content object
        content_text = message.content
        if isinstance(content_text, dict) and "text" in content_text:
            content_text = content_text["text"]
        elif isinstance(content_text, dict):
            content_text = str(content_text)
        
        items.append({
            "id": str(message.id),
            "chat_id": str(message.chat_id),
            "role": message.role,
            "content": content_text,
            "created_at": message.created_at.isoformat() + "Z" if message.created_at else None
        })
    
    # Calculate next cursor based on last message's created_at
    next_cursor = None
    if len(items) == limit and items:
        # Use created_at of last message as cursor
        next_cursor = items[-1]["created_at"]
    
    return {
        "items": items,
        "next_cursor": next_cursor,
        "limit": limit
    }

@router.post("/{chat_id}/messages")
async def send_message_stream(
    chat_id: str,
    body: Dict[str, Any],
    request: Request,
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(get_redis),
    llm: LLMClientProtocol = Depends(get_llm_client),
    current_user: UserCtx = Depends(get_current_user)
) -> StreamingResponse:
    """Send a message to a chat with SSE streaming (persist→stream→persist)
    
    Body params:
        content: str - Message content (required)
        model: str - LLM model override (optional)
        agent_slug: str - Agent to use (default: "assistant" with auto-routing)
        use_rag: bool - Legacy flag, maps to "rag-search" agent (deprecated)
    """
    content = body.get("content", "")
    model = body.get("model", None)
    agent_slug = body.get("agent_slug", None)
    use_rag = body.get("use_rag", False)
    
    # Legacy compat: use_rag=True → rag-search agent
    if not agent_slug:
        agent_slug = "rag-search" if use_rag else "assistant"
    
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    # Get idempotency key from headers
    idempotency_key = request.headers.get("Idempotency-Key")
    
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")
    
    # Resolve tenant_id: prefer from user token; fallback to chat's tenant
    tenant_id: Optional[uuid.UUID] = None
    if current_user.tenant_ids:
        try:
            tenant_id = uuid.UUID(str(current_user.tenant_ids[0]))
        except Exception:
            tenant_id = None
    if tenant_id is None:
        # Fallback: fetch chat to derive tenant_id
        try:
            from sqlalchemy import select
            from app.models.chat import Chats
            result = await session.execute(select(Chats).where(Chats.id == chat_uuid))
            chat_row = result.scalar_one_or_none()
            if chat_row and chat_row.tenant_id:
                tenant_id = uuid.UUID(str(chat_row.tenant_id))
            else:
                raise HTTPException(status_code=400, detail="Tenant ID is required")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Tenant ID is required")

    # Use repository factory bound to the current request's DB session
    repo_factory = AsyncRepositoryFactory(session, tenant_id, current_user.id)
    chats_repo = repo_factory.get_chats_repository()
    messages_repo = repo_factory.get_chat_messages_repository()
    
    service = ChatStreamService(
        session=session,
        redis=redis,
        llm_client=llm,
        chats_repo=chats_repo,
        messages_repo=messages_repo
    )
    
    # Stream response
    async def _gen() -> AsyncGenerator[str, None]:
        try:
            async for event in service.send_message_stream(
                chat_id=str(chat_uuid),
                user_id=str(current_user.id),
                content=content,
                idempotency_key=idempotency_key,
                use_rag=use_rag,
                model=model,
                agent_slug=agent_slug
            ):
                event_type = event.get("type")
                
                if event_type == "user_message":
                    # Notify about user message creation
                    data = json.dumps({"message_id": event["message_id"]})
                    yield f"event: user_message\ndata: {data}\n\n"
                
                elif event_type == "status":
                    # Stream status updates
                    data = json.dumps({"stage": event.get("stage", "")})
                    yield f"event: status\ndata: {data}\n\n"
                
                elif event_type == "delta":
                    # Stream content chunk preserving newlines per SSE spec
                    try:
                        yield "event: delta\n"
                        chunk_text = str(event.get('content', ''))
                        for line in chunk_text.splitlines():
                            yield f"data: {line}\n"
                        # Preserve trailing newline
                        if chunk_text.endswith("\n"):
                            yield "data:\n"
                        yield "\n"
                    except Exception:
                        # Fallback: single data line
                        yield f"event: delta\ndata: {event.get('content','')}\n\n"
                
                elif event_type == "final":
                    # Send final message ID
                    data = json.dumps({"message_id": event["message_id"]})
                    yield f"event: final\ndata: {data}\n\n"
                
                elif event_type == "cached":
                    # Return cached result
                    data = json.dumps({
                        "user_message_id": event["user_message_id"],
                        "assistant_message_id": event["assistant_message_id"]
                    })
                    yield f"event: cached\ndata: {data}\n\n"
                
                elif event_type == "error":
                    # Send error
                    data = json.dumps({"error": event["error"]})
                    yield f"event: error\ndata: {data}\n\n"
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Error in chat stream: {e}", exc_info=True)
            data = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {data}\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(_gen(), media_type="text/event-stream")

@router.patch("/{chat_id}")
async def update_chat(
    chat_id: str,
    body: Dict[str, Any],
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Update chat name"""
    name = body.get("name", "")
    
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")
    
    chats_repo = repo_factory.get_chats_repository()
    chat = await chats_repo.update_chat(chat_uuid, name=name)
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return {
        "id": str(chat.id),
        "name": chat.name,
        "created_at": chat.created_at.isoformat() + "Z" if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() + "Z" if chat.updated_at else None,
        "tags": chat.tags or []
    }

@router.put("/{chat_id}/tags")
async def update_chat_tags(
    chat_id: str,
    body: Dict[str, Any],
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Update chat tags"""
    tags = body.get("tags", [])
    
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")
    
    chats_repo = repo_factory.get_chats_repository()
    chat = await chats_repo.update_chat(chat_uuid, tags=tags)
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return {"id": chat_id, "tags": tags}

@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
):
    """Delete a chat"""
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")
    
    chats_repo = repo_factory.get_chats_repository()
    success = await chats_repo.delete_chat(chat_uuid)
    
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return {"id": chat_id, "deleted": True}

@router.post("/chat")
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
