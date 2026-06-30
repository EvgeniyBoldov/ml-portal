from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Optional, Tuple, Literal


@dataclass(frozen=True, slots=True)
class OperationSpec:
    canonical_op_slug: str
    domain: str
    title: str
    description: str
    result_kind: str
    scope_kind: str
    collection_types: Tuple[str, ...] = ()
    requires_collection_binding: bool = False
    requires_vector_search: bool = False

    def to_publication_decision(self) -> "PublicationDecision":
        return PublicationDecision(canonical_op_slug=self.canonical_op_slug, spec=self)


@dataclass(frozen=True, slots=True)
class PublicationRule:
    instance_domain: str
    raw_tool_slug: str
    canonical_op_slug: str


@dataclass(frozen=True, slots=True)
class PublicationDecision:
    canonical_op_slug: str
    spec: OperationSpec

    @property
    def scope_kind(self) -> str:
        return self.spec.scope_kind


@dataclass(frozen=True, slots=True)
class CollectionCapabilityBinding:
    canonical_op_slug: str
    raw_tool_slugs: Tuple[str, ...]
    source: Literal["local", "mcp", "any"] = "any"


_OPERATION_SPECS: Dict[str, OperationSpec] = {
    "collection.info": OperationSpec(
        canonical_op_slug="collection.info",
        domain="collection",
        title="Collection Info",
        description="Inspect the bound collection schema, metadata, filterable fields, and observed values",
        result_kind="catalog",
        scope_kind="collection",
        collection_types=("table", "document", "template", "sql", "api"),
        requires_collection_binding=True,
    ),
    "sql.execute_sql": OperationSpec(
        canonical_op_slug="sql.execute_sql",
        domain="sql",
        title="SQL Execute",
        description="Execute read-only SQL against curated external database",
        result_kind="rows",
        scope_kind="system",
    ),
    "sql.search_objects": OperationSpec(
        canonical_op_slug="sql.search_objects",
        domain="sql",
        title="SQL Search Objects",
        description="Search available schemas, tables, columns, and views in external database",
        result_kind="schema_search",
        scope_kind="system",
    ),
    "collection.table.search": OperationSpec(
        canonical_op_slug="collection.table.search",
        domain="collection.table",
        title="Table Search",
        description="Filter and retrieve records from table collection",
        result_kind="rows",
        scope_kind="collection",
        collection_types=("table",),
        requires_collection_binding=True,
    ),
    "collection.table.aggregate": OperationSpec(
        canonical_op_slug="collection.table.aggregate",
        domain="collection.table",
        title="Table Aggregate",
        description="Compute grouped metrics over table collection",
        result_kind="aggregation",
        scope_kind="collection",
        collection_types=("table",),
        requires_collection_binding=True,
    ),
    "collection.table.get": OperationSpec(
        canonical_op_slug="collection.table.get",
        domain="collection.table",
        title="Table Get",
        description="Read a single table record by id",
        result_kind="row",
        scope_kind="collection",
        collection_types=("table",),
        requires_collection_binding=True,
    ),
    "collection.api.get_device": OperationSpec(
        canonical_op_slug="collection.api.get_device",
        domain="collection.api",
        title="Get Device",
        description="Get a single device by name from NetBox DCIM inventory",
        result_kind="row",
        scope_kind="collection",
        collection_types=("api",),
        requires_collection_binding=True,
    ),
    "collection.api.search_devices": OperationSpec(
        canonical_op_slug="collection.api.search_devices",
        domain="collection.api",
        title="Search Devices",
        description="Search NetBox devices by query string (name, role, site, etc.)",
        result_kind="rows",
        scope_kind="collection",
        collection_types=("api",),
        requires_collection_binding=True,
    ),
    "collection.api.list_sites": OperationSpec(
        canonical_op_slug="collection.api.list_sites",
        domain="collection.api",
        title="List Sites",
        description="List all sites in NetBox DCIM (locations/datacenters)",
        result_kind="rows",
        scope_kind="collection",
        collection_types=("api",),
        requires_collection_binding=True,
    ),
    "collection.api.get_objects": OperationSpec(
        canonical_op_slug="collection.api.get_objects",
        domain="collection.api",
        title="Get Objects",
        description="Get objects from NetBox by type (dcim.device, ipam.prefix, dcim.rack, etc.) with optional filters",
        result_kind="rows",
        scope_kind="collection",
        collection_types=("api",),
        requires_collection_binding=True,
    ),
    "collection.api.search_objects": OperationSpec(
        canonical_op_slug="collection.api.search_objects",
        domain="collection.api",
        title="Search Objects",
        description="Search NetBox objects across multiple types by query string",
        result_kind="rows",
        scope_kind="collection",
        collection_types=("api",),
        requires_collection_binding=True,
    ),
    "collection.sql.execute": OperationSpec(
        canonical_op_slug="collection.sql.execute",
        domain="collection.sql",
        title="SQL Execute",
        description="Execute read-only SQL against the collection's remote database",
        result_kind="rows",
        scope_kind="collection",
        collection_types=("sql",),
        requires_collection_binding=True,
    ),
    "collection.sql.search_objects": OperationSpec(
        canonical_op_slug="collection.sql.search_objects",
        domain="collection.sql",
        title="SQL Search Objects",
        description="Search available schemas, tables, columns in the collection's remote database",
        result_kind="schema_search",
        scope_kind="collection",
        collection_types=("sql",),
        requires_collection_binding=True,
    ),
    "collection.document.search": OperationSpec(
        canonical_op_slug="collection.document.search",
        domain="collection.document",
        title="Document Search",
        description="Search documents and return relevant document results",
        result_kind="documents",
        scope_kind="collection",
        collection_types=("document",),
        requires_collection_binding=True,
        requires_vector_search=True,
    ),
    "collection.document.list": OperationSpec(
        canonical_op_slug="collection.document.list",
        domain="collection.document",
        title="List Documents",
        description="List files in a document collection with metadata and file_ids",
        result_kind="rows",
        scope_kind="collection",
        collection_types=("document",),
        requires_collection_binding=True,
    ),
    "collection.document.get": OperationSpec(
        canonical_op_slug="collection.document.get",
        domain="collection.document",
        title="Get Document",
        description="Get a single document's metadata and file_id by document_id",
        result_kind="row",
        scope_kind="collection",
        collection_types=("document",),
        requires_collection_binding=True,
    ),
    "collection.template.list": OperationSpec(
        canonical_op_slug="collection.template.list",
        domain="collection.template",
        title="List Templates",
        description="List templates in a template collection with metadata",
        result_kind="rows",
        scope_kind="collection",
        collection_types=("template",),
        requires_collection_binding=True,
    ),
    "collection.template.search": OperationSpec(
        canonical_op_slug="collection.template.search",
        domain="collection.template",
        title="Search Templates",
        description="Semantic search over templates in a template collection by template description",
        result_kind="rows",
        scope_kind="collection",
        collection_types=("template",),
        requires_collection_binding=True,
        requires_vector_search=True,
    ),
    "collection.template.get_schema": OperationSpec(
        canonical_op_slug="collection.template.get_schema",
        domain="collection.template",
        title="Get Template Schema",
        description="Retrieve the fillable schema for a template row",
        result_kind="schema",
        scope_kind="collection",
        collection_types=("template",),
        requires_collection_binding=True,
    ),
    "collection.template.fill": OperationSpec(
        canonical_op_slug="collection.template.fill",
        domain="collection.template",
        title="Fill Template",
        description="Fill a template with values and return a generated file",
        result_kind="file",
        scope_kind="collection",
        collection_types=("template",),
        requires_collection_binding=True,
    ),
}

# Planner/LLM-facing retrieval operations.
# Raw builtin tool slugs are adapter-level implementation details and must not leak into prompts.
PUBLIC_RETRIEVAL_OPERATIONS: tuple[str, ...] = (
    "collection.document.search",
    "collection.table.search",
    "collection.template.search",
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
        raw_tool_slug="collection.info",
        canonical_op_slug="collection.info",
    ),
    PublicationRule(
        instance_domain="collection.document",
        raw_tool_slug="collection.info",
        canonical_op_slug="collection.info",
    ),
    PublicationRule(
        instance_domain="collection.template",
        raw_tool_slug="collection.info",
        canonical_op_slug="collection.info",
    ),
    PublicationRule(
        instance_domain="collection.sql",
        raw_tool_slug="collection.info",
        canonical_op_slug="collection.info",
    ),
    PublicationRule(
        instance_domain="collection.api",
        raw_tool_slug="collection.info",
        canonical_op_slug="collection.info",
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
        raw_tool_slug="collection.list_documents",
        canonical_op_slug="collection.document.list",
    ),
    PublicationRule(
        instance_domain="collection.document",
        raw_tool_slug="collection.get_document",
        canonical_op_slug="collection.document.get",
    ),
    PublicationRule(
        instance_domain="collection.template",
        raw_tool_slug="collection.template.list",
        canonical_op_slug="collection.template.list",
    ),
    PublicationRule(
        instance_domain="collection.template",
        raw_tool_slug="collection.template.search",
        canonical_op_slug="collection.template.search",
    ),
    PublicationRule(
        instance_domain="collection.template",
        raw_tool_slug="collection.template.get_schema",
        canonical_op_slug="collection.template.get_schema",
    ),
    PublicationRule(
        instance_domain="collection.template",
        raw_tool_slug="collection.template.fill",
        canonical_op_slug="collection.template.fill",
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

_COLLECTION_CAPABILITY_BINDINGS: Dict[str, Tuple[CollectionCapabilityBinding, ...]] = {
    "document": (
        CollectionCapabilityBinding("collection.info", ("collection.info",), source="local"),
        CollectionCapabilityBinding("collection.document.search", ("collection.document.search", "collection.doc_search")),
        CollectionCapabilityBinding("collection.document.list", ("collection.list_documents",)),
        CollectionCapabilityBinding("collection.document.get", ("collection.get_document",)),
    ),
    "table": (
        CollectionCapabilityBinding("collection.info", ("collection.info",), source="local"),
        CollectionCapabilityBinding("collection.table.search", ("collection.table.search", "collection.search")),
        CollectionCapabilityBinding("collection.table.aggregate", ("collection.table.aggregate", "collection.aggregate")),
        CollectionCapabilityBinding("collection.table.get", ("collection.table.get", "collection.get")),
    ),
    "template": (
        CollectionCapabilityBinding("collection.info", ("collection.info",), source="local"),
        CollectionCapabilityBinding("collection.template.list", ("collection.template.list",), source="local"),
        CollectionCapabilityBinding("collection.template.search", ("collection.template.search",), source="local"),
        CollectionCapabilityBinding("collection.template.get_schema", ("collection.template.get_schema",), source="local"),
        CollectionCapabilityBinding("collection.template.fill", ("collection.template.fill",), source="local"),
    ),
    "sql": (
        CollectionCapabilityBinding("collection.info", ("collection.info",), source="local"),
        CollectionCapabilityBinding("collection.sql.search_objects", ("sql.search_objects", "search_objects"), source="mcp"),
        CollectionCapabilityBinding("collection.sql.execute", ("sql.execute_sql", "execute_sql"), source="mcp"),
    ),
    "api": (
        CollectionCapabilityBinding("collection.info", ("collection.info",), source="local"),
        CollectionCapabilityBinding("collection.api.get_device", ("netbox_get_device",), source="mcp"),
        CollectionCapabilityBinding("collection.api.search_devices", ("netbox_search_devices",), source="mcp"),
        CollectionCapabilityBinding("collection.api.list_sites", ("netbox_list_sites",), source="mcp"),
        CollectionCapabilityBinding("collection.api.get_objects", ("netbox_get_objects",), source="mcp"),
        CollectionCapabilityBinding("collection.api.search_objects", ("netbox_search_objects",), source="mcp"),
    ),
}

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
                description="",
                result_kind="generic",
                scope_kind="system",
            ),
        )
    return None


def is_operation_allowed_for_collection_type(
    publication: PublicationDecision,
    *,
    collection_type: Optional[str],
) -> bool:
    supported = tuple(publication.spec.collection_types or ())
    if not supported:
        return publication.scope_kind != "collection"
    normalized = str(collection_type or "").strip().lower()
    return bool(normalized) and normalized in supported


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
    if "system" in candidate_domains and not op_domain.startswith("collection."):
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


def get_operation_spec(canonical_op_slug: str) -> Optional[OperationSpec]:
    return _OPERATION_SPECS.get(str(canonical_op_slug or "").strip())


def get_collection_capability_bindings(
    collection_type: str,
) -> Tuple[CollectionCapabilityBinding, ...]:
    return _COLLECTION_CAPABILITY_BINDINGS.get(str(collection_type or "").strip().lower(), ())


def build_collection_workflow_steps(
    *,
    collection_type: str,
    canonical_operations: Iterable[str],
) -> List[str]:
    ops = {
        str(item or "").strip()
        for item in canonical_operations
        if str(item or "").strip()
    }
    steps: List[str] = []

    if "collection.info" in ops:
        if collection_type in {"table", "document", "template"}:
            steps.append(
                "Сначала вызови `collection.info`, если нужно понять поля, фильтры, наблюдаемые значения или структуру данных."
            )
        elif collection_type in {"sql", "api"}:
            steps.append(
                "Сначала вызови `collection.info`, чтобы понять доступную структуру, сущности и ограничения источника."
            )

    if collection_type == "document":
        if "collection.document.search" in ops:
            steps.append(
                "Для поиска содержимого начни с `collection.document.search` и получи `document_id` из результата."
            )
        if "collection.document.get" in ops:
            steps.append(
                "Используй `collection.document.get` только с `document_id`, полученным из `collection.document.search` или `collection.document.list`."
            )
        elif "collection.document.list" in ops:
            steps.append(
                "Используй `collection.document.list`, когда нужно перечислить документы, а не искать по смыслу."
            )
    elif collection_type == "template":
        if "collection.template.search" in ops:
            steps.append(
                "Если шаблон неочевиден, начни с `collection.template.search`, чтобы найти подходящий `row_id` по смыслу."
            )
        if "collection.template.list" in ops:
            steps.append(
                "Используй `collection.template.list`, чтобы получить точные `row_id`, названия шаблонов и связанные файлы."
            )
        if "collection.template.get_schema" in ops:
            steps.append(
                "Перед заполнением вызови `collection.template.get_schema` с реальным `row_id`, чтобы узнать поля и placeholders."
            )
        if "collection.template.fill" in ops:
            steps.append(
                "`collection.template.fill` вызывай только с `row_id`, найденным через `collection.template.list` или `collection.template.search`; не придумывай `row_id`."
            )
    elif collection_type == "table":
        if "collection.table.search" in ops:
            steps.append(
                "Основной вход — `collection.table.search`; сначала найди нужные строки, потом переходи к точечным операциям."
            )
        if "collection.table.get" in ops:
            steps.append("`collection.table.get` используй только когда уже известен идентификатор записи.")
        if "collection.table.aggregate" in ops:
            steps.append(
                "`collection.table.aggregate` используй для метрик и сводок, а не для чтения конкретных строк."
            )
    elif collection_type == "sql":
        if "collection.sql.search_objects" in ops:
            steps.append(
                "Сначала вызови `collection.sql.search_objects`, чтобы найти нужные таблицы, представления и колонки."
            )
        if "collection.sql.execute" in ops:
            steps.append(
                "После этого используй `collection.sql.execute` только для read-only SQL по уже найденным объектам."
            )
    elif collection_type == "api":
        if "collection.api.search_objects" in ops or "collection.api.get_objects" in ops:
            steps.append(
                "Сначала определи нужный тип сущности, затем используй поиск или выборку объектов по этому типу."
            )
        if "collection.api.search_devices" in ops or "collection.api.get_device" in ops:
            steps.append(
                "Для устройств: `collection.api.search_devices` для поиска, `collection.api.get_device` — когда уже известно точное имя."
            )
        if "collection.api.list_sites" in ops:
            steps.append(
                "`collection.api.list_sites` используй для выбора площадок и контекста, а не для поиска устройств."
            )

    return steps
