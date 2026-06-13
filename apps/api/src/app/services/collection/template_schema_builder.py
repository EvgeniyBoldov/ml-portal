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
from app.services.collection.template_layout_parser import RawLayout, TableRegion

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
            data = json.loads(resp.get("content", "{}"))
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
            required=data.get("required", True),
            example=data.get("example"),
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
                required=c.get("required", True),
                example=c.get("example"),
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
            required=data.get("required", True),
            min_rows=data.get("min_rows", 1),
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
        """Deterministic fallback: scalars from non-dotted, tables from dotted prefixes."""
        fields = []
        for key in layout.scalar_keys:
            fields.append(ScalarField(
                key=key,
                label=key.replace("_", " ").capitalize(),
                type=FieldType.STRING,
                required=True,
                locator=TokenLocator(token=f"{{{{{key}}}}}"),
                source=FieldSource.PARSER,
            ))
        prefix_to_region: Dict[str, TableRegion] = {}
        for r in layout.table_regions:
            if r.loop_prefix and r.loop_prefix not in prefix_to_region:
                prefix_to_region[r.loop_prefix] = r
        for prefix in layout.table_prefixes:
            region = prefix_to_region.get(prefix)
            columns = []
            if region and region.loop_tokens:
                for tok in region.loop_tokens:
                    col_key = tok.strip("{}").split(".", 1)[-1] if "." in tok else tok
                    columns.append(TableColumn(
                        key=col_key,
                        label=col_key.replace("_", " ").capitalize(),
                        type=FieldType.STRING,
                        required=True,
                        locator=TokenLocator(token=tok),
                        source=FieldSource.PARSER,
                    ))
            else:
                columns.append(TableColumn(
                    key="value",
                    label="Value",
                    type=FieldType.STRING,
                    required=True,
                    locator=TokenLocator(token="{{" + prefix + ".value}}"),
                    source=FieldSource.PARSER,
                ))
            strategy = AnchorStrategy.MARKER if region and region.loop_tokens else AnchorStrategy.STRUCTURAL
            anchor = None
            if strategy == AnchorStrategy.MARKER:
                anchor = TableAnchor(
                    sheet=region.location.get("sheet") if region else None,
                    strategy=strategy,
                    marker=MarkerAnchor(loop_tokens=region.loop_tokens if region else []),
                )
            else:
                header = region.header_row if region and region.header_row else []
                anchor = TableAnchor(
                    sheet=region.location.get("sheet") if region else None,
                    strategy=strategy,
                    structural=StructuralAnchor(
                        header_signature=header,
                        match="fuzzy",
                        template_row="first_after_header",
                    ),
                )
            fields.append(TableField(
                key=prefix,
                label=prefix.capitalize(),
                orientation=Orientation.VERTICAL,
                required=True,
                min_rows=1,
                anchor=anchor,
                columns=columns,
                source=FieldSource.PARSER,
            ))
        fmt = DocumentFormat(layout.format) if layout.format in ("excel", "docx", "text") else None
        return TemplateContract(fields=fields, format=fmt)
