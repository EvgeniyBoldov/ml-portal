from .base import Base
from .user import Users, UserTokens, UserRefreshTokens
from .chat import Chats, ChatMessages
from .rag import RAGDocument, RAGChunk
from .analyze import AnalysisDocuments, AnalysisChunks

# Создаем алиасы для совместимости с тестами
User = Users
Chat = Chats
ChatMessage = ChatMessages
RagDocuments = RAGDocument
RagChunks = RAGChunk

__all__ = [
    "Base", "Users", "UserTokens", "UserRefreshTokens", "Chats", "ChatMessages",
    "RAGDocument", "RAGChunk", "AnalysisDocuments", "AnalysisChunks",
    "User", "Chat", "ChatMessage", "RagDocuments", "RagChunks"
]
