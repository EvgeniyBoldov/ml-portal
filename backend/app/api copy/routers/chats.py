from __future__ import annotations
from typing import Dict, Any, AsyncGenerator, Callable
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.api.deps import db_session, get_current_user
from app.repositories.chats_repo import ChatsRepo
from app.schemas.chat_schemas import ChatCreateRequest, ChatUpdateRequest, ChatTagsUpdateRequest, ChatMessageRequest, ChatMessageResponse
from app.services import clients as llm_clients

router = APIRouter(prefix="/chats", tags=["chats"])

def _ser_chat(c): return {"id": str(c.id), "name": c.name, "tags": c.tags or []}
def _ser_msg(m): return {"id": str(m.id), "chat_id": str(m.chat_id), "role": m.role, "content": m.content.get("text") if isinstance(m.content, dict) else str(m.content)}

try: llm_chat: Callable = getattr(llm_clients, 'llm_chat')
except Exception:
    def llm_chat(messages): return "(stub) llm_chat not configured"

@router.get("")
def list_chats(limit: int = Query(100, ge=1, le=200), cursor: str | None = None, q: str | None = None, session: Session = Depends(db_session), user: Dict[str, Any] = Depends(get_current_user)):
    repo = ChatsRepo(session); items = repo.list_chats(user["id"], q=q, limit=limit)
    return {"items": [_ser_chat(c) for c in items], "next_cursor": None}

@router.post("")
def create_chat(request: ChatCreateRequest, session: Session = Depends(db_session), user: Dict[str, Any] = Depends(get_current_user)):
    repo = ChatsRepo(session); chat = repo.create_chat(user["id"], request.name, request.tags); return {"chat_id": str(chat.id)}

@router.post("/{chat_id}/messages")
async def post_message(chat_id: str, request: ChatMessageRequest, session: Session = Depends(db_session), user: Dict[str, Any] = Depends(get_current_user)):
    repo = ChatsRepo(session); chat = repo.get(chat_id)
    if not chat or chat.owner_id != user["id"]: raise HTTPException(status_code=404, detail="not_found")
    user_msg = repo.add_message(chat_id, "user", {"text": request.content})
    async def stream_resp() -> AsyncGenerator[bytes, None]:
        stream_fn = getattr(llm_clients, 'llm_chat_stream', None)
        if callable(stream_fn):
            async for delta in stream_fn([{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": request.content}]):
                if not isinstance(delta, str): delta = str(delta)
                yield f"data: {delta}\n\n".encode("utf-8")
            answer_final = llm_chat([{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": request.content}])
            repo.add_message(chat_id, "assistant", {"text": answer_final})
        else:
            answer = llm_chat([{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": request.content}])
            repo.add_message(chat_id, "assistant", {"text": answer})
            for i in range(0, len(answer), 100):
                chunk = answer[i:i+100]
                yield f"data: {chunk}\n\n".encode("utf-8")
    if request.response_stream: return StreamingResponse(stream_resp(), media_type="text/event-stream")
    else:
        answer = llm_chat([{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": request.content}])
        repo.add_message(chat_id, "assistant", {"text": answer})
        return ChatMessageResponse(message_id=str(user_msg.id), content=request.content, answer=answer)
