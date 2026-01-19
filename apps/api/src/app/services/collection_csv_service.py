"""
CSV upload service for collections
"""
import csv
import io
import uuid
from typing import List, Tuple, Optional, Any
from datetime import datetime, date

from app.models.collection import Collection, FieldType


class CSVValidationError(Exception):
    """CSV validation failed"""
    def __init__(self, message: str, errors: List[dict] = None):
        super().__init__(message)
        self.errors = errors or []


class CollectionCSVService:
    """Service for parsing and validating CSV data for collections"""

    def __init__(self, collection: Collection):
        self.collection = collection
        self.field_map = {f["name"]: f for f in collection.fields}
        self.required_fields = {
            f["name"] for f in collection.fields if f.get("required", False)
        }

    def _parse_value(self, value: str, field_type: str) -> Any:
        """Parse string value to appropriate Python type"""
        if value is None or value.strip() == "":
            return None

        value = value.strip()

        if field_type == FieldType.TEXT.value:
            return value

        if field_type == FieldType.INTEGER.value:
            try:
                return int(value)
            except ValueError:
                raise ValueError(f"Cannot parse '{value}' as integer")

        if field_type == FieldType.FLOAT.value:
            try:
                return float(value)
            except ValueError:
                raise ValueError(f"Cannot parse '{value}' as float")

        if field_type == FieldType.BOOLEAN.value:
            lower = value.lower()
            if lower in ("true", "1", "yes", "да"):
                return True
            if lower in ("false", "0", "no", "нет"):
                return False
            raise ValueError(f"Cannot parse '{value}' as boolean")

        if field_type == FieldType.DATETIME.value:
            for fmt in [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%d.%m.%Y %H:%M:%S",
                "%d.%m.%Y",
            ]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse '{value}' as datetime")

        if field_type == FieldType.DATE.value:
            for fmt in ["%Y-%m-%d", "%d.%m.%Y"]:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse '{value}' as date")

        return value

    def parse_csv(
        self,
        content: bytes,
        encoding: str = "utf-8",
        delimiter: str = ",",
    ) -> Tuple[List[dict], List[dict]]:
        """
        Parse CSV content and validate against collection schema.
        
        Args:
            content: Raw CSV bytes
            encoding: File encoding
            delimiter: CSV delimiter
        
        Returns:
            Tuple of (valid_rows, errors)
            - valid_rows: List of parsed row dicts
            - errors: List of error dicts with row_number, field, message
        """
        try:
            text_content = content.decode(encoding)
        except UnicodeDecodeError:
            try:
                text_content = content.decode("cp1251")
            except UnicodeDecodeError:
                raise CSVValidationError("Cannot decode file. Try UTF-8 or CP1251 encoding.")

        reader = csv.DictReader(io.StringIO(text_content), delimiter=delimiter)

        if not reader.fieldnames:
            raise CSVValidationError("CSV file is empty or has no headers")

        csv_columns = set(reader.fieldnames)
        schema_columns = set(self.field_map.keys())

        missing_required = self.required_fields - csv_columns
        if missing_required:
            raise CSVValidationError(
                f"Missing required columns: {', '.join(sorted(missing_required))}"
            )

        valid_rows = []
        errors = []

        for row_num, row in enumerate(reader, start=2):
            parsed_row = {}
            row_errors = []

            for field_name, field_def in self.field_map.items():
                raw_value = row.get(field_name)

                if raw_value is None or raw_value.strip() == "":
                    if field_def.get("required", False):
                        row_errors.append({
                            "row": row_num,
                            "field": field_name,
                            "message": "Required field is empty",
                        })
                    else:
                        parsed_row[field_name] = None
                    continue

                try:
                    parsed_row[field_name] = self._parse_value(
                        raw_value, field_def["type"]
                    )
                except ValueError as e:
                    row_errors.append({
                        "row": row_num,
                        "field": field_name,
                        "message": str(e),
                    })

            if row_errors:
                errors.extend(row_errors)
            else:
                valid_rows.append(parsed_row)

        return valid_rows, errors

    def preview_csv(
        self,
        content: bytes,
        max_rows: int = 10,
        encoding: str = "utf-8",
        delimiter: str = ",",
    ) -> dict:
        """
        Preview CSV file without full validation.
        
        Returns:
            {
                "columns": ["col1", "col2"],
                "matched_columns": ["col1"],
                "unmatched_columns": ["col2"],
                "missing_required": ["col3"],
                "sample_rows": [{...}, {...}],
                "total_rows": 100
            }
        """
        try:
            text_content = content.decode(encoding)
        except UnicodeDecodeError:
            try:
                text_content = content.decode("cp1251")
            except UnicodeDecodeError:
                raise CSVValidationError("Cannot decode file")

        reader = csv.DictReader(io.StringIO(text_content), delimiter=delimiter)

        if not reader.fieldnames:
            raise CSVValidationError("CSV file is empty or has no headers")

        csv_columns = set(reader.fieldnames)
        schema_columns = set(self.field_map.keys())

        matched = csv_columns & schema_columns
        unmatched = csv_columns - schema_columns
        missing_required = self.required_fields - csv_columns

        sample_rows = []
        total_rows = 0

        for row in reader:
            total_rows += 1
            if len(sample_rows) < max_rows:
                filtered_row = {k: v for k, v in row.items() if k in schema_columns}
                sample_rows.append(filtered_row)

        return {
            "columns": list(reader.fieldnames),
            "matched_columns": sorted(matched),
            "unmatched_columns": sorted(unmatched),
            "missing_required": sorted(missing_required),
            "sample_rows": sample_rows,
            "total_rows": total_rows,
        }
