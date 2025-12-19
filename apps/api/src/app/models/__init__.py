# Import all models to ensure they are registered with SQLAlchemy
from app.models.base import Base
from app.models.audit_log import AuditLog
from .user import Users
from .tenant import Tenants, UserTenants
from .chat import Chats, ChatMessages
from .rag import RAGDocument, RAGChunk
from .rag_ingest import Source, Chunk, EmbStatus, RAGStatus
from .model_registry import ModelRegistry
from .events import EventOutbox
from .prompt import Prompt
from .tool import Tool
from .agent import Agent
from .agent_run import AgentRun, AgentRunStep
from .api_key import APIKey

__all__ = [
    "Base",
    "AuditLog",
    "Users",
    "Tenants",
    "UserTenants",
    "Chats",
    "ChatMessages",
    "RAGDocument",
    "RAGChunk",
    "Source",
    "Chunk",
    "EmbStatus",
    "RAGStatus",
    "ModelRegistry",
    "EventOutbox",
    "Prompt",
    "Tool",
    "Agent",
    "AgentRun",
    "AgentRunStep",
    "APIKey",
]
