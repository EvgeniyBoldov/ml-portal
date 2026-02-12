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
from .prompt import Prompt, PromptVersion, PromptStatus
# Baseline removed in refactor/policy-limits
from .tool_group import ToolGroup
from .tool import Tool
from .tool_instance import ToolInstance, InstanceType
from .tool_release import ToolBackendRelease, ToolRelease, ToolReleaseStatus
from .agent import Agent
from .agent_version import AgentVersion, AgentVersionStatus
from .agent_binding import AgentBinding, CredentialStrategy
from .agent_run import AgentRun, AgentRunStep
from .api_key import APIKey
from .api_token import ApiToken
from .collection import Collection, FieldType, SearchMode
from .tool import ToolKind
from .credential_set import Credential, AuthType
from .permission_set import PermissionSet, PermissionScope, PermissionValue
from .routing_log import RoutingLog
from .policy import Policy
from .limit import Limit, LimitVersion, LimitStatus
from .rbac import RbacRule, RbacLevel, ResourceType, RbacEffect
from .platform_settings import PlatformSettings

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
    "PromptVersion",
    "PromptStatus",
    "ToolGroup",
    "Tool",
    "ToolInstance",
    "InstanceType",
    "ToolBackendRelease",
    "ToolRelease",
    "ToolReleaseStatus",
    "Agent",
    "AgentVersion",
    "AgentVersionStatus",
    "AgentBinding",
    "CredentialStrategy",
    "AgentRun",
    "AgentRunStep",
    "APIKey",
    "ApiToken",
    "Collection",
    "FieldType",
    "SearchMode",
    "ToolKind",
    "Credential",
    "AuthType",
    "PermissionSet",
    "PermissionScope",
    "PermissionValue",
    "RoutingLog",
    "Policy",
    "Limit",
    "LimitVersion",
    "LimitStatus",
    "RbacRule",
    "RbacLevel",
    "ResourceType",
    "RbacEffect",
    "PlatformSettings",
]
