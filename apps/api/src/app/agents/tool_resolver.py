"""Tool resolver.

Translates a DiscoveredTool (raw MCP/local capability snapshot) into a
runtime-ready ResolvedTool. The MCP-published schema is the single source
of truth; there is no separate semantic layer on top of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from app.agents.mcp_discovery import parse_discovered_operation
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.operation_publication import PublicationDecision, resolve_publication
from app.core.logging import get_logger
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance

logger = get_logger(__name__)


@dataclass(slots=True)
class ToolPublicationContainerView:
    id: Optional[str]
    slug: str
    name: str
    domains: List[str] = field(default_factory=list)
    current_version_id: Optional[str] = None
    is_virtual: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "domains": list(self.domains),
            "current_version_id": self.current_version_id,
            "is_virtual": self.is_virtual,
        }


@dataclass(slots=True)
class ToolPublicationView:
    state: Literal["draft", "published"]
    source_kind: Literal["real", "virtual"]
    container: ToolPublicationContainerView

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "source_kind": self.source_kind,
            "container": self.container.to_dict(),
        }


@dataclass(slots=True)
class ResolvedTool:
    raw_slug: str
    operation_name: str
    published: bool
    title: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]]
    # Runtime metadata defaults are sourced from MCP schema extension x-runtime.
    side_effects: bool = False
    risk_level: Literal["safe", "write", "destructive"] = "safe"
    idempotent: bool = True
    requires_confirmation: bool = False
    credential_scope: Literal["platform", "user", "auto"] = "auto"
    risk_flags: List[str] = field(default_factory=list)
    publication: Optional[PublicationDecision] = None
    publication_view: Optional[ToolPublicationView] = None
    prompt_context: Dict[str, Any] = field(default_factory=dict)

    def to_prompt_context(self) -> Dict[str, Any]:
        return {
            "raw_slug": self.raw_slug,
            "operation_name": self.operation_name,
            "published": self.published,
            "title": self.title,
            "description": self.description,
            "side_effects": self.side_effects,
            "risk_level": self.risk_level,
            "idempotent": self.idempotent,
            "requires_confirmation": self.requires_confirmation,
            "credential_scope": self.credential_scope,
            "risk_flags": list(self.risk_flags),
            "publication_view": self.publication_view.to_dict() if self.publication_view else None,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            **self.prompt_context,
        }


class ToolResolver:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(
        self,
        *,
        discovered_tool: DiscoveredTool,
        instance: ToolInstance,
        provider: ToolInstance,
        runtime_domain: str,
        context_domains: Optional[List[str]] = None,
    ) -> Optional[ResolvedTool]:
        raw_operation_name = discovered_tool.slug
        publication = resolve_publication(
            raw_slug=raw_operation_name,
            discovered_domains=discovered_tool.domains or [],
            context_domains=context_domains,
        )
        operation_name = publication.canonical_op_slug if publication else raw_operation_name
        title = _build_title(discovered_tool.name, discovered_tool.slug)
        description = _build_description(
            slug=discovered_tool.slug,
            description=discovered_tool.description,
            domains=discovered_tool.domains or [],
            instance_slug=instance.slug,
            instance_domain=runtime_domain,
        )
        container = ToolPublicationContainerView(
            id=None,
            slug=discovered_tool.slug,
            name=title,
            domains=list(discovered_tool.domains or []) or [runtime_domain],
            current_version_id=None,
            is_virtual=True,
        )
        publication_view = ToolPublicationView(
            state="published",
            source_kind="virtual",
            container=container,
        )
        discovered_operation = parse_discovered_operation(
            tool_name=discovered_tool.slug,
            description=discovered_tool.description,
            input_schema=discovered_tool.input_schema,
            output_schema=discovered_tool.output_schema,
        )
        return ResolvedTool(
            raw_slug=raw_operation_name,
            operation_name=operation_name,
            published=True,
            title=title,
            description=description,
            input_schema=discovered_operation.input_schema,
            output_schema=discovered_operation.output_schema,
            risk_level=discovered_operation.risk_level,
            side_effects=discovered_operation.side_effects,
            requires_confirmation=discovered_operation.requires_confirmation,
            credential_scope=discovered_operation.credential_scope,
            publication=publication,
            publication_view=publication_view,
            prompt_context={
                "instance_slug": instance.slug,
                "provider_slug": provider.slug,
                "runtime_domain": runtime_domain,
            },
        )


def _build_title(discovered_name: Optional[str], slug: str) -> str:
    if discovered_name and discovered_name.strip():
        return discovered_name.strip()
    leaf = (slug or "").split(".")[-1].replace("_", " ").strip()
    return leaf.title() if leaf else "Tool Operation"


def _build_description(
    *,
    slug: str,
    description: Optional[str],
    domains: List[str],
    instance_slug: str,
    instance_domain: str,
) -> str:
    if description and description.strip():
        return description.strip()
    domains_txt = ", ".join(domains) if domains else instance_domain
    return (
        f"Operation '{slug}' for instance '{instance_slug}' "
        f"(domain: {domains_txt})."
    )
