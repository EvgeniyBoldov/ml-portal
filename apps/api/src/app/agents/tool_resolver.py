"""Tool resolver.

Builds the runtime-facing tool view directly from discovered capability snapshots
with optional sandbox semantic overrides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.operation_publication import PublicationDecision, resolve_publication
from app.agents.tool_semantics import ToolSemantics, build_tool_semantics
from app.core.logging import get_logger
from app.models.discovered_tool import DiscoveredTool
from app.models.tool import Tool
from app.models.tool_instance import ToolInstance
from app.models.tool_release import ToolRelease

logger = get_logger(__name__)


@dataclass(slots=True)
class ToolPublicationContainerView:
    id: Optional[str]
    slug: str
    name: str
    domains: List[str] = field(default_factory=list)
    current_version_id: Optional[str] = None
    is_virtual: bool = False

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
class ToolPublicationReleaseView:
    id: Optional[str]
    version: Optional[int]
    status: str
    backend_release_id: Optional[str] = None
    is_virtual: bool = False
    semantic_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "status": self.status,
            "backend_release_id": self.backend_release_id,
            "is_virtual": self.is_virtual,
            "semantic_payload": dict(self.semantic_payload),
        }


@dataclass(slots=True)
class ToolPublicationView:
    state: Literal["draft", "published"]
    source_kind: Literal["real", "virtual", "hybrid"]
    container: ToolPublicationContainerView
    release: ToolPublicationReleaseView

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "source_kind": self.source_kind,
            "container": self.container.to_dict(),
            "release": self.release.to_dict(),
        }


@dataclass(slots=True)
class ResolvedTool:
    raw_slug: str
    operation_name: str
    published: bool
    semantics: ToolSemantics
    publication: Optional[PublicationDecision] = None
    publication_view: Optional[ToolPublicationView] = None
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None
    linked_tool_id: Optional[str] = None
    release_id: Optional[str] = None
    release_payload: Dict[str, Any] = field(default_factory=dict)
    prompt_context: Dict[str, Any] = field(default_factory=dict)

    def to_prompt_context(self) -> Dict[str, Any]:
        return {
            "raw_slug": self.raw_slug,
            "operation_name": self.operation_name,
            "published": self.published,
            "title": self.semantics.title,
            "description": self.semantics.description,
            "semantic_profile": self.semantics.semantic_profile,
            "policy_hints": self.semantics.policy_hints,
            "side_effects": self.semantics.side_effects,
            "risk_level": self.semantics.risk_level,
            "idempotent": self.semantics.idempotent,
            "requires_confirmation": self.semantics.requires_confirmation,
            "credential_scope": self.semantics.credential_scope,
            "risk_flags": list(self.semantics.risk_flags),
            "examples": list(self.semantics.examples),
            "quality": self.semantics.quality,
            "publication_view": self.publication_view.to_dict() if self.publication_view else None,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "linked_tool_id": self.linked_tool_id,
            "release_id": self.release_id,
            "release_payload": self.release_payload,
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
        publication_override: Optional[bool] = None,
        resolved_release_id: Optional[str] = None,
        runtime_override: Optional[Dict[str, Any]] = None,
        sandbox_mode: bool = False,
    ) -> Optional[ResolvedTool]:
        raw_operation_name = discovered_tool.slug
        _ = publication_override, resolved_release_id, sandbox_mode
        published = True

        linked_tool_id: Optional[str] = None
        effective_release_id: Optional[str] = None
        release_payload: Dict[str, Any] = {}
        release_view = self._build_virtual_release_view(
            discovered_tool=discovered_tool,
            instance=instance,
            runtime_domain=runtime_domain,
        )
        release_payload.update(release_view.semantic_payload)

        if isinstance(runtime_override, dict):
            release_payload.update(runtime_override)
            if release_view is not None:
                release_view.semantic_payload.update(runtime_override)

        semantics = build_tool_semantics(
            slug=raw_operation_name,
            source=discovered_tool.source,
            discovered_name=discovered_tool.name,
            discovered_description=discovered_tool.description,
            input_schema=discovered_tool.input_schema or {},
            domains=discovered_tool.domains or [],
            instance_slug=instance.slug,
            instance_domain=runtime_domain,
            instance_config=instance.config or {},
            provider_config=provider.config or {},
            draft_semantic_overrides=release_payload,
        )
        publication = resolve_publication(
            raw_slug=raw_operation_name,
            discovered_domains=discovered_tool.domains or [],
            context_domains=context_domains,
        )
        operation_name = publication.canonical_op_slug if publication else raw_operation_name
        publication_view = self._build_publication_view(
            discovered_tool=discovered_tool,
            linked_tool=None,
            release_view=release_view,
            publication_state="published",
        )

        return ResolvedTool(
            raw_slug=raw_operation_name,
            operation_name=operation_name,
            published=published,
            semantics=semantics,
            publication=publication,
            publication_view=publication_view,
            input_schema=discovered_tool.input_schema or {},
            output_schema=discovered_tool.output_schema,
            linked_tool_id=linked_tool_id,
            release_id=effective_release_id,
            release_payload=release_payload,
            prompt_context={
                "instance_slug": instance.slug,
                "provider_slug": provider.slug,
                "runtime_domain": runtime_domain,
            },
        )

    def _build_publication_view(
        self,
        *,
        discovered_tool: DiscoveredTool,
        linked_tool: Optional[Tool],
        release_view: ToolPublicationReleaseView,
        publication_state: Literal["draft", "published"],
    ) -> ToolPublicationView:
        if linked_tool is not None and not release_view.is_virtual:
            source_kind: Literal["real", "virtual", "hybrid"] = "real"
        elif linked_tool is None and release_view.is_virtual:
            source_kind = "virtual"
        else:
            source_kind = "hybrid"

        container = self._build_container_view(
            discovered_tool=discovered_tool,
            linked_tool=linked_tool,
            release_view=release_view,
        )
        return ToolPublicationView(
            state=publication_state,
            source_kind=source_kind,
            container=container,
            release=release_view,
        )

    def _build_container_view(
        self,
        *,
        discovered_tool: DiscoveredTool,
        linked_tool: Optional[Tool],
        release_view: ToolPublicationReleaseView,
    ) -> ToolPublicationContainerView:
        if linked_tool is not None:
            return ToolPublicationContainerView(
                id=str(linked_tool.id),
                slug=linked_tool.slug,
                name=linked_tool.name,
                domains=list(linked_tool.domains or []),
                current_version_id=str(linked_tool.current_version_id) if linked_tool.current_version_id is not None else None,
                is_virtual=False,
            )

        fallback_name = _build_title(discovered_tool.name, discovered_tool.slug)
        domains = list(discovered_tool.domains or [])
        if not domains and release_view.semantic_payload.get("runtime_domain"):
            domains = [str(release_view.semantic_payload["runtime_domain"])]
        return ToolPublicationContainerView(
            id=None,
            slug=discovered_tool.slug,
            name=fallback_name,
            domains=domains,
            current_version_id=release_view.id,
            is_virtual=True,
        )

    def _build_virtual_release_view(
        self,
        *,
        discovered_tool: DiscoveredTool,
        instance: ToolInstance,
        runtime_domain: str,
    ) -> ToolPublicationReleaseView:
        semantic_profile = {
            "summary": _build_description(
                slug=discovered_tool.slug,
                description=discovered_tool.description,
                side_effects="none",
                domains=discovered_tool.domains or [],
                instance_slug=instance.slug,
                instance_domain=runtime_domain,
            ),
            "when_to_use": "",
            "limitations": "",
            "examples": [],
        }
        semantic_payload: Dict[str, Any] = {
            "title": _build_title(discovered_tool.name, discovered_tool.slug),
            "semantic_profile": semantic_profile,
            "policy_hints": {
                "dos": [],
                "donts": [],
                "guardrails": [],
                "sensitive_inputs": [],
            },
        }
        semantic_payload["runtime_domain"] = runtime_domain
        return ToolPublicationReleaseView(
            id=None,
            version=None,
            status="draft",
            backend_release_id=None,
            is_virtual=True,
            semantic_payload=semantic_payload,
        )

    async def _load_release_view(
        self,
        *,
        release_id: str,
        expected_tool_id: Optional[str] = None,
    ) -> Optional[tuple[ToolPublicationReleaseView, Dict[str, Any]]]:
        try:
            release_uuid = UUID(str(release_id))
        except (TypeError, ValueError):
            return None

        result = await self.session.execute(
            select(ToolRelease, Tool)
            .join(Tool, Tool.id == ToolRelease.tool_id)
            .where(ToolRelease.id == release_uuid)
        )
        row = result.first()
        if row is None:
            return None

        release, tool = row
        if expected_tool_id and str(tool.id) != str(expected_tool_id):
            logger.warning(
                "sandbox_tool_release_id_tool_mismatch",
                extra={
                    "release_id": str(release.id),
                    "expected_tool_id": expected_tool_id,
                    "actual_tool_id": str(tool.id),
                },
            )
            return None

        payload: Dict[str, Any] = {}
        if tool.name:
            payload["title"] = tool.name
        semantic_profile = self._normalize_semantic_profile(getattr(release, "semantic_profile", None))
        policy_hints = self._normalize_policy_hints(getattr(release, "policy_hints", None))
        payload["semantic_profile"] = semantic_profile
        payload["policy_hints"] = policy_hints
        return (
            ToolPublicationReleaseView(
                id=str(release.id),
                version=release.version,
                status=release.status,
                backend_release_id=str(release.backend_release_id),
                is_virtual=False,
                semantic_payload=dict(payload),
            ),
            payload,
        )

    @staticmethod
    def _normalize_semantic_profile(value: Any) -> Dict[str, Any]:
        payload = value if isinstance(value, dict) else {}
        return {
            "summary": _clean_text(payload.get("summary") or payload.get("description")),
            "when_to_use": _clean_text(payload.get("when_to_use")),
            "limitations": _clean_text(payload.get("limitations")),
            "examples": _normalize_lines(payload.get("examples")),
        }

    @staticmethod
    def _normalize_policy_hints(value: Any) -> Dict[str, Any]:
        payload = value if isinstance(value, dict) else {}
        return {
            "dos": _normalize_lines(payload.get("dos")),
            "donts": _normalize_lines(payload.get("donts")),
            "guardrails": _normalize_lines(payload.get("guardrails")),
            "sensitive_inputs": _normalize_lines(payload.get("sensitive_inputs")),
        }


def _build_title(discovered_name: Optional[str], slug: str) -> str:
    if discovered_name and discovered_name.strip():
        return discovered_name.strip()
    leaf = (slug or "").split(".")[-1].replace("_", " ").strip()
    return leaf.title() if leaf else "Tool Operation"


def _build_description(
    *,
    slug: str,
    description: Optional[str],
    side_effects: str,
    domains: List[str],
    instance_slug: str,
    instance_domain: str,
) -> str:
    if description and description.strip():
        return description.strip()

    domains_txt = ", ".join(domains) if domains else instance_domain
    return (
        f"Operation '{slug}' for instance '{instance_slug}' "
        f"(domain: {domains_txt}, side_effects: {side_effects})."
    )


def _normalize_lines(value: Any) -> List[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.splitlines()
    else:
        items = []
    result: List[str] = []
    for item in items:
        text = _clean_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
