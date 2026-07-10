"""S4 TemplateFillEngine — fill templates with contract validation.

Supports:
- Scalar field substitution ({{key}})
- Table expansion via marker-loop ({{#table}}..{{/table}})
- Table expansion via structural anchor (header_signature matching)
- Excel, Docx, Text formats
"""
from __future__ import annotations

from copy import copy, deepcopy
import io
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from app.services.collection.template_contract import (
    AnchorStrategy,
    DocumentFormat,
    Orientation,
    ScalarField,
    TableAnchor,
    TableField,
    TemplateContract,
    ValidationReport,
)
from app.services.collection.template_layout_parser import _parse_placeholder_expr

logger = logging.getLogger(__name__)


@dataclass
class FillResult:
    """Result of template filling operation."""
    success: bool
    content: Optional[bytes] = None
    error: Optional[str] = None
    filled_scalars: List[str] = None
    filled_tables: List[str] = None
    missing_scalars: List[str] = None
    missing_tables: List[str] = None
    validation: Optional[ValidationReport] = None

    def __post_init__(self):
        if self.filled_scalars is None:
            self.filled_scalars = []
        if self.filled_tables is None:
            self.filled_tables = []
        if self.missing_scalars is None:
            self.missing_scalars = []
        if self.missing_tables is None:
            self.missing_tables = []


class TemplateFillEngine:
    """Fill templates using contract validation and table expansion."""

    def __init__(self, contract: TemplateContract):
        self.contract = contract

    def fill(
        self,
        template_bytes: bytes,
        values: Dict[str, Any],
        filename: str,
        *,
        assume_valid: bool = False,
    ) -> FillResult:
        """Fill template with validated values."""
        normalized_values = self.contract.normalize_values(values)
        if not assume_valid:
            report = self.contract.validate_generated_values(values)
            if not report.ok:
                return FillResult(
                    success=False,
                    error=f"Validation failed: {report.errors}",
                    validation=report,
                )

        fmt = self._detect_format(filename)
        if fmt == DocumentFormat.EXCEL:
            return self._fill_excel(template_bytes, normalized_values)
        elif fmt == DocumentFormat.DOCX:
            return self._fill_docx(template_bytes, normalized_values)
        else:
            return self._fill_text(template_bytes, normalized_values)

    def _detect_format(self, filename: str) -> DocumentFormat:
        fn = filename.lower()
        if fn.endswith('.xlsx') or fn.endswith('.xls'):
            return DocumentFormat.EXCEL
        elif fn.endswith('.docx'):
            return DocumentFormat.DOCX
        else:
            return DocumentFormat.TEXT

    def _fill_text(self, template_bytes: bytes, values: Dict[str, Any]) -> FillResult:
        """Fill text template with scalar substitution."""
        try:
            text = template_bytes.decode('utf-8')
        except UnicodeDecodeError:
            text = template_bytes.decode('utf-8', errors='replace')

        filled_scalars = []
        missing_scalars = []
        filled_tables = []
        missing_tables = []

        scalar_map = {
            field.key: _lookup_nested_value(values, field.key)
            for field in self.contract.scalar_fields()
        }
        text, used_keys = _substitute_placeholders(text, scalar_map)
        filled_scalars.extend(sorted(used_keys))
        for field in self.contract.scalar_fields():
            if field.key not in used_keys and _lookup_nested_value(values, field.key) in (None, ""):
                missing_scalars.append(field.key)

        # Simple table handling for text (no row expansion, just markers)
        for tfield in self.contract.table_fields():
            table_key = tfield.key
            if table_key not in values:
                missing_tables.append(table_key)
                continue
            rows = values[table_key]
            if not isinstance(rows, list):
                missing_tables.append(table_key)
                continue
            # Replace first occurrence with joined rows, remove markers
            marker_start = f"{{{{#{table_key}}}}}"
            marker_end = f"{{{{/{table_key}}}}}"
            if marker_start in text and marker_end in text:
                # Build replacement text from rows
                parts = []
                for row in rows:
                    row_text = " ".join(str(row.get(c.key, "")) for c in tfield.columns)
                    parts.append(row_text)
                replacement = "\n".join(parts)
                # Replace between markers
                pattern = re.escape(marker_start) + r".*?" + re.escape(marker_end)
                text = re.sub(pattern, replacement, text, flags=re.DOTALL)
                filled_tables.append(table_key)
            else:
                # No markers - simple column substitution won't work for multiple rows
                missing_tables.append(table_key)

        total_filled = len(filled_scalars) + len(filled_tables)
        if total_filled == 0:
            return FillResult(
                success=False,
                error="No placeholders were filled. Verify values keys against template schema before calling fill.",
                missing_scalars=missing_scalars,
                missing_tables=missing_tables,
            )

        return FillResult(
            success=True,
            content=text.encode('utf-8'),
            filled_scalars=filled_scalars,
            missing_scalars=missing_scalars,
            filled_tables=filled_tables,
            missing_tables=missing_tables,
        )

    def _fill_excel(self, template_bytes: bytes, values: Dict[str, Any]) -> FillResult:
        """Fill Excel template with scalar and table expansion."""
        try:
            import openpyxl
        except ImportError:
            return FillResult(success=False, error="openpyxl not available")

        try:
            wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
        except Exception as e:
            return FillResult(success=False, error=f"Failed to load Excel: {e}")

        filled_scalars = []
        filled_tables = []
        missing_scalars = []
        missing_tables = []

        scalar_map = {
            field.key: _lookup_nested_value(values, field.key)
            for field in self.contract.scalar_fields()
        }
        used_scalar_keys: set[str] = set()
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value and isinstance(cell.value, str):
                        new_val, keys = _substitute_placeholders(cell.value, scalar_map)
                        if new_val != cell.value:
                            cell.value = new_val
                            used_scalar_keys.update(keys)
        filled_scalars.extend(sorted(used_scalar_keys))
        for field in self.contract.scalar_fields():
            if field.key not in used_scalar_keys and _lookup_nested_value(values, field.key) in (None, ""):
                missing_scalars.append(field.key)

        # Fill tables
        for tfield in self.contract.table_fields():
            table_key = tfield.key
            if table_key not in values:
                missing_tables.append(table_key)
                continue
            rows = values[table_key]
            if not isinstance(rows, list):
                missing_tables.append(table_key)
                continue

            anchor = tfield.anchor
            if anchor and anchor.strategy == AnchorStrategy.MARKER and anchor.marker:
                # Marker-loop strategy
                marker_success, marker_error = self._expand_excel_marker_loop(wb, tfield, rows)
                if marker_success:
                    filled_tables.append(table_key)
                else:
                    missing_tables.append(table_key)
                    if marker_error:
                        return FillResult(success=False, error=marker_error)
            elif anchor and anchor.strategy == AnchorStrategy.STRUCTURAL and anchor.structural:
                # Structural strategy
                structural_success, structural_error = self._expand_excel_structural(wb, tfield, rows)
                if structural_success:
                    filled_tables.append(table_key)
                else:
                    missing_tables.append(table_key)
                    if structural_error:
                        return FillResult(success=False, error=structural_error)
            else:
                # Auto - try marker first, then structural
                marker_success, marker_error = self._expand_excel_marker_loop(wb, tfield, rows)
                if marker_success:
                    filled_tables.append(table_key)
                else:
                    structural_success, structural_error = self._expand_excel_structural(wb, tfield, rows)
                    if structural_success:
                        filled_tables.append(table_key)
                    else:
                        missing_tables.append(table_key)
                        error_message = marker_error or structural_error
                        if error_message:
                            return FillResult(success=False, error=error_message)

        output = io.BytesIO()
        wb.save(output)
        total_filled = len(filled_scalars) + len(filled_tables)
        if total_filled == 0:
            return FillResult(
                success=False,
                error="No placeholders were filled. Verify values keys against template schema before calling fill.",
                missing_scalars=missing_scalars,
                missing_tables=missing_tables,
            )

        return FillResult(
            success=True,
            content=output.getvalue(),
            filled_scalars=filled_scalars,
            filled_tables=filled_tables,
            missing_scalars=missing_scalars,
            missing_tables=missing_tables,
        )

    def _expand_excel_marker_loop(
        self, wb, tfield: TableField, rows: List[Dict]
    ) -> tuple[bool, Optional[str]]:
        """Expand vertical marker table without deleting the template row after fill."""
        anchor = tfield.anchor
        if not anchor or not anchor.marker:
            return False, None
        loop_tokens = anchor.marker.loop_tokens
        if not loop_tokens:
            return False, None
        if tfield.orientation != Orientation.VERTICAL:
            return False, f"Failed to fill table '{tfield.key}': horizontal table fill is not implemented yet"

        sheet_name = anchor.sheet
        if sheet_name and sheet_name not in wb.sheetnames:
            return False, f"Failed to fill table '{tfield.key}': sheet '{sheet_name}' not found"

        sheets = [wb[sheet_name]] if sheet_name else [wb[s] for s in wb.sheetnames]

        for sheet in sheets:
            marker_row_idx = None
            for idx, row in enumerate(sheet.iter_rows(), start=1):
                for cell in row:
                    if cell.value and isinstance(cell.value, str):
                        if any(tok in cell.value for tok in loop_tokens):
                            marker_row_idx = idx
                            break
                if marker_row_idx:
                    break

            if not marker_row_idx:
                continue

            template_row = list(sheet.iter_rows(min_row=marker_row_idx, max_row=marker_row_idx))[0]
            template_values = [cell.value for cell in template_row]
            template_cells = list(template_row)
            template_dimension = sheet.row_dimensions[marker_row_idx]
            template_height = template_dimension.height
            template_hidden = template_dimension.hidden
            rows = list(rows or [])

            if not rows:
                self._write_excel_row(
                    sheet,
                    marker_row_idx,
                    template_values,
                    template_cells,
                    {},
                    table_key=tfield.key,
                    cleanup_only=True,
                )
                return True, None

            for offset, row_data in enumerate(rows[:-1]):
                target_row_idx = marker_row_idx + offset
                sheet.insert_rows(target_row_idx)
                self._copy_excel_row_template(sheet, template_cells, target_row_idx, template_height, template_hidden)
                self._write_excel_row(
                    sheet,
                    target_row_idx,
                    template_values,
                    template_cells,
                    row_data,
                    table_key=tfield.key,
                )

            self._write_excel_row(
                sheet,
                marker_row_idx + len(rows) - 1,
                template_values,
                template_cells,
                rows[-1],
                table_key=tfield.key,
            )
            final_dimension = sheet.row_dimensions[marker_row_idx + len(rows) - 1]
            if template_height is not None:
                final_dimension.height = template_height
            final_dimension.hidden = template_hidden
            return True, None

        return False, (
            f"Failed to fill table '{tfield.key}': marker row not found for tokens {loop_tokens}"
        )

    def _expand_excel_structural(
        self, wb, tfield: TableField, rows: List[Dict]
    ) -> tuple[bool, Optional[str]]:
        """Expand table using structural anchor (header signature)."""
        anchor = tfield.anchor
        if not anchor or not anchor.structural:
            return False, None
        header_sig = anchor.structural.header_signature
        if not header_sig:
            return False, None
        if tfield.orientation != Orientation.VERTICAL:
            return False, f"Failed to fill table '{tfield.key}': horizontal table fill is not implemented yet"

        sheet_name = anchor.sheet
        if sheet_name and sheet_name not in wb.sheetnames:
            return False, f"Failed to fill table '{tfield.key}': sheet '{sheet_name}' not found"

        sheets = [wb[sheet_name]] if sheet_name else [wb[s] for s in wb.sheetnames]

        for sheet in sheets:
            # Find header row by signature matching
            header_row_idx = None
            for idx, row in enumerate(sheet.iter_rows(), start=1):
                row_texts = [str(cell.value or "") for cell in row[:len(header_sig)]]
                match_type = anchor.structural.match if anchor.structural else "exact"
                if match_type == "exact":
                    if row_texts == list(header_sig):
                        header_row_idx = idx
                        break
                else:
                    # Fuzzy match
                    if all(any(sig in txt for txt in row_texts) for sig in header_sig):
                        header_row_idx = idx
                        break

            if not header_row_idx:
                continue

            # Determine template row (first after header by default)
            template_row_idx = header_row_idx + 1
            if template_row_idx > sheet.max_row:
                return False, f"Failed to fill table '{tfield.key}': template row after header is missing"

            # Get template row
            template_row = list(sheet.iter_rows(min_row=template_row_idx, max_row=template_row_idx))[0]
            template_values = [cell.value for cell in template_row]

            # Map columns from header to column indices
            header_row = list(sheet.iter_rows(min_row=header_row_idx, max_row=header_row_idx))[0]
            header_values = [str(cell.value or "") for cell in header_row]

            col_indices = {}
            for col in tfield.columns:
                for idx, hv in enumerate(header_values):
                    if col.label.lower() in hv.lower() or col.key.lower() in hv.lower():
                        col_indices[col.key] = idx
                        break
            missing_columns = [col.key for col in tfield.columns if col.key not in col_indices]
            if missing_columns:
                return False, (
                    f"Failed to fill table '{tfield.key}': structural header mapping is incomplete "
                    f"for columns {missing_columns}"
                )

            template_row = list(sheet.iter_rows(min_row=template_row_idx, max_row=template_row_idx))[0]
            template_values = [cell.value for cell in template_row]
            template_cells = list(template_row)
            template_dimension = sheet.row_dimensions[template_row_idx]
            template_height = template_dimension.height
            template_hidden = template_dimension.hidden
            rows = list(rows or [])

            if not rows:
                self._copy_excel_row_template(sheet, template_cells, template_row_idx, template_height, template_hidden)
                for col in tfield.columns:
                    idx = col_indices[col.key]
                    if idx < len(template_cells):
                        sheet.cell(row=template_row_idx, column=idx + 1).value = None
                return True, None

            for offset, row_data in enumerate(rows[:-1]):
                target_row_idx = template_row_idx + offset
                sheet.insert_rows(target_row_idx)
                self._copy_excel_row_template(sheet, template_cells, target_row_idx, template_height, template_hidden)
                self._write_excel_structural_row(sheet, target_row_idx, row_data, tfield, col_indices)

            self._write_excel_structural_row(
                sheet,
                template_row_idx + len(rows) - 1,
                rows[-1],
                tfield,
                col_indices,
            )
            final_dimension = sheet.row_dimensions[template_row_idx + len(rows) - 1]
            if template_height is not None:
                final_dimension.height = template_height
            final_dimension.hidden = template_hidden
            return True, None

        return False, (
            f"Failed to fill table '{tfield.key}': structural header row not found for signature {header_sig}"
        )

    def _fill_docx(self, template_bytes: bytes, values: Dict[str, Any]) -> FillResult:
        """Fill Word template with scalar and table expansion."""
        try:
            from docx import Document
        except ImportError:
            return FillResult(success=False, error="python-docx not available")

        try:
            doc = Document(io.BytesIO(template_bytes))
        except Exception as e:
            return FillResult(success=False, error=f"Failed to load DOCX: {e}")

        filled_scalars = []
        filled_tables = []
        missing_scalars = []
        missing_tables = []

        scalar_map = {
            field.key: _lookup_nested_value(values, field.key)
            for field in self.contract.scalar_fields()
        }
        used_scalar_keys: set[str] = set()
        for para in doc.paragraphs:
            if para.text:
                new_text, keys = _substitute_placeholders(para.text, scalar_map)
                if new_text != para.text:
                    para.clear()
                    para.add_run(new_text)
                    used_scalar_keys.update(keys)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text:
                        new_text, keys = _substitute_placeholders(cell.text, scalar_map)
                        if new_text != cell.text and cell.paragraphs:
                            cell.paragraphs[0].clear()
                            cell.paragraphs[0].add_run(new_text)
                            used_scalar_keys.update(keys)
        filled_scalars.extend(sorted(used_scalar_keys))
        for field in self.contract.scalar_fields():
            if field.key not in used_scalar_keys and _lookup_nested_value(values, field.key) in (None, ""):
                missing_scalars.append(field.key)

        # Fill tables (marker-loop only for docx)
        for tfield in self.contract.table_fields():
            table_key = tfield.key
            if table_key not in values:
                missing_tables.append(table_key)
                continue
            rows = values[table_key]
            if not isinstance(rows, list):
                missing_tables.append(table_key)
                continue
            if tfield.orientation != Orientation.VERTICAL:
                return FillResult(
                    success=False,
                    error=f"Failed to fill table '{table_key}': horizontal table fill is not implemented yet",
                )

            marker_start = f"{{{{#{table_key}}}}}"
            marker_end = f"{{{{/{table_key}}}}}"

            # Find table containing markers
            for table in doc.tables:
                start_row = None
                end_row = None
                for idx, row in enumerate(table.rows):
                    row_text = " ".join(cell.text for cell in row.cells)
                    if marker_start in row_text:
                        start_row = idx
                    if marker_end in row_text:
                        end_row = idx
                        break

                if start_row is not None and end_row is not None:
                    # Get template row (row after start marker)
                    template_idx = start_row + 1
                    if template_idx >= len(table.rows) or template_idx >= end_row:
                        return FillResult(
                            success=False,
                            error=f"Failed to fill table '{table_key}': template row between table markers is missing",
                        )

                    template_row = table.rows[template_idx]
                    rows = list(rows or [])

                    for offset, row_data in enumerate(rows[:-1]):
                        inserted_row = self._clone_docx_row_before(table, template_idx + offset, template_row)
                        self._write_docx_table_row(inserted_row, row_data, table_key)

                    if rows:
                        self._write_docx_table_row(table.rows[template_idx + len(rows) - 1], rows[-1], table_key)
                    else:
                        self._write_docx_table_row(template_row, {}, table_key, cleanup_only=True)

                    self._remove_docx_row(table.rows[start_row])
                    end_row_after_start_removal = end_row - 1 + len(rows[:-1])
                    self._remove_docx_row(table.rows[end_row_after_start_removal])

                    filled_tables.append(table_key)
                    break
            else:
                missing_tables.append(table_key)

        output = io.BytesIO()
        doc.save(output)
        total_filled = len(filled_scalars) + len(filled_tables)
        if total_filled == 0:
            return FillResult(
                success=False,
                error="No placeholders were filled. Verify values keys against template schema before calling fill.",
                missing_scalars=missing_scalars,
                missing_tables=missing_tables,
            )

        return FillResult(
            success=True,
            content=output.getvalue(),
            filled_scalars=filled_scalars,
            filled_tables=filled_tables,
            missing_scalars=missing_scalars,
            missing_tables=missing_tables,
        )

    def _clone_docx_row_before(self, table, row_index: int, template_row):
        cloned_tr = deepcopy(template_row._tr)
        target_row = table.rows[row_index]
        target_row._tr.addprevious(cloned_tr)
        return table.rows[row_index]

    def _remove_docx_row(self, row) -> None:
        tr = row._tr
        tr.getparent().remove(tr)

    def _write_docx_table_row(self, row, row_data: Dict[str, Any], table_key: str, *, cleanup_only: bool = False) -> None:
        row_values = _table_row_values(table_key, row_data)
        for cell in row.cells:
            if not cell.paragraphs:
                continue
            original_text = "\n".join(paragraph.text for paragraph in cell.paragraphs)
            filled_text, _ = _substitute_placeholders(original_text, row_values)
            final_text = _clear_placeholder_tokens(filled_text) if cleanup_only or filled_text != original_text else filled_text
            self._replace_docx_cell_text(cell, final_text)

    def _replace_docx_cell_text(self, cell, text: str) -> None:
        paragraphs = list(cell.paragraphs)
        if not paragraphs:
            cell.text = text
            return
        paragraphs[0].clear()
        paragraphs[0].add_run(text)
        for paragraph in paragraphs[1:]:
            p = paragraph._element
            p.getparent().remove(p)

    def _copy_excel_row_template(self, sheet, template_cells, target_row_idx: int, template_height: Any, template_hidden: Any) -> None:
        target_dimension = sheet.row_dimensions[target_row_idx]
        if template_height is not None:
            target_dimension.height = template_height
        target_dimension.hidden = template_hidden
        for template_cell in template_cells:
            target_cell = sheet.cell(row=target_row_idx, column=template_cell.column)
            if template_cell.has_style:
                target_cell._style = copy(template_cell._style)
            if template_cell.number_format:
                target_cell.number_format = copy(template_cell.number_format)
            if template_cell.font:
                target_cell.font = copy(template_cell.font)
            if template_cell.fill:
                target_cell.fill = copy(template_cell.fill)
            if template_cell.border:
                target_cell.border = copy(template_cell.border)
            if template_cell.alignment:
                target_cell.alignment = copy(template_cell.alignment)
            if template_cell.protection:
                target_cell.protection = copy(template_cell.protection)

    def _write_excel_row(
        self,
        sheet,
        row_idx: int,
        template_values: List[Any],
        template_cells: List[Any],
        row_data: Dict[str, Any],
        *,
        table_key: str,
        cleanup_only: bool = False,
    ) -> None:
        row_values = _table_row_values(table_key, row_data)
        for template_cell, template_val in zip(template_cells, template_values):
            target_cell = sheet.cell(row=row_idx, column=template_cell.column)
            if template_val and isinstance(template_val, str):
                filled_val, _ = _substitute_placeholders(template_val, row_values)
                target_cell.value = _clear_placeholder_tokens(filled_val)
            else:
                target_cell.value = template_val

    def _write_excel_structural_row(self, sheet, row_idx: int, row_data: Dict[str, Any], tfield: TableField, col_indices: Dict[str, int]) -> None:
        for col in tfield.columns:
            idx = col_indices[col.key]
            target_cell = sheet.cell(row=row_idx, column=idx + 1)
            target_cell.value = _lookup_nested_value(row_data, col.key)


def _substitute_placeholders(text: str, values: Dict[str, Any]) -> Tuple[str, set[str]]:
    used_keys: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        parsed = _parse_placeholder_expr(match.group(1))
        if not parsed:
            return match.group(0)
        key, _, _, _ = parsed
        value = _lookup_nested_value(values, key)
        if value in (None, ""):
            return match.group(0)
        used_keys.add(key)
        return str(value)

    return re.sub(r"\{\{([^{}]+)\}\}", _replace, text), used_keys


def _clear_placeholder_tokens(text: str) -> str:
    return re.sub(r"\{\{[^{}]+\}\}", "", text)


def _table_row_values(prefix: str, row_data: Dict[str, Any]) -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                next_path = f"{path}.{key}" if path else str(key)
                _walk(value, next_path)
            return
        flattened[path] = node

    _walk(row_data or {}, "")
    if prefix:
        return {
            f"{prefix}.{key}": value
            for key, value in flattened.items()
            if key
        }
    return flattened


def _lookup_nested_value(values: Dict[str, Any], key: str) -> Any:
    if key in values:
        return values.get(key)
    current: Any = values
    for segment in key.split("."):
        if not isinstance(current, dict) or segment not in current:
            return ""
        current = current.get(segment)
    return current
