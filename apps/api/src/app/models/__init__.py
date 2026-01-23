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
from .api_token import ApiToken
from .collection import Collection, FieldType, SearchMode
from .tool_instance import ToolInstance, InstanceScope, HealthStatus
from .credential_set import CredentialSet, AuthType, CredentialScope
from .permission_set import PermissionSet, PermissionScope
from .routing_log import RoutingLog

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
    "ApiToken",
    "Collection",
    "FieldType",
    "SearchMode",
    "ToolInstance",
    "InstanceScope",
    "HealthStatus",
    "CredentialSet",
    "AuthType",
    "CredentialScope",
    "PermissionSet",
    "PermissionScope",
    "RoutingLog",
]
