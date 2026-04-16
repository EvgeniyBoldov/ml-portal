"""
CSV upload service for collections
"""
import csv
import io
from typing import List, Tuple, Any

from app.models.collection import Collection
from app.core.exceptions import CSVValidationError
from app.services.collection.field_coercion import coerce_value


class CollectionCSVService:
    """Service for parsing and validating CSV data for collections"""

    def __init__(self, collection: Collection):
        self.collection = collection
        self.field_map = {f["name"]: f for f in collection.fields}
        self.required_fields = {
            f["name"] for f in collection.fields if f.get("required", False)
        }

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
                    parsed_row[field_name] = coerce_value(
                        field_name, field_def["data_type"], raw_value
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
