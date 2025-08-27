from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

_FAKE_USERS_DB = {
    "admin": {"username": "admin", "password": "admin", "role": "admin"},
    "user":  {"username": "user",  "password": "user",  "role": "user"},  # опционально
}

_FAKE_TOKEN = "admin-token"  # токен-заглушка (для простоты один на всех)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class User(BaseModel):
    username: str
    role: str = "user"

def authenticate_user(username: str, password: str) -> User | None:
    user = _FAKE_USERS_DB.get(username)
    if not user or user["password"] != password:
        return None
    return User(username=user["username"], role=user["role"])  # type: ignore[arg-type]

@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username or password")
    # Возвращаем фиксированный токен-заглушку
    return Token(access_token=_FAKE_TOKEN)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    if token != _FAKE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token")
    # Для простоты всегда возвращаем админа (можно расширить при желании)
    return User(username="admin", role="admin")


@router.get("/me", response_model=User)
async def me(current: User = Depends(get_current_user)):
    return current
