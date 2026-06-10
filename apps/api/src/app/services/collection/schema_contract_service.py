from __future__ import annotations

import re
import unicodedata
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

TEMPLATE_SPECIFIC_FIELD_DEFS = (
    {
        "name": "file",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.FILE.value,
        "required": True,
        "description": "Template file reference",
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
        "description": "Template title extracted from headers",
        "filterable": True,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": True,
    },
    {
        "name": "source",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.STRING.value,
        "required": True,
        "description": "Template source reference",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
    {
        "name": "template_version",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.STRING.value,
        "required": False,
        "description": "Template version extracted from headers",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
    {
        "name": "template_schema",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.JSON.value,
        "required": False,
        "description": "Structured schema for template filling",
        "filterable": False,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
    {
        "name": "description",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.TEXT.value,
        "required": False,
        "description": "Template description for semantic discovery",
        "filterable": True,
        "sortable": False,
        "used_in_retrieval": True,
        "used_in_prompt_context": True,
    },
    {
        "name": "status",
        "category": FieldCategory.SPECIFIC.value,
        "data_type": FieldType.STRING.value,
        "required": True,
        "description": "Template lifecycle status",
        "filterable": True,
        "sortable": False,
        "used_in_retrieval": False,
        "used_in_prompt_context": False,
    },
)

TEMPLATE_SPECIFIC_FIELD_NAMES = {field["name"] for field in TEMPLATE_SPECIFIC_FIELD_DEFS}


class CollectionSchemaContractService:
    """Collection schema contract validation and type-owned field presets."""

    @staticmethod
    def get_type_specific_field_presets() -> dict[str, list[dict]]:
        return {
            CollectionType.TABLE.value: [],
            CollectionType.DOCUMENT.value: [dict(field) for field in DOCUMENT_SPECIFIC_FIELD_DEFS],
            CollectionType.SQL.value: [dict(field) for field in SQL_SPECIFIC_FIELD_DEFS],
            CollectionType.API.value: [],
            CollectionType.TEMPLATE.value: [dict(field) for field in TEMPLATE_SPECIFIC_FIELD_DEFS],
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

    @property
    def template_specific_field_names(self) -> set[str]:
        return TEMPLATE_SPECIFIC_FIELD_NAMES

    @staticmethod
    def get_specific_field_names(collection_type: str) -> set[str]:
        return {
            CollectionType.DOCUMENT.value: DOCUMENT_SPECIFIC_FIELD_NAMES,
            CollectionType.SQL.value: SQL_SPECIFIC_FIELD_NAMES,
            CollectionType.API.value: API_SPECIFIC_FIELD_NAMES,
            CollectionType.TEMPLATE.value: TEMPLATE_SPECIFIC_FIELD_NAMES,
        }.get(collection_type, set())

    def validate_slug(self, slug: str) -> None:
        if not slug or len(slug) > 50:
            raise InvalidSchemaError("Slug must be 1-50 characters")
        if not VALID_SLUG_PATTERN.match(slug):
            raise InvalidSchemaError(
                "Slug must start with letter, contain only lowercase letters, numbers, underscores"
            )

    def slugify_name(self, name: str, *, fallback: str = "collection") -> str:
        raw = str(name or "").strip().lower()
        if not raw:
            return fallback

        cyr_map = {
            "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
            "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
            "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
            "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
            "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
        }
        transliterated = "".join(cyr_map.get(ch, ch) for ch in raw)
        ascii_text = (
            unicodedata.normalize("NFKD", transliterated)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        normalized = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
        normalized = re.sub(r"_+", "_", normalized)

        if not normalized:
            normalized = fallback
        if not re.match(r"^[a-z]", normalized):
            normalized = f"{fallback}_{normalized}" if normalized else fallback
        return normalized[:50]

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
            specific_names = self.get_specific_field_names(collection_type)
            if category == FieldCategory.USER.value and name in specific_names:
                raise InvalidSchemaError(
                    f"Field name '{name}' is reserved for {collection_type}-specific immutable fields"
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

            if used_in_retrieval and field_type != FieldType.TEXT.value:
                raise InvalidSchemaError(
                    f"Field '{name}': used_in_retrieval is only available for text fields"
                )

            if sortable and field_type in (FieldType.FILE.value, FieldType.JSON.value):
                raise InvalidSchemaError(
                    f"Field '{name}': sortable is not valid for data_type '{field_type}'"
                )

    def validate_admin_defined_fields(self, fields: List[dict], collection_type: str) -> None:
        specific_names = self.get_specific_field_names(collection_type)
        for field in fields:
            category = field.get("category", FieldCategory.USER.value)
            if category not in {FieldCategory.USER.value, FieldCategory.SPECIFIC.value}:
                raise InvalidSchemaError(
                    f"Field '{field.get('name', '<unknown>')}' must use category 'user' or 'specific'"
                )
            if field.get("name") in specific_names:
                raise InvalidSchemaError(
                    f"Field name '{field['name']}' is reserved for {collection_type}-specific immutable fields"
                )

    def ensure_document_preset_fields(self, fields: List[dict]) -> List[dict]:
        return self._merge_preset_fields(fields, DOCUMENT_SPECIFIC_FIELD_DEFS)

    def ensure_sql_preset_fields(self, fields: List[dict]) -> List[dict]:
        return self._merge_preset_fields(fields, SQL_SPECIFIC_FIELD_DEFS)

    def ensure_api_preset_fields(self, fields: List[dict]) -> List[dict]:
        # API collections no longer auto-inject specific fields.
        return list(fields)

    def ensure_template_preset_fields(self, fields: List[dict]) -> List[dict]:
        sanitized = [
            dict(field)
            for field in fields
            if field.get("name") not in {"template_kind", "semantic_description", "description_error", "schema_error"}
        ]
        return self._merge_preset_fields(sanitized, TEMPLATE_SPECIFIC_FIELD_DEFS)

    @staticmethod
    def _merge_preset_fields(fields: List[dict], preset_fields: tuple[dict, ...]) -> List[dict]:
        by_name = {field.get("name"): dict(field) for field in fields}
        preset_names = {field["name"] for field in preset_fields}
        result: list[dict] = []

        for preset_field in preset_fields:
            existing = by_name.pop(preset_field["name"], None)
            if existing is None:
                result.append(dict(preset_field))
            else:
                result.append({**existing, **preset_field})

        for field in fields:
            if field.get("name") not in preset_names:
                result.append(dict(field))

        return result

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
