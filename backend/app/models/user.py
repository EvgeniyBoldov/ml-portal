from sqlalchemy import Column, Integer, String, DateTime, func
from .base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), default="user", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
