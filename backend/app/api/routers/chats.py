from fastapi import APIRouter, Depends, Request
from app.api.deps import db_session, get_current_user, rate_limit
from app.api.sse import sse_response

router = APIRouter(prefix="/chats", tags=["chats"])

# Simple in-memory store for stubs
_CHATS: dict[str, dict] = {}
_MESSAGES: dict[str, list[dict]] = {}

@router.get("")
async def list_chats(limit: int = 50, cursor: str | None = None, q: str | None = None, session=Depends(db_session), user=Depends(get_current_user)):
	items = [{"id": cid, "name": data.get("name") or f"Chat {cid}"} for cid, data in list(_CHATS.items())[:limit]]
	return {"items": items, "next_cursor": None}

@router.post("")
async def create_chat(payload: dict | None = None, session=Depends(db_session), user=Depends(get_current_user)):
	import uuid
	cid = str(uuid.uuid4())
	_CHATS[cid] = {"id": cid, "name": (payload or {}).get("name")}
	_MESSAGES[cid] = []
	return {"chat_id": cid}

@router.get("/{chat_id}/messages")
async def get_messages(chat_id: str, limit: int = 50, cursor: str | None = None, session=Depends(db_session), user=Depends(get_current_user)):
	msgs = _MESSAGES.get(chat_id, [])
	return {"items": msgs[:limit], "next_cursor": None}

@router.post("/{chat_id}/messages")
async def post_messages(chat_id: str, payload: dict, request: Request, session=Depends(db_session), user=Depends(get_current_user)):
	await rate_limit(request, f"chat_post:{chat_id}", 60, 60)
	if (payload or {}).get("response_stream"):
		def gen():
			yield {"data": "event: token"}
			yield {"data": "data: Привет..."}
			yield {"data": "data: Это стрим ответа."}
			yield {"data": "event: done"}
		return sse_response(gen())
	msg = {"role": "user", "content": (payload or {}).get("content", "")}
	_MESSAGES.setdefault(chat_id, []).append(msg)
	resp = {"role": "assistant", "content": "Привет! Это заглушка ответа."}
	_MESSAGES[chat_id].append(resp)
	return {"messages":[resp]}

@router.patch("/{chat_id}")
async def rename_chat(chat_id: str, payload: dict, session=Depends(db_session), user=Depends(get_current_user)):
	if chat_id not in _CHATS:
		_CHATS[chat_id] = {"id": chat_id}
	_CHATS[chat_id]["name"] = (payload or {}).get("name")
	return {"ok": True}

@router.delete("/{chat_id}")
async def delete_chat(chat_id: str, session=Depends(db_session), user=Depends(get_current_user)):
	_CHATS.pop(chat_id, None)
	_MESSAGES.pop(chat_id, None)
	return {"ok": True}
