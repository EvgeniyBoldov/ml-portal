from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models.user import User as UserModel
from app.core.security import verify_password

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class User(BaseModel):
    username: str
    role: str = "user"

def authenticate_user(db: Session, username: str, password: str):
    user = db.query(UserModel).filter(UserModel.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return {"username": user.username, "role": user.role}

@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(),
                db: Session = Depends(get_session)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return Token(access_token=f"{user['username']}-token")


async def get_current_user(token: str = Depends(oauth2_scheme),
                           db: Session = Depends(get_session)) -> User:
    if not token.endswith("-token"):
        raise HTTPException(status_code=401, detail="Invalid token")
    username = token[:-6]
    user = db.query(UserModel).filter(UserModel.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return User(username=user.username, role=user.role)

@router.get("/me", response_model=User)
async def me(current: User = Depends(get_current_user)):
    return current