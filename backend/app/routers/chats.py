from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Iterable, List, Optional

from app.core.dependencies import current_user
from app.db import get_session
from app.models.chat import Chat
from app.models.message import Message
from app.schemas.chat import (
    ChatOut, ChatCreate, ChatUpdate,
    ChatMessageIn, ChatMessageOut,
    ChatSendRequest, ChatSendResponse, ChatCreatedResponse
)

router = APIRouter(prefix="/chats", tags=["chats"])

# ------------------------------- helpers -------------------------------

def _ensure_owner(chat: Chat, username: str):
    if chat.owner_username != username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

def _first_user_text(messages: List[ChatMessageIn]) -> Optional[str]:
    # берём последнюю user-реплику (чаще всего это текущее сообщение)
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return None

def _make_title(messages: List[ChatMessageIn]) -> str:
    # Если есть system → возьмём её как тему; иначе — первую user, обрежем
    cand: Optional[str] = None
    for m in messages:
        if m.role == "system":
            cand = m.content
            break
    if not cand:
        for m in messages:
            if m.role == "user":
                cand = m.content
                break
    if not cand:
        cand = "Новый чат"

    cand = cand.strip().replace("\n", " ")
    if len(cand) > 60:
        cand = cand[:57] + "..."
    return cand or "Новый чат"

def _fake_llm_answer(text: str, use_rag: bool) -> str:
    # Заглушка генерации: эхо + RAG-флаг
    prefix = "[RAG] " if use_rag else ""
    return f"{prefix}Эхо: {text}"

def _chunkify(s: str, n: int = 20) -> Iterable[str]:
    # режем ответ на куски для стрима
    for i in range(0, len(s), n):
        yield s[i:i+n]

# ------------------------------- list/create/update/delete -------------------------------

@router.get("", response_model=List[ChatOut])
def list_chats(db: Session = Depends(get_session), user=Depends(current_user)):
    items = (
        db.query(Chat)
        .filter(Chat.owner_username == user.username)
        .order_by(Chat.id.desc())
        .all()
    )
    return items

# Оставляем на будущее: явное создание пустого чата (не используется в новой логике)
@router.post("", response_model=ChatOut, status_code=201)
def create_chat(
    payload: Optional[ChatCreate] = Body(default=None),
    db: Session = Depends(get_session),
    user=Depends(current_user),
):
    title = payload.title if (payload and payload.title) else "Новый чат"
    rag = payload.rag_enabled if payload else False
    chat = Chat(owner_username=user.username, title=title, rag_enabled=rag)
    db.add(chat); db.flush()
    return chat

@router.patch("/{chat_id}", response_model=ChatOut)
def update_chat(
    chat_id: int,
    payload: ChatUpdate,
    db: Session = Depends(get_session),
    user=Depends(current_user),
):
    chat = db.query(Chat).get(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    _ensure_owner(chat, user.username)
    if payload.title is not None:
        chat.title = payload.title
    if payload.rag_enabled is not None:
        chat.rag_enabled = payload.rag_enabled
    db.add(chat)
    return chat

@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: int, db: Session = Depends(get_session), user=Depends(current_user)):
    chat = db.query(Chat).get(chat_id)
    if not chat:
        return
    _ensure_owner(chat, user.username)
    db.delete(chat)

# ------------------------------- send: first message (no id) -------------------------------

@router.post("/send", response_model=ChatCreatedResponse)
def send_new_chat(
    payload: ChatSendRequest,
    db: Session = Depends(get_session),
    user=Depends(current_user),
):
    # создать чат
    title = _make_title(payload.messages)
    chat = Chat(owner_username=user.username, title=title, rag_enabled=False)
    db.add(chat); db.flush()

    # взять актуальное пользовательское сообщение
    last_user = _first_user_text(payload.messages)
    if not last_user:
        raise HTTPException(422, detail="At least one 'user' message is required")

    # сохранить user message
    m_user = Message(chat_id=chat.id, role="user", content=last_user)
    db.add(m_user)

    # сгенерировать ответ ассистента (заглушка) и сохранить
    answer = _fake_llm_answer(last_user, payload.use_rag)
    m_assist = Message(chat_id=chat.id, role="assistant", content=answer)
    db.add(m_assist)

    # (опционально) ссылки при RAG
    refs = [{"id": "doc_1", "score": 0.93}] if payload.use_rag else None

    return {
        "chat": chat,
        "assistant": {"id": m_assist.id, "role": "assistant", "content": m_assist.content},
        "references": refs,
    }

# ------------------------------- send: existing chat (non-stream) -------------------------------

@router.post("/{chat_id}/send", response_model=ChatSendResponse)
def send_existing_chat(
    chat_id: int,
    payload: ChatSendRequest,
    db: Session = Depends(get_session),
    user=Depends(current_user),
):
    chat = db.query(Chat).get(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    _ensure_owner(chat, user.username)

    last_user = _first_user_text(payload.messages)
    if not last_user:
        raise HTTPException(422, detail="At least one 'user' message is required")

    m_user = Message(chat_id=chat.id, role="user", content=last_user)
    db.add(m_user)

    answer = _fake_llm_answer(last_user, payload.use_rag)
    m_assist = Message(chat_id=chat.id, role="assistant", content=answer)
    db.add(m_assist)

    refs = [{"id": "doc_1", "score": 0.93}] if payload.use_rag else None

    return {
        "assistant": {"id": m_assist.id, "role": "assistant", "content": m_assist.content},
        "references": refs,
    }

# ------------------------------- send: existing chat (stream) -------------------------------

@router.post("/{chat_id}/send/stream")
def send_existing_chat_stream(
    chat_id: int,
    payload: ChatSendRequest,
    db: Session = Depends(get_session),
    user=Depends(current_user),
):
    chat = db.query(Chat).get(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    _ensure_owner(chat, user.username)

    last_user = _first_user_text(payload.messages)
    if not last_user:
        raise HTTPException(422, detail="At least one 'user' message is required")

    # на заглушке: готовим полный ответ
    full = _fake_llm_answer(last_user, payload.use_rag)

    # сохраняем user сразу
    m_user = Message(chat_id=chat.id, role="user", content=last_user)
    db.add(m_user); db.flush()

    # отдадим стримом, а в конце допишем ассистента в БД
    def generator():
        for chunk in _chunkify(full, 20):
            yield chunk
        # здесь можно добавить "[DONE]" для SSE, но фронт читает и сырые чанки

    # после завершения ответа сохраним ассистента
    def on_close():
        m_assist = Message(chat_id=chat.id, role="assistant", content=full)
        db.add(m_assist); db.flush()

    # StreamingResponse не имеет "on_close" хука — в реальной интеграции лучше стримить из корутины
    # и после возврата результата сохранять. Для заглушки просто вернём поток.
    return StreamingResponse(generator(), media_type="text/plain; charset=utf-8")
