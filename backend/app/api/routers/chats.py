from fastapi import APIRouter, Depends, Request
from app.api.deps import db_session, get_current_user, rate_limit
from app.api.sse import sse_response

router = APIRouter(prefix="/chats", tags=["chats"])

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
    return {"messages":[{"role":"assistant","content":"Привет! Это заглушка ответа."}]}
