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
import logging
import json

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

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
    """Send a message to a chat with SSE streaming (persist→stream→persist)"""
    content = body.get("content", "")
    use_rag = body.get("use_rag", False)
    model = body.get("model", None)
    
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    # Get idempotency key from headers
    idempotency_key = request.headers.get("Idempotency-Key")
    
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")
    
    # Require tenant_id from user context (no dev fallback)
    if not current_user.tenant_ids:
        raise HTTPException(status_code=400, detail="Tenant ID is required")
    tenant_id = uuid.UUID(str(current_user.tenant_ids[0]))

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
                model=model
            ):
                event_type = event.get("type")
                
                if event_type == "user_message":
                    # Notify about user message creation
                    data = json.dumps({"message_id": event["message_id"]})
                    yield f"event: user_message\ndata: {data}\n\n"
                
                elif event_type == "delta":
                    # Stream content chunk
                    yield f"event: delta\ndata: {event['content']}\n\n"
                
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

@router.post("/stream")
async def chat_stream_deprecated(
    payload: Dict[str, Any],
    llm: LLMClientProtocol = Depends(get_llm_client),
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory)
) -> StreamingResponse:
    """DEPRECATED: Use POST /{chat_id}/messages instead for unified SSE streaming"""
    """Server-Sent Events streaming chat endpoint with RAG support."""
    messages: List[Dict[str, Any]] = payload.get("messages", [])
    params: Dict[str, Any] = payload.get("params", {})
    model: Optional[str] = payload.get("model")
    use_rag: bool = payload.get("use_rag", False)
    
    # Get the last user message for RAG search
    last_user_message = None
    chat_id = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_message = msg.get("content", "")
            chat_id = msg.get("chat_id")
            break
    
    # Prepare messages for LLM - clean them from chat_id and other fields
    llm_messages = []
    for msg in messages:
        clean_msg = {
            "role": msg.get("role"),
            "content": msg.get("content")
        }
        llm_messages.append(clean_msg)
    
    # If no messages provided, create a basic user message
    if not llm_messages and last_user_message:
        llm_messages = [{"role": "user", "content": last_user_message}]
    
    # If RAG is enabled and we have a user message, add context
    if use_rag and last_user_message:
        try:
            from app.services.rag_search_service import RagSearchService
            
            # Get tenant_id from user (required)
            if not current_user.tenant_ids:
                raise HTTPException(status_code=400, detail="Tenant ID is required")
            tenant_id = current_user.tenant_ids[0]
            
            # Search for relevant documents
            search_service = RagSearchService()
            rag_results = await search_service.search(
                tenant_id=tenant_id,
                query=last_user_message,
                k=3  # Get top 3 relevant chunks
            )
            
            # Add RAG context to the system message
            if rag_results:
                context_parts = []
                for i, result in enumerate(rag_results, 1):
                    context_parts.append(f"{i}. {result.text}")
                
                context = "\n".join(context_parts)
                system_message = {
                    "role": "system",
                    "content": f"Use the following context to answer the user's question. If the context doesn't contain relevant information, say so.\n\nContext:\n{context}\n\nAnswer based on the provided context when possible."
                }
                
                # Insert system message at the beginning
                llm_messages.insert(0, system_message)
                
        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            # Continue without RAG context if search fails

    # Validate chat_id
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required in messages")
    
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat_id format")

    # Save user message to database
    user_message_id = None
    if last_user_message:
        try:
            messages_repo = repo_factory.get_chat_messages_repository()
            user_message = await messages_repo.create_message(
                chat_id=chat_uuid,
                role="user",
                content={"text": last_user_message},
                model=model
            )
            user_message_id = str(user_message.id)
        except Exception as e:
            logger.error(f"Failed to save user message: {e}")
            raise HTTPException(status_code=500, detail="Failed to save user message")

    async def _gen() -> AsyncGenerator[str, None]:
        assistant_content = ""
        try:
            # Stream response from LLM
            async for chunk in llm.chat_stream(llm_messages, model=model, **params):
                assistant_content += chunk
                yield f"data: {chunk}\n\n"
            
            # Save assistant message to database after streaming is complete
            if assistant_content:
                try:
                    messages_repo = repo_factory.get_chat_messages_repository()
                    assistant_message = await messages_repo.create_message(
                        chat_id=chat_uuid,
                        role="assistant",
                        content={"text": assistant_content},
                        model=model
                    )
                    # Send message ID to frontend
                    yield f"data: {{\"message_id\": \"{assistant_message.id}\"}}\n\n"
                except Exception as e:
                    logger.error(f"Failed to save assistant message: {e}")
                    # Don't raise here, just log the error
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Error in chat stream: {e}")
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(_gen(), media_type="text/event-stream")

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
