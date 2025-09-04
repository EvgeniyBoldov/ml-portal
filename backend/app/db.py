import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.base import Base
from app.models.user import User
from app.core.security import hash_password
from app.models.chat import Chat
from app.models.message import Message


DB_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

@contextmanager
def session_scope() -> Session:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_session() -> Session:
    with session_scope() as s:
        yield s

def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with session_scope() as s:
        if not s.query(User).filter(User.username == "admin").first():
            s.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
        if not s.query(User).filter(User.username == "user").first():
            s.add(User(username="user", password_hash=hash_password("user"), role="user"))
