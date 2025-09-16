from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime, date

class RefreshResponse(BaseModel):
    access_token: Optional[str] = Field(None)
    refresh_token: Optional[str] = Field(None)
    token_type: Optional[str] = Field(None)
    expires_in: Optional[int] = Field(None)

class LoginRequest(BaseModel):
    login: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = Field(None)

class LoginResponse(BaseModel):
    access_token: Optional[str] = Field(None)
    refresh_token: Optional[str] = Field(None)
    token_type: Optional[str] = Field(None)
    expires_in: Optional[int] = Field(None)
    user: Optional[Dict[str, Any]] = Field(None)
