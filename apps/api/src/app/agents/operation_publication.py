from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, Optional, Tuple


@dataclass(frozen=True, slots=True)
class OperationSpec:
    canonical_op_slug: str
    domain: str
    title: str
    description: str
    result_kind: str


@dataclass(frozen=True, slots=True)
class PublicationRule:
    instance_domain: str
    raw_tool_slug: str
    canonical_op_slug: str


@dataclass(frozen=True, slots=True)
class PublicationDecision:
    canonical_op_slug: str
    spec: OperationSpec


_OPERATION_SPECS: Dict[str, OperationSpec] = {
    "sql.execute_sql": OperationSpec(
        canonical_op_slug="sql.execute_sql",
        domain="sql",
        title="SQL Execute",
        description="Execute read-only SQL against curated external database",
        result_kind="rows",
    ),
    "sql.search_objects": OperationSpec(
        canonical_op_slug="sql.search_objects",
        domain="sql",
        title="SQL Search Objects",
        description="Search available schemas, tables, columns, and views in external database",
        result_kind="schema_search",
    ),
    "collection.table.search": OperationSpec(
        canonical_op_slug="collection.table.search",
        domain="collection.table",
        title="Table Search",
        description="Filter and retrieve records from table collection",
        result_kind="rows",
    ),
    "collection.table.aggregate": OperationSpec(
        canonical_op_slug="collection.table.aggregate",
        domain="collection.table",
        title="Table Aggregate",
        description="Compute grouped metrics over table collection",
        result_kind="aggregation",
    ),
    "collection.table.get": OperationSpec(
        canonical_op_slug="collection.table.get",
        domain="collection.table",
        title="Table Get",
        description="Read a single table record by id",
        result_kind="row",
    ),
    "collection.table.catalog_inspect": OperationSpec(
        canonical_op_slug="collection.table.catalog_inspect",
        domain="collection.table",
        title="Table Catalog Inspect",
        description="Inspect table collection schema and metadata dimensions",
        result_kind="catalog",
    ),
    "collection.document.catalog_inspect": OperationSpec(
        canonical_op_slug="collection.document.catalog_inspect",
        domain="collection.document",
        title="Document Catalog Inspect",
        description="Inspect document collection schema and metadata dimensions",
        result_kind="catalog",
    ),
    "collection.sql.catalog_inspect": OperationSpec(
        canonical_op_slug="collection.sql.catalog_inspect",
        domain="collection.sql",
        title="SQL Catalog Inspect",
        description="Inspect remote SQL collection catalog (schemas/tables/fields)",
        result_kind="catalog",
    ),
    "collection.api.catalog_inspect": OperationSpec(
        canonical_op_slug="collection.api.catalog_inspect",
        domain="collection.api",
        title="API Catalog Inspect",
        description="Inspect API collection catalog (entities/aliases/examples and schema hints)",
        result_kind="catalog",
    ),
    "collection.api.get_device": OperationSpec(
        canonical_op_slug="collection.api.get_device",
        domain="collection.api",
        title="Get Device",
        description="Get a single device by name from NetBox DCIM inventory",
        result_kind="row",
    ),
    "collection.api.search_devices": OperationSpec(
        canonical_op_slug="collection.api.search_devices",
        domain="collection.api",
        title="Search Devices",
        description="Search NetBox devices by query string (name, role, site, etc.)",
        result_kind="rows",
    ),
    "collection.api.list_sites": OperationSpec(
        canonical_op_slug="collection.api.list_sites",
        domain="collection.api",
        title="List Sites",
        description="List all sites in NetBox DCIM (locations/datacenters)",
        result_kind="rows",
    ),
    "collection.api.get_objects": OperationSpec(
        canonical_op_slug="collection.api.get_objects",
        domain="collection.api",
        title="Get Objects",
        description="Get objects from NetBox by type (dcim.device, ipam.prefix, dcim.rack, etc.) with optional filters",
        result_kind="rows",
    ),
    "collection.api.search_objects": OperationSpec(
        canonical_op_slug="collection.api.search_objects",
        domain="collection.api",
        title="Search Objects",
        description="Search NetBox objects across multiple types by query string",
        result_kind="rows",
    ),
    "collection.sql.execute": OperationSpec(
        canonical_op_slug="collection.sql.execute",
        domain="collection.sql",
        title="SQL Execute",
        description="Execute read-only SQL against the collection's remote database",
        result_kind="rows",
    ),
    "collection.sql.search_objects": OperationSpec(
        canonical_op_slug="collection.sql.search_objects",
        domain="collection.sql",
        title="SQL Search Objects",
        description="Search available schemas, tables, columns in the collection's remote database",
        result_kind="schema_search",
    ),
    "collection.document.search": OperationSpec(
        canonical_op_slug="collection.document.search",
        domain="collection.document",
        title="Document Search",
        description="Search documents and return relevant document results",
        result_kind="documents",
    ),
}

# Planner/LLM-facing retrieval operations.
# Raw builtin tool slugs (collection.doc_search / collection.search / collection.text_search)
# are adapter-level implementation details and must not leak into prompts.
PUBLIC_RETRIEVAL_OPERATIONS: tuple[str, ...] = (
    "collection.document.search",
    "collection.table.search",
)

_PUBLICATION_RULES: tuple[PublicationRule, ...] = (
    PublicationRule(
        instance_domain="sql",
        raw_tool_slug="execute_sql",
        canonical_op_slug="sql.execute_sql",
    ),
    PublicationRule(
        instance_domain="sql",
        raw_tool_slug="sql.execute_sql",
        canonical_op_slug="sql.execute_sql",
    ),
    PublicationRule(
        instance_domain="sql",
        raw_tool_slug="search_objects",
        canonical_op_slug="sql.search_objects",
    ),
    PublicationRule(
        instance_domain="sql",
        raw_tool_slug="sql.search_objects",
        canonical_op_slug="sql.search_objects",
    ),
    PublicationRule(
        instance_domain="collection.table",
        raw_tool_slug="collection.search",
        canonical_op_slug="collection.table.search",
    ),
    PublicationRule(
        instance_domain="collection.table",
        raw_tool_slug="collection.aggregate",
        canonical_op_slug="collection.table.aggregate",
    ),
    PublicationRule(
        instance_domain="collection.table",
        raw_tool_slug="collection.get",
        canonical_op_slug="collection.table.get",
    ),
    PublicationRule(
        instance_domain="collection.table",
        raw_tool_slug="collection.table.search",
        canonical_op_slug="collection.table.search",
    ),
    PublicationRule(
        instance_domain="collection.table",
        raw_tool_slug="collection.table.aggregate",
        canonical_op_slug="collection.table.aggregate",
    ),
    PublicationRule(
        instance_domain="collection.table",
        raw_tool_slug="collection.table.get",
        canonical_op_slug="collection.table.get",
    ),
    PublicationRule(
        instance_domain="collection.table",
        raw_tool_slug="collection.catalog",
        canonical_op_slug="collection.table.catalog_inspect",
    ),
    PublicationRule(
        instance_domain="collection.table",
        raw_tool_slug="collection.table.catalog_inspect",
        canonical_op_slug="collection.table.catalog_inspect",
    ),
    PublicationRule(
        instance_domain="collection.document",
        raw_tool_slug="collection.doc_search",
        canonical_op_slug="collection.document.search",
    ),
    PublicationRule(
        instance_domain="collection.document",
        raw_tool_slug="collection.document.search",
        canonical_op_slug="collection.document.search",
    ),
    PublicationRule(
        instance_domain="collection.document",
        raw_tool_slug="collection.catalog",
        canonical_op_slug="collection.document.catalog_inspect",
    ),
    PublicationRule(
        instance_domain="collection.document",
        raw_tool_slug="collection.document.catalog_inspect",
        canonical_op_slug="collection.document.catalog_inspect",
    ),
    PublicationRule(
        instance_domain="collection.sql",
        raw_tool_slug="collection.catalog",
        canonical_op_slug="collection.sql.catalog_inspect",
    ),
    PublicationRule(
        instance_domain="collection.sql",
        raw_tool_slug="collection.sql.catalog_inspect",
        canonical_op_slug="collection.sql.catalog_inspect",
    ),
    PublicationRule(
        instance_domain="collection.api",
        raw_tool_slug="collection.catalog",
        canonical_op_slug="collection.api.catalog_inspect",
    ),
    PublicationRule(
        instance_domain="collection.api",
        raw_tool_slug="collection.api.catalog_inspect",
        canonical_op_slug="collection.api.catalog_inspect",
    ),
    PublicationRule(
        instance_domain="collection.api",
        raw_tool_slug="netbox_get_device",
        canonical_op_slug="collection.api.get_device",
    ),
    PublicationRule(
        instance_domain="collection.api",
        raw_tool_slug="netbox_search_devices",
        canonical_op_slug="collection.api.search_devices",
    ),
    PublicationRule(
        instance_domain="collection.api",
        raw_tool_slug="netbox_list_sites",
        canonical_op_slug="collection.api.list_sites",
    ),
    PublicationRule(
        instance_domain="collection.api",
        raw_tool_slug="netbox_get_objects",
        canonical_op_slug="collection.api.get_objects",
    ),
    PublicationRule(
        instance_domain="collection.api",
        raw_tool_slug="netbox_search_objects",
        canonical_op_slug="collection.api.search_objects",
    ),
    PublicationRule(
        instance_domain="sql",
        raw_tool_slug="collection.catalog",
        canonical_op_slug="collection.sql.catalog_inspect",
    ),
    PublicationRule(
        instance_domain="collection.sql",
        raw_tool_slug="execute_sql",
        canonical_op_slug="collection.sql.execute",
    ),
    PublicationRule(
        instance_domain="collection.sql",
        raw_tool_slug="sql.execute_sql",
        canonical_op_slug="collection.sql.execute",
    ),
    PublicationRule(
        instance_domain="collection.sql",
        raw_tool_slug="search_objects",
        canonical_op_slug="collection.sql.search_objects",
    ),
    PublicationRule(
        instance_domain="collection.sql",
        raw_tool_slug="sql.search_objects",
        canonical_op_slug="collection.sql.search_objects",
    ),
)

_RULE_MAP: Dict[Tuple[str, str], str] = {
    (rule.instance_domain, rule.raw_tool_slug): rule.canonical_op_slug
    for rule in _PUBLICATION_RULES
}
_DOMAIN_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def canonical_operation_name(instance_domain: str, raw_slug: str) -> str:
    decision = resolve_publication(
        raw_slug=raw_slug,
        context_domains=[instance_domain] if instance_domain else None,
    )
    if decision:
        return decision.canonical_op_slug
    return raw_slug


def resolve_publication(
    *,
    raw_slug: str,
    discovered_domains: Optional[Iterable[str]] = None,
    context_domains: Optional[Iterable[str]] = None,
    instance_domain: Optional[str] = None,
) -> Optional[PublicationDecision]:
    normalized_raw = str(raw_slug or "").strip()
    if not normalized_raw:
        return None

    candidate_domains = _build_domain_candidates(
        context_domains=context_domains,
        discovered_domains=discovered_domains,
        fallback_domain=instance_domain or "",
    )

    direct_spec = _OPERATION_SPECS.get(normalized_raw)
    if direct_spec and _is_domain_allowed(
        op_domain=direct_spec.domain,
        candidate_domains=candidate_domains,
    ):
        return PublicationDecision(
            canonical_op_slug=normalized_raw,
            spec=direct_spec,
        )

    for candidate_domain in candidate_domains:
        canonical = _RULE_MAP.get((candidate_domain, normalized_raw))
        if canonical:
            spec = _OPERATION_SPECS.get(canonical)
            if spec:
                return PublicationDecision(canonical_op_slug=canonical, spec=spec)

    if _is_collection_like_raw(normalized_raw):
        return None

    canonical_non_collection = _resolve_non_collection_canonical(
        raw_slug=normalized_raw,
        candidate_domains=candidate_domains,
    )
    if canonical_non_collection:
        domain = canonical_non_collection.split(".", 1)[0]
        return PublicationDecision(
            canonical_op_slug=canonical_non_collection,
            spec=OperationSpec(
                canonical_op_slug=canonical_non_collection,
                domain=domain,
                title=canonical_non_collection,
                description=f"Published operation for domain '{domain}'",
                result_kind="generic",
            ),
        )
    return None


def _build_domain_candidates(
    *,
    context_domains: Optional[Iterable[str]],
    discovered_domains: Optional[Iterable[str]],
    fallback_domain: str,
) -> tuple[str, ...]:
    normalized: list[str] = []
    for domain_set in (context_domains, discovered_domains):
        for raw in domain_set or ():
            domain = str(raw or "").strip()
            if not domain:
                continue
            if domain in normalized:
                continue
            normalized.append(domain)

    fallback = str(fallback_domain or "").strip()
    if fallback and fallback not in normalized:
        normalized.append(fallback)
    return tuple(normalized)


def _resolve_non_collection_canonical(
    *,
    raw_slug: str,
    candidate_domains: tuple[str, ...],
) -> Optional[str]:
    if "." in raw_slug:
        prefix, _, suffix = raw_slug.partition(".")
        if (
            _DOMAIN_SEGMENT_RE.match(prefix)
            and suffix
            and prefix != "collection"
            and _is_domain_allowed(prefix, candidate_domains)
        ):
            return raw_slug

    if "_" in raw_slug:
        prefix, _, suffix = raw_slug.partition("_")
        if (
            _DOMAIN_SEGMENT_RE.match(prefix)
            and suffix
            and prefix != "collection"
            and _is_domain_allowed(prefix, candidate_domains)
        ):
            return f"{prefix}.{suffix}"

    for candidate_domain in candidate_domains:
        if candidate_domain.startswith("collection."):
            continue
        if not _DOMAIN_SEGMENT_RE.match(candidate_domain):
            continue
        domain_prefix_dot = f"{candidate_domain}."
        if raw_slug.startswith(domain_prefix_dot):
            return raw_slug
        domain_prefix_us = f"{candidate_domain}_"
        if raw_slug.startswith(domain_prefix_us):
            suffix = raw_slug[len(domain_prefix_us) :]
            if suffix:
                return f"{candidate_domain}.{suffix}"
    return None


def _is_domain_allowed(op_domain: str, candidate_domains: tuple[str, ...]) -> bool:
    if not candidate_domains:
        return True
    return op_domain in candidate_domains


def _is_collection_like_raw(raw_slug: str) -> bool:
    return raw_slug.startswith("collection.") or raw_slug.startswith("collection_")


def build_runtime_operation_slug(instance_slug: str, canonical_name: str) -> str:
    return f"instance.{instance_slug}.{canonical_name}"


def canonical_operation_identity(
    *,
    instance_slug: str,
    instance_domain: str,
    raw_slug: str,
) -> Tuple[str, str]:
    canonical_name = canonical_operation_name(instance_domain, raw_slug)
    return canonical_name, build_runtime_operation_slug(instance_slug, canonical_name)
