"""
TemplateLayoutParser — deterministic raw layout extraction (S1).

Parses template files (Excel / Word / plain-text) and returns a ``RawLayout``
dataclass that captures:

- All ``{{token}}`` occurrences with their positions.
- Document-level structure (sheets / paragraphs / lines).
- Table regions (Excel openpyxl tables, docx tables, heuristic dense regions).
- Marker-loop candidates: rows/columns that contain at least one dotted token
  ``{{table.col}}``.
- Block fences: ``{{#key}} … {{/key}}`` pairs in docx/text.
- Title and version hints extracted from leading non-placeholder text.

This module has **no LLM calls, no DB access, no async I/O** — it is a pure
bytes → data-structure transformation and must remain deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches dotted and simple tokens: {{name}}, {{items.qty}}, {{x.y.z}}
_TOKEN_RE = re.compile(r"\{\{([A-Za-z0-9_.\-]+)\}\}")
# Open/close fences: {{#key}} / {{/key}}
_FENCE_OPEN_RE = re.compile(r"\{\{#([A-Za-z0-9_.\-]+)\}\}")
_FENCE_CLOSE_RE = re.compile(r"\{\{/([A-Za-z0-9_.\-]+)\}\}")
# Version hint
_VERSION_RE = re.compile(
    r"(?:версия|version|v\.?)[:\s]*([\d]+(?:\.[\d]+)*)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TokenOccurrence:
    """A single ``{{token}}`` occurrence in the source."""
    token: str           # raw key inside braces, e.g. "items.qty"
    table_prefix: Optional[str]   # "items" if dotted, else None
    column_key: Optional[str]     # "qty" if dotted, else None
    location: Dict[str, Any]      # format-specific position info


@dataclass
class TableRegion:
    """A detected repeatable region in the document."""
    region_id: str
    location: Dict[str, Any]           # {sheet, row_start, row_end, col_start, col_end} etc.
    # Marker-loop info (if any column token found in the region)
    loop_tokens: List[str] = field(default_factory=list)   # e.g. ["{{items.name}}", "{{items.qty}}"]
    loop_prefix: Optional[str] = None                       # common table prefix, e.g. "items"
    # Structural anchor hint
    header_row: Optional[List[str]] = field(default_factory=list)  # text of header cells
    template_row_index: Optional[int] = None                        # 0-based row index after header
    orientation: str = "vertical"   # "vertical" | "horizontal"


@dataclass
class FenceBlock:
    """A ``{{#key}} … {{/key}}`` block (docx/text)."""
    key: str
    open_position: Dict[str, Any]
    close_position: Optional[Dict[str, Any]] = None


@dataclass
class RawLayout:
    """Complete raw layout extracted from a template file."""
    format: str                                    # "excel" | "docx" | "text"
    title: Optional[str]
    version: Optional[str]
    tokens: List[TokenOccurrence] = field(default_factory=list)
    table_regions: List[TableRegion] = field(default_factory=list)
    fence_blocks: List[FenceBlock] = field(default_factory=list)
    sheets: List[str] = field(default_factory=list)   # Excel sheet names
    # Aggregated unique token keys (scalar and table-prefixed)
    scalar_keys: List[str] = field(default_factory=list)   # non-dotted keys
    table_prefixes: List[str] = field(default_factory=list)  # dotted key table-parts
    # Raw text lines / paragraph texts — useful for LLM schema builder
    text_lines: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class TemplateLayoutParser:
    """Parse a template file and return a ``RawLayout`` (no LLM, no I/O)."""

    def parse(self, content: bytes, filename: str) -> RawLayout:
        ext = _ext(filename)
        if ext in ("xlsx", "xlsm", "xls"):
            return self._parse_excel(content, filename)
        if ext == "docx":
            return self._parse_docx(content, filename)
        return self._parse_text(content, filename)

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------

    def _parse_excel(self, content: bytes, filename: str) -> RawLayout:
        import io

        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("openpyxl is required for Excel template parsing") from exc

        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        tokens: List[TokenOccurrence] = []
        table_regions: List[TableRegion] = []
        text_lines: List[str] = []
        first_texts: List[str] = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            # Collect all cell data: {row: {col: value}}
            row_map: Dict[int, Dict[int, str]] = {}
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    val = str(cell.value).strip()
                    if not val:
                        continue
                    row_map.setdefault(cell.row, {})[cell.column] = val
                    text_lines.append(val)

                    for m in _TOKEN_RE.finditer(val):
                        key = m.group(1)
                        table_prefix, col_key = _split_dotted(key)
                        tokens.append(TokenOccurrence(
                            token=key,
                            table_prefix=table_prefix,
                            column_key=col_key,
                            location={
                                "sheet": sheet_name,
                                "row": cell.row,
                                "col": cell.column,
                                "coordinate": cell.coordinate,
                                "source_text": val,
                            },
                        ))

            if first_texts == [] and text_lines:
                first_texts = text_lines[:10]

            # Detect table regions for this sheet
            table_regions.extend(
                self._detect_excel_table_regions(ws, sheet_name, row_map)
            )

        sheet_names = list(wb.sheetnames)
        wb.close()

        title, version = _extract_title_version(first_texts)
        scalar_keys, table_prefixes = _aggregate_keys(tokens)

        return RawLayout(
            format="excel",
            title=title,
            version=version,
            tokens=tokens,
            table_regions=table_regions,
            sheets=sheet_names,
            scalar_keys=scalar_keys,
            table_prefixes=table_prefixes,
            text_lines=text_lines[:500],  # cap for LLM builder
        )

    def _detect_excel_table_regions(
        self,
        ws: Any,
        sheet_name: str,
        row_map: Dict[int, Dict[int, str]],
    ) -> List[TableRegion]:
        """Detect table regions in an Excel sheet.

        Two detection paths:
        1. **Marker rows** — rows that contain ≥2 dotted tokens sharing the same prefix.
        2. **Dense rows** — heuristic: ≥2 consecutive non-empty rows with ≥2 columns
           → candidate table; first row treated as header if it has no tokens.
        """
        regions: List[TableRegion] = []
        sorted_rows = sorted(row_map.keys())

        # --- Marker detection ---
        prefix_to_rows: Dict[str, List[int]] = {}
        for r in sorted_rows:
            row_vals = row_map[r]
            prefixes_in_row: Dict[str, List[str]] = {}
            for val in row_vals.values():
                for m in _TOKEN_RE.finditer(val):
                    key = m.group(1)
                    tp, ck = _split_dotted(key)
                    if tp:
                        prefixes_in_row.setdefault(tp, []).append(f"{{{{{key}}}}}")
            for tp, toks in prefixes_in_row.items():
                # A dotted prefix denotes a table column, so even a single
                # column ({{items.name}}) constitutes a marker-loop region.
                if len(toks) >= 1:
                    prefix_to_rows.setdefault(tp, []).append(r)

        for prefix, marker_rows in prefix_to_rows.items():
            marker_row = marker_rows[0]
            # Collect all loop_tokens from that row
            loop_tokens: List[str] = []
            row_cols = sorted(row_map.get(marker_row, {}).keys())
            col_start = row_cols[0] if row_cols else 1
            col_end = row_cols[-1] if row_cols else 1
            for val in row_map.get(marker_row, {}).values():
                for m in _TOKEN_RE.finditer(val):
                    key = m.group(1)
                    tp, _ = _split_dotted(key)
                    if tp == prefix:
                        tok = f"{{{{{key}}}}}"
                        if tok not in loop_tokens:
                            loop_tokens.append(tok)
            # Check for optional row above as header
            header_row_idx = marker_row - 1
            header_texts: List[str] = []
            if header_row_idx in row_map:
                header_vals = row_map[header_row_idx]
                header_texts = [header_vals.get(c, "") for c in row_cols]

            regions.append(TableRegion(
                region_id=f"{sheet_name}:marker:{prefix}",
                location={
                    "sheet": sheet_name,
                    "marker_row": marker_row,
                    "col_start": col_start,
                    "col_end": col_end,
                },
                loop_tokens=loop_tokens,
                loop_prefix=prefix,
                header_row=header_texts,
                template_row_index=None,
                orientation="vertical",
            ))

        # --- Structural (dense rows) fallback — only if no markers found ---
        if not prefix_to_rows:
            regions.extend(
                self._detect_dense_regions(sheet_name, row_map, sorted_rows)
            )

        return regions

    def _detect_dense_regions(
        self,
        sheet_name: str,
        row_map: Dict[int, Dict[int, str]],
        sorted_rows: List[int],
    ) -> List[TableRegion]:
        """Find dense rectangular regions (≥2 cols, ≥2 rows) as structural candidates."""
        regions: List[TableRegion] = []
        min_cols = 2
        run_rows: List[int] = []

        def _flush(run: List[int]) -> None:
            if len(run) < 2:
                return
            first_r = run[0]
            last_r = run[-1]
            all_cols: List[int] = []
            for r in run:
                all_cols.extend(row_map[r].keys())
            col_start = min(all_cols) if all_cols else 1
            col_end = max(all_cols) if all_cols else 1
            # Treat first row as potential header (no tokens)
            first_row_vals = list(row_map[first_r].values())
            has_tokens_in_first = any(_TOKEN_RE.search(v) for v in first_row_vals)
            header_texts = first_row_vals if not has_tokens_in_first else []
            template_row_idx = 1 if not has_tokens_in_first else 0

            regions.append(TableRegion(
                region_id=f"{sheet_name}:structural:r{first_r}-{last_r}",
                location={
                    "sheet": sheet_name,
                    "row_start": first_r,
                    "row_end": last_r,
                    "col_start": col_start,
                    "col_end": col_end,
                },
                loop_tokens=[],
                loop_prefix=None,
                header_row=header_texts,
                template_row_index=template_row_idx,
                orientation="vertical",
            ))

        for r in sorted_rows:
            if len(row_map[r]) >= min_cols:
                run_rows.append(r)
            else:
                _flush(run_rows)
                run_rows = []
        _flush(run_rows)
        return regions

    # ------------------------------------------------------------------
    # Docx
    # ------------------------------------------------------------------

    def _parse_docx(self, content: bytes, filename: str) -> RawLayout:
        import io

        try:
            import docx
        except ImportError as exc:
            raise RuntimeError("python-docx is required for Word template parsing") from exc

        doc = docx.Document(io.BytesIO(content))
        tokens: List[TokenOccurrence] = []
        fence_blocks: List[FenceBlock] = []
        text_lines: List[str] = []
        table_regions: List[TableRegion] = []

        open_fences: Dict[str, Dict[str, Any]] = {}

        # Paragraphs
        for p_idx, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if not text:
                continue
            text_lines.append(text)

            for m in _FENCE_OPEN_RE.finditer(text):
                key = m.group(1)
                open_fences[key] = {"paragraph_index": p_idx, "context": text[:100]}

            for m in _FENCE_CLOSE_RE.finditer(text):
                key = m.group(1)
                open_pos = open_fences.pop(key, None)
                fence_blocks.append(FenceBlock(
                    key=key,
                    open_position=open_pos or {},
                    close_position={"paragraph_index": p_idx, "context": text[:100]},
                ))

            for m in _TOKEN_RE.finditer(text):
                key = m.group(1)
                table_prefix, col_key = _split_dotted(key)
                tokens.append(TokenOccurrence(
                    token=key,
                    table_prefix=table_prefix,
                    column_key=col_key,
                    location={
                        "type": "paragraph",
                        "paragraph_index": p_idx,
                        "source_text": text[:200],
                    },
                ))

        # Tables
        for t_idx, table in enumerate(doc.tables):
            region_tokens: List[str] = []
            header_texts: List[str] = []
            prefix_counts: Dict[str, int] = {}

            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    cell_text = cell.text.strip()
                    if not cell_text:
                        continue
                    text_lines.append(cell_text)

                    for m in _TOKEN_RE.finditer(cell_text):
                        key = m.group(1)
                        table_prefix, col_key = _split_dotted(key)
                        tok = f"{{{{{key}}}}}"
                        if tok not in region_tokens:
                            region_tokens.append(tok)
                        tokens.append(TokenOccurrence(
                            token=key,
                            table_prefix=table_prefix,
                            column_key=col_key,
                            location={
                                "type": "table",
                                "table_index": t_idx,
                                "row_index": r_idx,
                                "col_index": c_idx,
                                "source_text": cell_text[:200],
                            },
                        ))
                        if table_prefix:
                            prefix_counts[table_prefix] = prefix_counts.get(table_prefix, 0) + 1

                    if r_idx == 0:
                        header_texts.append(cell_text)

            if not table.rows:
                continue

            rows_count = len(table.rows)
            cols_count = len(table.columns)
            # Find dominant prefix (most column tokens)
            dominant_prefix = max(prefix_counts, key=lambda k: prefix_counts[k]) if prefix_counts else None
            loop_toks = [t for t in region_tokens if dominant_prefix and dominant_prefix + "." in t] if dominant_prefix else []

            table_regions.append(TableRegion(
                region_id=f"docx:table:{t_idx}",
                location={
                    "type": "docx_table",
                    "table_index": t_idx,
                    "rows": rows_count,
                    "cols": cols_count,
                },
                loop_tokens=loop_toks,
                loop_prefix=dominant_prefix,
                header_row=header_texts,
                template_row_index=1 if header_texts else 0,
                orientation="vertical",
            ))

        # Unclosed fences
        for key, open_pos in open_fences.items():
            fence_blocks.append(FenceBlock(key=key, open_position=open_pos))

        title, version = _extract_title_version(text_lines[:20])
        scalar_keys, table_prefixes = _aggregate_keys(tokens)

        return RawLayout(
            format="docx",
            title=title,
            version=version,
            tokens=tokens,
            table_regions=table_regions,
            fence_blocks=fence_blocks,
            scalar_keys=scalar_keys,
            table_prefixes=table_prefixes,
            text_lines=text_lines[:500],
        )

    # ------------------------------------------------------------------
    # Plain text
    # ------------------------------------------------------------------

    def _parse_text(self, content: bytes, filename: str) -> RawLayout:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")

        tokens: List[TokenOccurrence] = []
        fence_blocks: List[FenceBlock] = []
        open_fences: Dict[str, Dict[str, Any]] = {}
        text_lines: List[str] = []

        for line_idx, raw_line in enumerate(text.splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            text_lines.append(line)

            for m in _FENCE_OPEN_RE.finditer(line):
                key = m.group(1)
                open_fences[key] = {"line_index": line_idx, "context": line[:100]}

            for m in _FENCE_CLOSE_RE.finditer(line):
                key = m.group(1)
                open_pos = open_fences.pop(key, None)
                fence_blocks.append(FenceBlock(
                    key=key,
                    open_position=open_pos or {},
                    close_position={"line_index": line_idx, "context": line[:100]},
                ))

            for m in _TOKEN_RE.finditer(line):
                key = m.group(1)
                table_prefix, col_key = _split_dotted(key)
                tokens.append(TokenOccurrence(
                    token=key,
                    table_prefix=table_prefix,
                    column_key=col_key,
                    location={
                        "type": "line",
                        "line_index": line_idx,
                        "source_text": line[:200],
                    },
                ))

        # Table regions from fence blocks
        table_regions: List[TableRegion] = []
        for fb in fence_blocks:
            if fb.close_position is not None:
                region_tokens = [
                    f"{{{{{t.token}}}}}"
                    for t in tokens
                    if t.table_prefix == fb.key
                ]
                table_regions.append(TableRegion(
                    region_id=f"text:fence:{fb.key}",
                    location={
                        "type": "fence",
                        "key": fb.key,
                        "open": fb.open_position,
                        "close": fb.close_position,
                    },
                    loop_tokens=list(dict.fromkeys(region_tokens)),
                    loop_prefix=fb.key,
                    orientation="vertical",
                ))

        # Also add structural regions for dotted keys without fences
        fenced_prefixes = {fb.key for fb in fence_blocks}
        prefix_tokens: Dict[str, List[str]] = {}
        for t in tokens:
            if t.table_prefix and t.table_prefix not in fenced_prefixes:
                prefix_tokens.setdefault(t.table_prefix, []).append(f"{{{{{t.token}}}}}")
        for prefix, toks in prefix_tokens.items():
            if len(set(toks)) >= 1:
                table_regions.append(TableRegion(
                    region_id=f"text:marker:{prefix}",
                    location={"type": "inline", "key": prefix},
                    loop_tokens=list(dict.fromkeys(toks)),
                    loop_prefix=prefix,
                    orientation="vertical",
                ))

        title, version = _extract_title_version(text_lines[:10])
        scalar_keys, table_prefixes = _aggregate_keys(tokens)

        return RawLayout(
            format="text",
            title=title,
            version=version,
            tokens=tokens,
            table_regions=table_regions,
            fence_blocks=fence_blocks,
            scalar_keys=scalar_keys,
            table_prefixes=table_prefixes,
            text_lines=text_lines[:500],
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].strip().lower() if "." in filename else ""


def _split_dotted(key: str) -> Tuple[Optional[str], Optional[str]]:
    """Split a dotted key like 'items.qty' → ('items', 'qty').

    Non-dotted keys return ``(None, None)``.
    Only the *first* dot is used as separator; deeper nesting is not supported.
    """
    if "." in key:
        parts = key.split(".", 1)
        return parts[0], parts[1]
    return None, None


def _extract_title_version(texts: List[str]) -> Tuple[Optional[str], Optional[str]]:
    title: Optional[str] = None
    version: Optional[str] = None
    for raw in texts:
        line = raw.strip()
        if not line:
            continue
        if title is None and len(line) > 3 and not _TOKEN_RE.search(line):
            title = line
        if version is None:
            m = _VERSION_RE.search(line)
            if m:
                version = m.group(1)
        if title and version:
            break
    return title, version


def _aggregate_keys(
    tokens: List[TokenOccurrence],
) -> Tuple[List[str], List[str]]:
    """Return (scalar_keys, table_prefixes) from token list, deduplicated, ordered."""
    scalars: List[str] = []
    prefixes: List[str] = []
    seen_s: set = set()
    seen_p: set = set()
    for t in tokens:
        if t.table_prefix:
            if t.table_prefix not in seen_p:
                seen_p.add(t.table_prefix)
                prefixes.append(t.table_prefix)
        else:
            if t.token not in seen_s:
                seen_s.add(t.token)
                scalars.append(t.token)
    return scalars, prefixes
