from __future__ import annotations
from typing import Dict, Any, AsyncGenerator
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.api.deps import db_session, get_current_user
from app.repositories.chats_repo import ChatsRepo
from app.schemas.chat_schemas import (
    ChatCreateRequest, ChatUpdateRequest, ChatTagsUpdateRequest,
    ChatMessageRequest, ChatMessageResponse, ChatOut, ChatMessageOut
)
from app.services.clients import llm_chat

router = APIRouter(prefix="/chats", tags=["chats"])

def _ser_chat(c) -> Dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "tags": c.tags or [],
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
    }

def _ser_msg(m) -> Dict[str, Any]:
    content = m.content if isinstance(m.content, str) else (m.content.get("text") if isinstance(m.content, dict) else str(m.content))
    return {
        "id": str(m.id),
        "chat_id": str(m.chat_id),
        "role": m.role,
        "content": content,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }

@router.get("")
def list_chats(
    limit: int = Query(100, ge=1, le=200),
    cursor: str | None = None,
    q: str | None = None,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    items = repo.list_chats(user["id"], q=q, limit=limit)
    return {"items": [_ser_chat(c) for c in items], "next_cursor": None}

@router.post("")
def create_chat(
    request: ChatCreateRequest,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    chat = repo.create_chat(user["id"], request.name, request.tags)
    return {"chat_id": str(chat.id)}

@router.patch("/{chat_id}")
def rename_chat(
    chat_id: str,
    request: ChatUpdateRequest,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    chat = repo.get(chat_id)
    if not chat or str(chat.owner_id) != str(user["id"]):
        raise HTTPException(status_code=404, detail="not_found")
    if request.name is not None:
        repo.rename_chat(chat_id, request.name or None)
    return _ser_chat(repo.get(chat_id))

@router.put("/{chat_id}/tags")
def update_tags(
    chat_id: str,
    request: ChatTagsUpdateRequest,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    chat = repo.get(chat_id)
    if not chat or str(chat.owner_id) != str(user["id"]):
        raise HTTPException(status_code=404, detail="not_found")
    repo.update_chat_tags(chat_id, request.tags)
    return {"id": chat_id, "tags": request.tags}

@router.get("/{chat_id}/messages")
def list_messages(
    chat_id: str,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    chat = repo.get(chat_id)
    if not chat or str(chat.owner_id) != str(user["id"]):
        raise HTTPException(status_code=404, detail="not_found")
    rows, next_cursor = repo.list_messages(chat_id, cursor=cursor, limit=limit)
    items = [_ser_msg(m) for m in rows]
    return {"items": items, "next_cursor": next_cursor}

@router.post("/{chat_id}/messages")
async def post_message(
    chat_id: str,
    request: ChatMessageRequest,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    chat = repo.get(chat_id)
    if not chat or str(chat.owner_id) != str(user["id"]):
        raise HTTPException(status_code=404, detail="not_found")

    # Store user message
    user_msg = repo.add_message(chat_id, "user", {"text": request.content})

    async def stream_resp() -> AsyncGenerator[bytes, None]:
      # Generate response with LLM (non-stream), then stream chunks to client
      messages = [{"role": "system", "content": "You are a helpful assistant."}]
      
      # Add RAG context if requested
      if request.use_rag:
          try:
              from app.services.rag_service import search
              rag_results = search(session, request.content, top_k=3)
              if rag_results.get("results"):
                  context = "\n\n".join([r.get("snippet", "") for r in rag_results["results"][:3]])
                  messages.append({"role": "system", "content": f"Context from knowledge base:\n{context}"})
          except Exception as e:
              print(f"RAG search failed: {e}")
      
      messages.append({"role": "user", "content": request.content})
      answer = llm_chat(messages)
      
      # Save assistant message
      repo.add_message(chat_id, "assistant", {"text": answer})
      # Stream by small chunks
      for i in range(0, len(answer), 100):
          chunk = answer[i:i+100]
          yield f"data: {chunk}\n\n".encode("utf-8")
          await asyncio.sleep(0)  # yield control

    if request.response_stream:
        return StreamingResponse(stream_resp(), media_type="text/event-stream")
    else:
        # non-streaming
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        
        # Add RAG context if requested
        if request.use_rag:
            try:
                from app.services.rag_service import search
                rag_results = search(session, request.content, top_k=3)
                if rag_results.get("results"):
                    context = "\n\n".join([r.get("snippet", "") for r in rag_results["results"][:3]])
                    messages.append({"role": "system", "content": f"Context from knowledge base:\n{context}"})
            except Exception as e:
                print(f"RAG search failed: {e}")
        
        messages.append({"role": "user", "content": request.content})
        answer = llm_chat(messages)
        repo.add_message(chat_id, "assistant", {"text": answer})
        return ChatMessageResponse(message_id=str(user_msg.id), content=request.content, answer=answer)

@router.delete("/{chat_id}")
def delete_chat(
    chat_id: str,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    chat = repo.get(chat_id)
    if not chat or str(chat.owner_id) != str(user["id"]):
        raise HTTPException(status_code=404, detail="not_found")
    repo.delete(chat_id)
    return {"id": chat_id, "deleted": True}
