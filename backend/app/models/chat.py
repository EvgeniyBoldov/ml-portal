from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True)
    owner_username = Column(String(64), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    rag_enabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan", passive_deletes=True)
