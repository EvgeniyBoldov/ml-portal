from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.chats import router as chats_router
from app.routers.rag import router as rag_router
from app.routers.docs import router as docs_router
from app.core.auth import router as auth_router
from app.db import init_db

app = FastAPI(title="GPT backend", version="0.1.0")

# CORS (при необходимости настроим домены фронта)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры по направлениям
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(chats_router, prefix="/chats", tags=["chats"])
app.include_router(docs_router, prefix="/docs", tags=["docs"])
app.include_router(rag_router, prefix="/rag", tags=["rag"])

@app.on_event("startup")
def _startup() -> None:
    # создаем таблицы и сидируем пользователей при старте
    init_db()


@app.get("/health", tags=["service"])
def healthcheck():
    return {"status": "ok", "service": "GPT"}
