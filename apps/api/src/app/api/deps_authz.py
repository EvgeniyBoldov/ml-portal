from __future__ import annotations
from typing import Iterable, Set
from fastapi import Depends, HTTPException, status
from app.api.deps import get_current_user  # assumes user has 'scopes' attribute or claim

def require_scopes(required: Iterable[str]):
    required_set: Set[str] = set(required)
    async def _dep(user=Depends(get_current_user)):
        scopes: Set[str] = set(getattr(user, "scopes", []) or [])
        if not required_set.issubset(scopes):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_scope")
        return user
    return _dep
