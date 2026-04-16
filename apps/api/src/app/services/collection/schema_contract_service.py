from __future__ import annotations

import re
from typing import List

from app.core.exceptions import InvalidSchemaError
from app.models.collection import Collection, CollectionType, FieldCategory, FieldType

VALID_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

DOCUMENT_SPECIFIC_FIELD_DEFS = (
    {
        "name": "file",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.FILE.value,
        "required": True,
        "description": "Document file reference",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
    {
        "name": "title",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.TEXT.value,
        "required": False,
        "description": "Document title",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
    {
        "name": "source",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.STRING.value,
        "required": False,
        "description": "Document source",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
)

SQL_SPECIFIC_FIELD_DEFS = (
    {
        "name": "table_name",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.STRING.value,
        "required": True,
        "description": "SQL table name",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
    {
        "name": "table_schema",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.JSON.value,
        "required": True,
        "description": "SQL table schema",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
)

API_SPECIFIC_FIELD_DEFS = (
    {
        "name": "entity_type",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.STRING.value,
        "required": False,
        "description": "API entity type",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
    {
        "name": "aliases",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.JSON.value,
        "required": False,
        "description": "Entity aliases and synonyms",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
    {
        "name": "examples",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.JSON.value,
        "required": False,
        "description": "Example API responses",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
)

DOCUMENT_SPECIFIC_FIELD_NAMES = {field["name"] for field in DOCUMENT_SPECIFIC_FIELD_DEFS}
SQL_SPECIFIC_FIELD_NAMES = {field["name"] for field in SQL_SPECIFIC_FIELD_DEFS}
API_SPECIFIC_FIELD_NAMES = {field["name"] for field in API_SPECIFIC_FIELD_DEFS}


class CollectionSchemaContractService:
    """Collection schema contract validation and type-owned field presets."""

    @staticmethod
    def get_type_specific_field_presets() -> dict[str, list[dict]]:
        return {
            CollectionType.TABLE.value: [],
            CollectionType.DOCUMENT.value: [dict(field) for field in DOCUMENT_SPECIFIC_FIELD_DEFS],
            CollectionType.SQL.value: [dict(field) for field in SQL_SPECIFIC_FIELD_DEFS],
            CollectionType.API.value: [],
        }

    @property
    def document_specific_field_names(self) -> set[str]:
        return DOCUMENT_SPECIFIC_FIELD_NAMES

    @property
    def sql_specific_field_names(self) -> set[str]:
        return SQL_SPECIFIC_FIELD_NAMES

    @property
    def api_specific_field_names(self) -> set[str]:
        return API_SPECIFIC_FIELD_NAMES

    def validate_slug(self, slug: str) -> None:
        if not slug or len(slug) > 50:
            raise InvalidSchemaError("Slug must be 1-50 characters")
        if not VALID_SLUG_PATTERN.match(slug):
            raise InvalidSchemaError(
                "Slug must start with letter, contain only lowercase letters, numbers, underscores"
            )

    def validate_fields(self, fields: List[dict], collection_type: str) -> None:
        local_types_requiring_fields = {CollectionType.TABLE.value, CollectionType.SQL.value}
        if collection_type in local_types_requiring_fields and not fields:
            raise InvalidSchemaError("At least one field is required for table collections")

        field_names = set()
        reserved_names = {
            "id",
            "_created_at",
            "_updated_at",
            "_vector_status",
            "_vector_chunk_count",
            "_vector_error",
        }

        for field in fields:
            name = field.get("name")
            if not name:
                raise InvalidSchemaError("Field name is required")

            if not re.match(r"^[a-z][a-z0-9_]*$", name):
                raise InvalidSchemaError(
                    f"Field '{name}' must start with letter, contain only lowercase letters, numbers, underscores"
                )

            if name in reserved_names:
                raise InvalidSchemaError(f"Field name '{name}' is reserved")

            if name in field_names:
                raise InvalidSchemaError(f"Duplicate field name: {name}")
            field_names.add(name)

            category = field.get("category")
            if category not in {fc.value for fc in FieldCategory}:
                raise InvalidSchemaError(f"Invalid field category '{category}' for field '{name}'")
            if category == FieldCategory.SYSTEM.value:
                raise InvalidSchemaError(
                    f"System field '{name}' is platform-owned and must not be declared in collection schema"
                )
            if (
                collection_type == CollectionType.DOCUMENT.value
                and category == FieldCategory.USER.value
                and name in DOCUMENT_SPECIFIC_FIELD_NAMES
            ):
                raise InvalidSchemaError(
                    f"Field name '{name}' is reserved for document-specific immutable fields"
                )

            field_type = field.get("data_type")
            if field_type not in [ft.value for ft in FieldType]:
                raise InvalidSchemaError(
                    f"Invalid field data_type '{field_type}' for field '{name}'"
                )

            filterable = bool(field.get("filterable", False))
            sortable = bool(field.get("sortable", False))
            used_in_retrieval = bool(field.get("used_in_retrieval", False))
            used_in_prompt_context = bool(field.get("used_in_prompt_context", False))

            if field_type == FieldType.FILE.value and (filterable or sortable or used_in_prompt_context):
                raise InvalidSchemaError(
                    f"Field '{name}': file fields cannot be filterable, sortable, or prompt-visible"
                )

            if used_in_retrieval and field_type != FieldType.TEXT.value:
                raise InvalidSchemaError(
                    f"Field '{name}': used_in_retrieval is only available for text fields"
                )

            if sortable and field_type in (FieldType.FILE.value, FieldType.JSON.value):
                raise InvalidSchemaError(
                    f"Field '{name}': sortable is not valid for data_type '{field_type}'"
                )

            if category == FieldCategory.SPECIFIC.value and (
                filterable or sortable or used_in_prompt_context or used_in_retrieval
            ):
                raise InvalidSchemaError(
                    f"Field '{name}': specific fields cannot be filterable, sortable, retrieval-enabled, or prompt-visible"
                )

    def validate_admin_defined_fields(self, fields: List[dict], collection_type: str) -> None:
        for field in fields:
            category = field.get("category", FieldCategory.USER.value)
            if category not in {FieldCategory.USER.value, FieldCategory.SPECIFIC.value}:
                raise InvalidSchemaError(
                    f"Field '{field.get('name', '<unknown>')}' must use category 'user' or 'specific'"
                )
            if collection_type == CollectionType.DOCUMENT.value and field.get("name") in DOCUMENT_SPECIFIC_FIELD_NAMES:
                raise InvalidSchemaError(
                    f"Field name '{field['name']}' is reserved for document-specific immutable fields"
                )
            if collection_type == CollectionType.SQL.value and field.get("name") in SQL_SPECIFIC_FIELD_NAMES:
                raise InvalidSchemaError(
                    f"Field name '{field['name']}' is reserved for sql-specific immutable fields"
                )
            if collection_type == CollectionType.API.value and field.get("name") in API_SPECIFIC_FIELD_NAMES:
                raise InvalidSchemaError(
                    f"Field name '{field['name']}' is reserved for api-specific immutable fields"
                )

    def ensure_document_preset_fields(self, fields: List[dict]) -> List[dict]:
        field_names = {f.get("name") for f in fields}
        result = list(fields)
        for preset_field in reversed(DOCUMENT_SPECIFIC_FIELD_DEFS):
            if preset_field["name"] not in field_names:
                result.insert(0, dict(preset_field))
                field_names.add(preset_field["name"])
        return result

    def ensure_sql_preset_fields(self, fields: List[dict]) -> List[dict]:
        field_names = {f.get("name") for f in fields}
        result = list(fields)
        for preset_field in reversed(SQL_SPECIFIC_FIELD_DEFS):
            if preset_field["name"] not in field_names:
                result.insert(0, dict(preset_field))
                field_names.add(preset_field["name"])
        return result

    def ensure_api_preset_fields(self, fields: List[dict]) -> List[dict]:
        # API collections no longer auto-inject specific fields.
        return list(fields)

    def normalize_default_sort(self, collection: Collection, fields: List[dict]) -> None:
        sortable_fields = {field["name"] for field in fields if field.get("sortable", False)}
        field_types = {field["name"]: field["data_type"] for field in fields}

        if collection.default_sort:
            field_name = collection.default_sort.get("field")
            if field_name not in sortable_fields:
                collection.default_sort = None

        if collection.time_column:
            field_type = field_types.get(collection.time_column)
            if field_type not in {FieldType.DATETIME.value, FieldType.DATE.value}:
                collection.time_column = None
