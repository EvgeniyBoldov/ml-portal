"""S2 TemplateSchemaBuilder — LLM contract generation from RawLayout with deterministic fallback."""
from __future__ import annotations
import json, logging
from typing import Any, Dict, List, Optional
from app.services.collection.template_contract import (
    TemplateContract, ScalarField, TableField, TableColumn,
    TokenLocator, FieldSource, FieldType, FieldKind,
    TableAnchor, MarkerAnchor, StructuralAnchor, AnchorStrategy,
    DocumentFormat, Orientation, merge_contract,
)
from app.services.collection.template_layout_parser import (
    RawLayout,
    SchemaNode,
    TableRegion,
    TokenOccurrence,
    _build_schema_roots,
)

logger = logging.getLogger(__name__)
SYS_PROMPT = "Analyze template and output JSON schema contract with scalar and table fields."


class TemplateSchemaBuilder:
    """Build contract from RawLayout using LLM with heuristic fallback."""

    def __init__(self, llm: Optional[Any] = None):
        self.llm = llm

    async def build(
        self,
        layout: RawLayout,
        existing_contract: Optional[TemplateContract] = None,
        title: Optional[str] = None,
    ) -> TemplateContract:
        """Generate contract from layout, merging with existing if provided."""
        proposed = await self._llm_build(layout, title)
        if proposed is None:
            proposed = self._heuristic_build(layout)
        if existing_contract:
            return merge_contract(existing_contract, proposed)
        return proposed

    async def _llm_build(self, layout: RawLayout, title: Optional[str]) -> Optional[TemplateContract]:
        if self.llm is None:
            return None
        try:
            prompt = self._build_prompt(layout, title)
            resp = await self.llm.chat(
                [
                    {"role": "system", "content": SYS_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                params={"temperature": 0.2, "max_tokens": 2000},
            )
            content = resp.get("content", "{}")
            data = content if isinstance(content, dict) else json.loads(content)
            return self._parse_llm_response(data, layout)
        except Exception as e:
            logger.warning(f"LLM schema build failed: {e}")
            return None

    def _build_prompt(self, layout: RawLayout, title: Optional[str]) -> str:
        lines = [
            f"Format: {layout.format}",
            f"Title hint: {title or layout.title or 'N/A'}",
        ]
        if layout.scalar_keys:
            lines.append(f"Scalar tokens: {', '.join(layout.scalar_keys[:20])}")
        if layout.table_prefixes:
            lines.append(f"Table prefixes: {', '.join(layout.table_prefixes)}")
        for r in layout.table_regions[:5]:
            header = ", ".join(r.header_row[:5]) if r.header_row else "N/A"
            tokens = ", ".join(r.loop_tokens[:5]) if r.loop_tokens else "N/A"
            lines.append(f"Region {r.region_id}: header=[{header}], tokens=[{tokens}]")
        lines.append(f"Sample text lines: {layout.text_lines[:10]}")
        return "\n".join(lines)

    def _parse_llm_response(self, data: Dict, layout: RawLayout) -> Optional[TemplateContract]:
        fields = []
        for f in data.get("fields", []):
            kind = f.get("kind")
            if kind == "scalar":
                sf = self._parse_scalar_field(f)
                if sf:
                    fields.append(sf)
            elif kind == "table":
                tf = self._parse_table_field(f, layout)
                if tf:
                    fields.append(tf)
        fmt = DocumentFormat(layout.format) if layout.format in ("excel", "docx", "text") else None
        return TemplateContract(fields=fields, format=fmt)

    def _parse_scalar_field(self, data: Dict) -> Optional[ScalarField]:
        key = data.get("key")
        if not key:
            return None
        return ScalarField(
            key=key,
            label=data.get("label", key),
            description=data.get("description"),
            type=FieldType(data.get("type", "string")),
            required=data.get("required", False),
            example=data.get("example"),
            enum=data.get("enum"),
            locator=TokenLocator(token=f"{{{{{key}}}}}"),
            source=FieldSource.LLM,
        )

    def _parse_table_field(self, data: Dict, layout: RawLayout) -> Optional[TableField]:
        key = data.get("key")
        if not key:
            return None
        cols_data = data.get("columns", [])
        columns = []
        for c in cols_data:
            col_key = c.get("key")
            if not col_key:
                continue
            columns.append(TableColumn(
                key=col_key,
                label=c.get("label", col_key),
                description=c.get("description"),
                type=FieldType(c.get("type", "string")),
                required=c.get("required", False),
                example=c.get("example"),
                enum=c.get("enum"),
                locator=TokenLocator(token=f"{{{{{key}.{col_key}}}}}"),
                source=FieldSource.LLM,
            ))
        if not columns:
            return None
        anchor_data = data.get("anchor", {})
        anchor = self._build_anchor(key, anchor_data, layout)
        return TableField(
            key=key,
            label=data.get("label", key),
            description=data.get("description"),
            orientation=Orientation(data.get("orientation", "vertical")),
            required=data.get("required", False),
            min_rows=data.get("min_rows", 0),
            max_rows=data.get("max_rows"),
            anchor=anchor,
            columns=columns,
            source=FieldSource.LLM,
        )

    def _build_anchor(self, key: str, data: Dict, layout: RawLayout) -> Optional[TableAnchor]:
        strategy = data.get("strategy", "auto")
        marker_data = data.get("marker")
        structural_data = data.get("structural")
        marker = MarkerAnchor(loop_tokens=marker_data.get("loop_tokens", [])) if marker_data else None
        structural = None
        if structural_data:
            structural = StructuralAnchor(
                header_signature=structural_data.get("header_signature", []),
                match=structural_data.get("match", "fuzzy"),
                template_row=structural_data.get("template_row", "first_after_header"),
            )
        sheet = None
        for r in layout.table_regions:
            if r.loop_prefix == key:
                sheet = r.location.get("sheet")
                break
        if strategy == "auto":
            if marker and marker.loop_tokens:
                strategy = AnchorStrategy.MARKER
            elif structural and structural.header_signature:
                strategy = AnchorStrategy.STRUCTURAL
            else:
                strategy = AnchorStrategy.AUTO
        return TableAnchor(
            sheet=sheet,
            strategy=AnchorStrategy(strategy),
            marker=marker,
            structural=structural,
        )

    def _heuristic_build(self, layout: RawLayout) -> TemplateContract:
        """Deterministic fallback that materializes the parser schema tree."""
        fields = []
        schema_roots = layout.schema_roots or _build_schema_roots(layout.tokens, layout.table_regions)
        node_meta = self._collect_node_meta(schema_roots)
        for node in schema_roots:
            if node.repeat:
                table = self._table_from_node(node)
                if table is not None:
                    fields.append(table)
                continue
            fields.extend(self._scalar_fields_from_node(node))

        # Structural fallback for spreadsheets/documents without explicit
        # placeholders. This keeps analysis useful when admins rely on
        # header-only tabular layout instead of ``{{table.col}}`` markers.
        table_counter = 0
        existing_keys = {field.key for field in fields}
        for region in layout.table_regions:
            if region.loop_prefix and region.loop_prefix in existing_keys:
                continue
            if not region.header_row:
                continue
            columns = self._columns_from_header(region.header_row)
            if len(columns) < 2:
                continue
            table_counter += 1
            key = region.loop_prefix or f"table_{table_counter}"
            if key in existing_keys:
                continue
            existing_keys.add(key)
            fields.append(TableField(
                key=key,
                label=self._region_label(region, table_counter),
                orientation=Orientation.VERTICAL,
                required=False,
                min_rows=0,
                anchor=TableAnchor(
                    sheet=region.location.get("sheet"),
                    strategy=AnchorStrategy.STRUCTURAL,
                    structural=StructuralAnchor(
                        header_signature=[h for h in region.header_row if str(h).strip()],
                        match="fuzzy",
                        template_row="first_after_header",
                    ),
                ),
                columns=columns,
                source=FieldSource.PARSER,
            ))
        fmt = DocumentFormat(layout.format) if layout.format in ("excel", "docx", "text") else None
        return TemplateContract(fields=fields, format=fmt, node_meta=node_meta)

    def _collect_node_meta(self, roots: List[SchemaNode]) -> Dict[str, Dict[str, Any]]:
        meta: Dict[str, Dict[str, Any]] = {}

        def _walk(node: SchemaNode) -> None:
            if node.children:
                meta[node.path] = {
                    "kind": FieldKind.OBJECT.value,
                    "label": self._label_for_node(node),
                    "description": self._description_for_node(node),
                    "required": self._required_for_node(node),
                    "source": FieldSource.PARSER.value,
                    "locked": False,
                }
            for child in node.children:
                _walk(child)

        for root in roots:
            _walk(root)
        return meta

    def _scalar_fields_from_node(self, node: SchemaNode) -> List[Any]:
        fields: List[Any] = []
        if node.repeat:
            table = self._table_from_node(node)
            if table is not None:
                fields.append(table)
            return fields
        if not node.children:
            fields.append(
                ScalarField(
                    key=node.path,
                    label=self._label_for_node(node),
                    description=self._description_for_node(node),
                    type=self._infer_node_type(node),
                    required=self._required_for_node(node),
                    enum=self._enum_for_node(node),
                    locator=TokenLocator(token=node.placeholder or f"{{{{{node.path}}}}}"),
                    source=FieldSource.PARSER,
                )
            )
            return fields
        for child in node.children:
            fields.extend(self._scalar_fields_from_node(child))
        return fields

    def _table_from_node(self, node: SchemaNode) -> Optional[TableField]:
        if not node.repeat:
            return None
        columns = self._columns_from_node(node)
        if not columns:
            return None
        return TableField(
            key=node.path,
            label=self._label_for_node(node),
            description=self._description_for_node(node),
            orientation=self._orientation_for_node(node),
            required=self._required_for_node(node),
            min_rows=self._min_rows_for_node(node),
            max_rows=self._max_rows_for_node(node),
            anchor=self._anchor_for_node(node),
            columns=columns,
            source=FieldSource.PARSER,
        )

    def _columns_from_node(self, table_node: SchemaNode) -> List[TableColumn]:
        columns: List[TableColumn] = []
        for leaf in self._leaf_nodes(table_node):
            if leaf.path == table_node.path:
                continue
            relative_key = leaf.path[len(table_node.path) + 1:] if leaf.path.startswith(f"{table_node.path}.") else leaf.key
            columns.append(
                TableColumn(
                    key=relative_key,
                    label=self._label_for_node(leaf),
                    description=self._description_for_node(leaf),
                    type=self._infer_node_type(leaf),
                    required=self._required_for_node(leaf),
                    enum=self._enum_for_node(leaf),
                    locator=TokenLocator(token=leaf.placeholder or f"{{{{{leaf.path}}}}}"),
                    source=FieldSource.PARSER,
                )
            )
        return columns

    def _leaf_nodes(self, node: SchemaNode) -> List[SchemaNode]:
        if not node.children:
            return [node]
        leaves: List[SchemaNode] = []
        for child in node.children:
            leaves.extend(self._leaf_nodes(child))
        return leaves

    def _anchor_for_node(self, node: SchemaNode) -> Optional[TableAnchor]:
        hint = node.anchors[0] if node.anchors else None
        if hint is None:
            return None
        location = hint.get("location") or {}
        strategy = AnchorStrategy.MARKER if hint.get("loop_tokens") else AnchorStrategy.STRUCTURAL
        if strategy == AnchorStrategy.MARKER:
            return TableAnchor(
                sheet=location.get("sheet"),
                strategy=strategy,
                marker=MarkerAnchor(loop_tokens=list(hint.get("loop_tokens") or [])),
            )
        return TableAnchor(
            sheet=location.get("sheet"),
            strategy=strategy,
            structural=StructuralAnchor(
                header_signature=[str(value) for value in hint.get("header_row") or [] if str(value).strip()],
                match="fuzzy",
                template_row="first_after_header",
            ),
        )

    def _label_for_node(self, node: SchemaNode) -> str:
        label = node.params.get("name") or node.params.get("label")
        if label:
            return str(label)
        return node.key.replace("_", " ").capitalize()

    def _description_for_node(self, node: SchemaNode) -> Optional[str]:
        description = node.params.get("description")
        return str(description) if description else None

    def _infer_node_type(self, node: SchemaNode) -> FieldType:
        if node.params.get("choice") is not None:
            return FieldType.ENUM
        hint = str(node.hint_type or node.params.get("type") or "").strip().lower()
        if hint in {"int", "float", "number", "decimal"}:
            return FieldType.NUMBER
        if hint in {"bool", "boolean"}:
            return FieldType.BOOL
        if hint in {"date", "datetime"}:
            return FieldType.DATE
        return FieldType.STRING

    def _enum_for_node(self, node: SchemaNode) -> Optional[List[str]]:
        value = node.params.get("choice")
        if isinstance(value, list):
            return [str(item) for item in value]
        return None

    def _required_for_node(self, node: SchemaNode) -> bool:
        value = node.params.get("required")
        return bool(value) if value is not None else False

    def _min_rows_for_node(self, node: SchemaNode) -> int:
        value = node.params.get("min")
        return int(value) if isinstance(value, (int, float)) else 0

    def _max_rows_for_node(self, node: SchemaNode) -> Optional[int]:
        value = node.params.get("max")
        return int(value) if isinstance(value, (int, float)) else None

    def _orientation_for_node(self, node: SchemaNode) -> Orientation:
        hint = node.anchors[0] if node.anchors else None
        orientation = str((hint or {}).get("orientation") or "vertical").strip().lower()
        return Orientation.HORIZONTAL if orientation == "horizontal" else Orientation.VERTICAL

    def _columns_from_header(self, header_row: List[str]) -> List[TableColumn]:
        columns: List[TableColumn] = []
        seen: set[str] = set()
        for idx, raw_header in enumerate(header_row, start=1):
            label = str(raw_header or "").strip() or f"Column {idx}"
            key = self._normalize_field_key(label, fallback=f"column_{idx}")
            if key in seen:
                suffix = 2
                while f"{key}_{suffix}" in seen:
                    suffix += 1
                key = f"{key}_{suffix}"
            seen.add(key)
            columns.append(TableColumn(
                key=key,
                label=label,
                type=FieldType.STRING,
                required=False,
                source=FieldSource.PARSER,
            ))
        return columns

    def _first_token(self, layout: RawLayout, key: str) -> Optional[TokenOccurrence]:
        for token in layout.tokens:
            if token.token == key:
                return token
        return None

    def _infer_field_type(self, token: Optional[TokenOccurrence]) -> FieldType:
        hint = (token.hint_type or self._segment_param(token, "type") or "").strip().lower() if token else ""
        if self._segment_param(token, "choice") is not None:
            return FieldType.ENUM
        if hint in {"int", "float", "number", "decimal"}:
            return FieldType.NUMBER
        if hint in {"bool", "boolean"}:
            return FieldType.BOOL
        if hint in {"date", "datetime"}:
            return FieldType.DATE
        return FieldType.STRING

    def _hint_description(self, token: Optional[TokenOccurrence]) -> Optional[str]:
        if not token:
            return None
        hints: list[str] = []
        hint_type = token.hint_type or self._segment_param(token, "type")
        hint_args = token.hint_args or self._segment_param(token, "type_args")
        if hint_type:
            hint = str(hint_type)
            if hint_args:
                hint = f"{hint}({hint_args})"
            hints.append(hint)
        params = self._segment_params(token)
        if params:
            parts = []
            for key in ("description", "min", "max", "required", "choice"):
                if key in params:
                    parts.append(f"{key}={params[key]}")
            if parts:
                hints.append(", ".join(parts))
        if not hints:
            return None
        return f"Template hint: {'; '.join(hints)}"

    def _label_for_token(
        self,
        key: str,
        token: Optional[TokenOccurrence],
        *,
        default_key: Optional[str] = None,
        context: str = "scalar",
    ) -> str:
        label = None
        params = self._segment_params(token, context=context)
        if params:
            label = params.get("name") or params.get("label")
        if not label:
            tail = (default_key or key).split(".")[-1]
            label = tail.replace("_", " ").capitalize()
        return str(label)

    def _token_for_placeholder(self, layout: RawLayout, placeholder: str) -> Optional[TokenOccurrence]:
        for token in layout.tokens:
            if token.placeholder == placeholder:
                return token
        clean = placeholder.strip("{}")
        clean = clean.replace("[]", "")
        return self._first_token(layout, clean)

    def _first_table_token(
        self,
        layout: RawLayout,
        prefix: str,
        region: Optional[TableRegion],
    ) -> Optional[TokenOccurrence]:
        if region and region.loop_tokens:
            for placeholder in region.loop_tokens:
                token = self._token_for_placeholder(layout, placeholder)
                if token is not None:
                    return token
        for token in layout.tokens:
            if token.table_prefix == prefix or token.token.startswith(f"{prefix}."):
                return token
        return self._first_token(layout, prefix)

    def _segment_params(
        self,
        token: Optional[TokenOccurrence],
        *,
        context: str = "scalar",
    ) -> Dict[str, Any]:
        if not token or not token.segments:
            return token.params if token else {}
        if context == "table":
            for segment in token.segments:
                if segment.get("repeat"):
                    return dict(segment.get("params") or {})
            return dict(token.segments[0].get("params") or {})
        if context == "column":
            return dict(token.segments[-1].get("params") or {})
        return dict(token.segments[-1].get("params") or {})

    def _segment_param(
        self,
        token: Optional[TokenOccurrence],
        key: str,
        *,
        context: str = "scalar",
    ) -> Any:
        return self._segment_params(token, context=context).get(key)

    def _is_required(self, token: Optional[TokenOccurrence], *, context: str) -> bool:
        value = self._segment_param(token, "required", context=context)
        return bool(value) if value is not None else False

    def _min_rows(self, token: Optional[TokenOccurrence]) -> int:
        value = self._segment_param(token, "min", context="table")
        return int(value) if isinstance(value, (int, float)) else 0

    def _max_rows(self, token: Optional[TokenOccurrence]) -> Optional[int]:
        value = self._segment_param(token, "max", context="table")
        return int(value) if isinstance(value, (int, float)) else None

    def _table_description(self, token: Optional[TokenOccurrence]) -> Optional[str]:
        value = self._segment_param(token, "description", context="table")
        return str(value) if value else None

    def _region_label(self, region: TableRegion, counter: int) -> str:
        if region.loop_prefix:
            return region.loop_prefix.replace("_", " ").capitalize()
        first = next((str(h).strip() for h in region.header_row if str(h).strip()), "")
        return first or f"Table {counter}"

    def _normalize_field_key(self, value: str, *, fallback: str) -> str:
        normalized = value.strip().lower()
        normalized = normalized.replace(".", "_")
        normalized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in normalized)
        normalized = normalized.strip("_")
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized or fallback
