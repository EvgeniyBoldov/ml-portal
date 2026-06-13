"""S4 TemplateFillEngine — fill templates with contract validation.

Supports:
- Scalar field substitution ({{key}})
- Table expansion via marker-loop ({{#table}}..{{/table}})
- Table expansion via structural anchor (header_signature matching)
- Excel, Docx, Text formats
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from app.services.collection.template_contract import (
    AnchorStrategy,
    DocumentFormat,
    ScalarField,
    TableAnchor,
    TableField,
    TemplateContract,
    ValidationReport,
)

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

    def fill(self, template_bytes: bytes, values: Dict[str, Any], filename: str) -> FillResult:
        """Fill template with validated values."""
        # Validate values against contract
        report = self.contract.validate_values(values)
        if not report.ok:
            return FillResult(success=False, error=f"Validation failed: {report.errors}")

        fmt = self._detect_format(filename)
        if fmt == DocumentFormat.EXCEL:
            return self._fill_excel(template_bytes, values)
        elif fmt == DocumentFormat.DOCX:
            return self._fill_docx(template_bytes, values)
        else:
            return self._fill_text(template_bytes, values)

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

        filled = []
        missing = []

        for field in self.contract.scalar_fields():
            key = field.key
            token = f"{{{{{key}}}}}"
            if key in values:
                text = text.replace(token, str(values[key]))
                filled.append(key)
            else:
                missing.append(key)

        # Simple table handling for text (no row expansion, just markers)
        for tfield in self.contract.table_fields():
            table_key = tfield.key
            if table_key not in values:
                missing.append(table_key)
                continue
            rows = values[table_key]
            if not isinstance(rows, list):
                missing.append(table_key)
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
                filled.append(table_key)
            else:
                # No markers - simple column substitution won't work for multiple rows
                missing.append(table_key)

        return FillResult(
            success=True,
            content=text.encode('utf-8'),
            filled_scalars=filled,
            missing_scalars=missing,
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

        # Fill scalars
        for field in self.contract.scalar_fields():
            key = field.key
            token = f"{{{{{key}}}}}"
            found = False
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.value and isinstance(cell.value, str) and token in cell.value:
                            if key in values:
                                cell.value = cell.value.replace(token, str(values[key]))
                                found = True
                            else:
                                missing_scalars.append(key)
            if found and key in values:
                filled_scalars.append(key)

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
                if self._expand_excel_marker_loop(wb, tfield, rows):
                    filled_tables.append(table_key)
                else:
                    missing_tables.append(table_key)
            elif anchor and anchor.strategy == AnchorStrategy.STRUCTURAL and anchor.structural:
                # Structural strategy
                if self._expand_excel_structural(wb, tfield, rows):
                    filled_tables.append(table_key)
                else:
                    missing_tables.append(table_key)
            else:
                # Auto - try marker first, then structural
                if self._expand_excel_marker_loop(wb, tfield, rows):
                    filled_tables.append(table_key)
                elif self._expand_excel_structural(wb, tfield, rows):
                    filled_tables.append(table_key)
                else:
                    missing_tables.append(table_key)

        output = io.BytesIO()
        wb.save(output)
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
    ) -> bool:
        """Expand table using marker-loop strategy. Returns True if successful."""
        anchor = tfield.anchor
        if not anchor or not anchor.marker:
            return False
        loop_tokens = anchor.marker.loop_tokens
        if not loop_tokens:
            return False

        sheet_name = anchor.sheet
        if sheet_name and sheet_name not in wb.sheetnames:
            return False

        sheets = [wb[sheet_name]] if sheet_name else [wb[s] for s in wb.sheetnames]

        for sheet in sheets:
            # Find marker row
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

            # Get template row values
            template_row = list(sheet.iter_rows(min_row=marker_row_idx, max_row=marker_row_idx))[0]
            template_values = [cell.value for cell in template_row]

            # Delete marker row (it becomes first data row)
            sheet.delete_rows(marker_row_idx)

            # Insert rows for each data row (in reverse to maintain order)
            for row_data in reversed(rows):
                sheet.insert_rows(marker_row_idx)
                new_row = list(sheet.iter_rows(min_row=marker_row_idx, max_row=marker_row_idx))[0]
                for cell, template_val in zip(new_row, template_values):
                    if template_val and isinstance(template_val, str):
                        filled_val = template_val
                        for col in tfield.columns:
                            col_token = f"{{{{{tfield.key}.{col.key}}}}}"
                            if col_token in filled_val:
                                filled_val = filled_val.replace(col_token, str(row_data.get(col.key, "")))
                        cell.value = filled_val

            return True

        return False

    def _expand_excel_structural(
        self, wb, tfield: TableField, rows: List[Dict]
    ) -> bool:
        """Expand table using structural anchor (header signature)."""
        anchor = tfield.anchor
        if not anchor or not anchor.structural:
            return False
        header_sig = anchor.structural.header_signature
        if not header_sig:
            return False

        sheet_name = anchor.sheet
        if sheet_name and sheet_name not in wb.sheetnames:
            return False

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
                continue

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

            # Clear/delete template row
            sheet.delete_rows(template_row_idx)

            # Insert rows for data
            for row_data in reversed(rows):
                sheet.insert_rows(template_row_idx)
                new_row = list(sheet.iter_rows(min_row=template_row_idx, max_row=template_row_idx))[0]
                for col in tfield.columns:
                    if col.key in col_indices:
                        idx = col_indices[col.key]
                        if idx < len(new_row):
                            new_row[idx].value = row_data.get(col.key, "")

            return True

        return False

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

        # Fill scalars in paragraphs
        for field in self.contract.scalar_fields():
            key = field.key
            token = f"{{{{{key}}}}}"
            found = False
            for para in doc.paragraphs:
                if token in para.text:
                    if key in values:
                        for run in para.runs:
                            run.text = run.text.replace(token, str(values[key]))
                        found = True
                    else:
                        missing_scalars.append(key)
            if found and key in values:
                filled_scalars.append(key)

        # Fill scalars in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for field in self.contract.scalar_fields():
                        key = field.key
                        token = f"{{{{{key}}}}}"
                        if token in cell.text:
                            if key in values:
                                for para in cell.paragraphs:
                                    for run in para.runs:
                                        run.text = run.text.replace(token, str(values[key]))
                                filled_scalars.append(key)
                            else:
                                missing_scalars.append(key)

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
                        continue

                    template_row = table.rows[template_idx]
                    template_cells = [cell.text for cell in template_row.cells]

                    # Remove marker rows and template row
                    for _ in range(end_row - start_row + 1):
                        table._element.getparent().remove(table.rows[start_row]._element)

                    # Add rows for data
                    for row_data in rows:
                        new_row = table.add_row()
                        for idx, template_text in enumerate(template_cells):
                            if idx < len(new_row.cells):
                                filled_text = template_text
                                for col in tfield.columns:
                                    col_token = f"{{{{{table_key}.{col.key}}}}}"
                                    if col_token in filled_text:
                                        filled_text = filled_text.replace(col_token, str(row_data.get(col.key, "")))
                                new_row.cells[idx].text = filled_text

                    filled_tables.append(table_key)
                    break
            else:
                missing_tables.append(table_key)

        output = io.BytesIO()
        doc.save(output)
        return FillResult(
            success=True,
            content=output.getvalue(),
            filled_scalars=filled_scalars,
            filled_tables=filled_tables,
            missing_scalars=missing_scalars,
            missing_tables=missing_tables,
        )
