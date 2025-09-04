from fastapi import Depends
from .auth import get_current_user, User

async def current_user(user: User = Depends(get_current_user)) -> User:
    return user