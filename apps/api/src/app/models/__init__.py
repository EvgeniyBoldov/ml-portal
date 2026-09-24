# Import all models to ensure they are registered with SQLAlchemy
from app.models.base import Base
from app.models.audit_log import AuditLog
from .user import Users
from .tenant import Tenants, UserTenants
from .chat import Chats, ChatMessages
from .chat_attachment import ChatAttachment
from .chat_artifact_reference import ChatArtifactReference
from .rag import RAGDocument, RAGChunk
from .rag_ingest import (
    Source, Chunk, EmbStatus, RAGStatus, DocumentCollectionMembership,
    RAGIngestRun, RAGIngestOutbox, RAGIngestStageRun, RAGIngestStageOutbox,
)
from .template_analysis_status import TemplateAnalysisStatus
from .model_registry import ModelRegistry
from .events import EventOutbox
from .prompt import Prompt, PromptVersion, PromptStatus
from .tool import Tool
from .tool_instance import ToolInstance, InstanceKind, InstancePlacement, InstanceDomain
from .tool_release import ToolBackendRelease, ToolRelease, ToolReleaseStatus
from .agent import Agent
from .agent_version import AgentVersion, AgentVersionStatus
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
from .policy import Policy
from .rbac import RbacRule, RbacLevel, ResourceType, RbacEffect
from .platform_settings import PlatformSettings
from .orchestration_settings import OrchestrationSettings
from .system_llm_role import SystemLLMRole, SystemLLMRoleType, RetryBackoffType
from .chat_summary import ChatSummary
from .chat_turn import ChatTurn
from .chat_memory import ChatMemoryItem
from .chat_context_head import ChatContextHead
from .sandbox import SandboxSession, SandboxOverride, SandboxRun
from .discovered_tool import DiscoveredTool
from .memory import Fact, FactScope, FactSource, DialogueSummary
from .memory import FactObservation, FactStatus, MemoryClaim, MemoryItem, MemoryItemSource, MemoryItemEvaluation, MemoryRelation
from .memory_scope import MemoryScope, MemoryCandidateScope, MemoryClaimScope, DocumentMemoryScope
from .project import Project
from .glossary import GlossaryEntry, GlossaryObservation, GlossaryScope, GlossaryStatus
from .knowledge_entity import KnowledgeEntity, KnowledgeEntitySource
from .document_memory_staging import (
    DocumentMemorySnapshot,
    MemoryExtractionCandidate,
    MemoryCandidateProjectBinding,
    GlossaryTerm,
    GlossaryMeaning,
    GlossaryMeaningProjectBinding,
    GlossaryMeaningSource,
    MemoryConflictCase,
    MemoryConflictMember,
    MemoryCandidateDecision,
)
from .execution_limit import (
    ActorExecutionLimit,
    ActorExecutionLimitScope,
    ExecutionLimit,
    ExecutionLimitScope,
    RuntimeExecutionLimits,
)
from .periodic_task import PeriodicTask
from .runtime_observability import RuntimeExecutionEvent, RuntimeEventSequence
from .runtime_plan import (
    RuntimeNeedBinding, RuntimePause, RuntimePlan, RuntimePlanIteration,
    RuntimePlanTask, RuntimeTaskAttempt, RuntimeToolResult, RuntimeTaskDependency, RuntimeTaskNeed,
    RuntimeTaskResolution,
)

__all__ = [
    "Base",
    "AuditLog",
    "Users",
    "Tenants",
    "UserTenants",
    "Chats",
    "ChatMessages",
    "ChatAttachment",
    "ChatArtifactReference",
    "RAGDocument",
    "RAGChunk",
    "Source",
    "Chunk",
    "EmbStatus",
    "RAGStatus",
    "DocumentCollectionMembership",
    "RAGIngestRun",
    "RAGIngestOutbox",
    "RAGIngestStageRun",
    "RAGIngestStageOutbox",
    "TemplateAnalysisStatus",
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
    "Policy",
    "RbacRule",
    "RbacLevel",
    "ResourceType",
    "RbacEffect",
    "PlatformSettings",
    "OrchestrationSettings",
    "SystemLLMRole",
    "SystemLLMRoleType", 
    "RetryBackoffType",
    "ChatSummary",
    "ChatTurn",
    "ChatMemoryItem",
    "ChatContextHead",
    "SandboxSession",
    "SandboxOverride",
    "SandboxRun",
    "DiscoveredTool",
    "Fact",
    "FactScope",
    "FactSource",
    "DialogueSummary",
    "FactObservation",
    "FactStatus",
    "MemoryItem",
    "MemoryClaim",
    "MemoryItemSource",
    "MemoryItemEvaluation",
    "MemoryRelation",
    "Project",
    "GlossaryEntry",
    "GlossaryObservation",
    "KnowledgeEntity",
    "KnowledgeEntitySource",
    "DocumentMemorySnapshot",
    "MemoryExtractionCandidate",
    "MemoryCandidateProjectBinding",
    "GlossaryTerm",
    "GlossaryMeaning",
    "GlossaryMeaningProjectBinding",
    "GlossaryMeaningSource",
    "MemoryConflictCase",
    "MemoryConflictMember",
    "MemoryCandidateDecision",
    "GlossaryScope",
    "GlossaryStatus",
    "ExecutionLimit",
    "ExecutionLimitScope",
    "ActorExecutionLimit",
    "ActorExecutionLimitScope",
    "RuntimeExecutionLimits",
    "PeriodicTask",
    "RuntimeExecutionEvent",
    "RuntimeEventSequence",
    "RuntimePlan",
    "RuntimePlanIteration",
    "RuntimePlanTask",
    "RuntimeTaskDependency",
    "RuntimeTaskNeed",
    "RuntimeNeedBinding",
    "RuntimeTaskResolution",
    "RuntimeTaskAttempt", "RuntimeToolResult",
    "RuntimePause",
]
