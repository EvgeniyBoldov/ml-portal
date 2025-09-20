import uuid
from datetime import datetime, timezone

try:
    from apps.api.src.app.models.user import Users  # type: ignore
    from apps.api.src.app.models.chat import Chats, ChatMessages  # type: ignore
except Exception:
    from app.models.user import Users  # type: ignore
    from app.models.chat import Chats, ChatMessages  # type: ignore

try:
    from apps.api.src.app.core.security import hash_password  # type: ignore
except Exception:
    from app.core.security import hash_password  # type: ignore

def make_user(login="testuser", password="Testpassword123!", role="reader"):
    return Users(
        id=uuid.uuid4(),
        login=login,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

def make_chat(owner_id, name="Test Chat", tags=None):
    return Chats(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name=name,
        tags=tags or ["test"],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

def make_message(chat_id, role="user", text="Hello world"):
    return ChatMessages(
        id=uuid.uuid4(),
        chat_id=chat_id,
        role=role,
        content={"text": text},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
