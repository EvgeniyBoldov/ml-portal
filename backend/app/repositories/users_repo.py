from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.user import Users, UserTokens, UserRefreshTokens

class UsersRepo:
    def __init__(self, session: Session):
        self.s = session

    def by_login(self, login: str) -> Optional[Users]:
        return self.s.execute(select(Users).where(Users.login == login)).scalars().first()

    def get(self, user_id):
        return self.s.get(Users, user_id)

    # Refresh tokens
    def add_refresh(self, rec: UserRefreshTokens) -> None:
        self.s.add(rec)

    def get_refresh_by_hash(self, refresh_hash: str) -> Optional[UserRefreshTokens]:
        return self.s.execute(select(UserRefreshTokens).where(UserRefreshTokens.refresh_hash == refresh_hash)).scalars().first()

    def revoke_refresh(self, refresh_hash: str) -> bool:
        rec = self.get_refresh_by_hash(refresh_hash)
        if rec and not rec.revoked:
            rec.revoked = True
            return True
        return False
