# Import all models to ensure they are registered with SQLAlchemy
from app.models.base import Base
from app.models.audit_log import AuditLog
from .user import Users
from .tenant import Tenants, UserTenants
from .chat import Chats, ChatMessages
from .chat_attachment import ChatAttachment
from .rag import RAGDocument, RAGChunk
from .rag_ingest import Source, Chunk, EmbStatus, RAGStatus
from .model_registry import ModelRegistry
from .events import EventOutbox
from .prompt import Prompt, PromptVersion, PromptStatus
from .tool import Tool
from .tool_instance import ToolInstance, InstanceKind, InstancePlacement, InstanceDomain
from .tool_release import ToolBackendRelease, ToolRelease, ToolReleaseStatus
from .agent import Agent
from .agent_version import AgentVersion, AgentVersionStatus
from .agent_run import AgentRun, AgentRunStep
from .api_key import APIKey
from .api_token import ApiToken
from .collection import (
    Collection,
    CollectionSchema,
    CollectionVersion,
    CollectionVersionStatus,
    CollectionType,
    CollectionStatus,
    FieldCategory,
    FieldType,
)
from .credential_set import Credential, AuthType
from .routing_log import RoutingLog
from .policy import Policy
from .limit import Limit, LimitVersion, LimitStatus
from .rbac import RbacRule, RbacLevel, ResourceType, RbacEffect
from .platform_settings import PlatformSettings
from .orchestration_settings import OrchestrationSettings
from .system_llm_role import SystemLLMRole, SystemLLMRoleType, RetryBackoffType
from .system_llm_trace import SystemLLMTrace, SystemLLMTraceType
from .plan import Plan, PlanStatus
from .chat_summary import ChatSummary
from .execution_memory import ExecutionMemory
from .chat_turn import ChatTurn
from .sandbox import SandboxSession, SandboxOverride, SandboxRun, SandboxRunStep
from .discovered_tool import DiscoveredTool

__all__ = [
    "Base",
    "AuditLog",
    "Users",
    "Tenants",
    "UserTenants",
    "Chats",
    "ChatMessages",
    "ChatAttachment",
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
    "Tool",
    "ToolInstance",
    "ToolBackendRelease",
    "ToolRelease",
    "ToolReleaseStatus",
    "Agent",
    "AgentVersion",
    "AgentVersionStatus",
    "AgentRun",
    "AgentRunStep",
    "APIKey",
    "ApiToken",
    "Collection",
    "CollectionSchema",
    "CollectionVersion",
    "CollectionVersionStatus",
    "CollectionType",
    "CollectionStatus",
    "FieldCategory",
    "FieldType",
    "Credential",
    "AuthType",
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
    "OrchestrationSettings",
    "SystemLLMRole",
    "SystemLLMRoleType", 
    "RetryBackoffType",
    "SystemLLMTrace",
    "SystemLLMTraceType",
    "Plan",
    "PlanStatus",
    "ChatSummary",
    "ExecutionMemory",
    "ChatTurn",
    "SandboxSession",
    "SandboxOverride",
    "SandboxRun",
    "SandboxRunStep",
    "DiscoveredTool",
]
