# app/api/routers/chats.py
from __future__ import annotations
from typing import Optional, Dict, Any, AsyncGenerator
import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.repositories.chats_repo import ChatsRepo
from app.services.chat_service import post_message
from app.services.clients import llm_chat

router = APIRouter(prefix="/chats", tags=["chats"])

# ---- serializers to match frontend expectations ----
def _ser_chat(c) -> Dict[str, Any]:
    # Chats model: id, name, owner_id, created_at, updated_at, last_message_at (optional)
    return {
        "id": str(c.id),
        "name": c.name or f"Chat {str(c.id)[:8]}",
    }

@router.get("")
def list_chats(
    limit: int = 50,
    cursor: Optional[str] = None,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    # get_current_user returns a dict, so we must index by "id"
    items = repo.list_chats(user["id"])[:limit]
    return {"items": [_ser_chat(c) for c in items], "next_cursor": None}

@router.post("")
def create_chat(
    payload: Dict[str, Any] | None = None,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    name = (payload or {}).get("name")
    chat = repo.create_chat(owner_id=user["id"], name=name)
    return {"chat_id": str(chat.id)}

async def _stream_llm_response(messages: list, use_rag: bool = False) -> AsyncGenerator[str, None]:
    """Стриминг ответа от LLM"""
    import httpx
    from app.core.config import settings
    
    # Подготавливаем запрос к LLM
    llm_payload = {
        "messages": messages,
        "temperature": 0.2,
        "use_rag": use_rag
    }
    
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST", 
                f"{settings.LLM_URL}/v1/chat/completions", 
                json=llm_payload
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Убираем "data: "
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        yield f"Ошибка при обращении к LLM: {str(e)}"

@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    payload: Dict[str, Any],
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Отправка сообщения в чат с интеграцией LLM"""
    content = payload.get("content", "")
    use_rag = payload.get("use_rag", False)
    response_stream = payload.get("response_stream", False)
    
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    # Проверяем существование чата
    repo = ChatsRepo(session)
    chat = repo.get(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Сохраняем сообщение пользователя
    user_message = post_message(
        session, 
        chat_id, 
        "user", 
        {"text": content}, 
        model="gpt-3.5-turbo"
    )
    
    # Получаем историю сообщений
    messages = repo.list_messages(chat_id)
    llm_messages = []
    for msg in messages:
        if msg.role == "user":
            llm_messages.append({"role": "user", "content": msg.content.get("text", "")})
        elif msg.role == "assistant":
            llm_messages.append({"role": "assistant", "content": msg.content.get("text", "")})
    
    if response_stream:
        # Стриминг ответ
        async def generate_response():
            full_response = ""
            async for chunk in _stream_llm_response(llm_messages, use_rag):
                full_response += chunk
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            
            # Сохраняем полный ответ в БД
            post_message(
                session,
                chat_id,
                "assistant", 
                {"text": full_response},
                model="gpt-3.5-turbo"
            )
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate_response(), 
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    else:
        # Обычный ответ
        try:
            response_text = llm_chat(llm_messages, temperature=0.2)
            
            # Сохраняем ответ в БД
            assistant_message = post_message(
                session,
                chat_id,
                "assistant",
                {"text": response_text},
                model="gpt-3.5-turbo"
            )
            
            return {
                "message_id": str(assistant_message.id),
                "content": response_text,
                "answer": response_text
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")