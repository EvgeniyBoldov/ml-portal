from __future__ import annotations

import re
from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidSchemaError
from app.models.collection import Collection, CollectionType


class CollectionSchemaEvolutionService:
    """Controlled schema evolution for user fields of dynamic collections."""

    def __init__(
        self,
        session: AsyncSession,
        host,
        contract,
        *,
        field_type_to_pg: dict[str, str],
    ) -> None:
        self.session = session
        self.host = host
        self.contract = contract
        self.field_type_to_pg = field_type_to_pg
        self.document_specific_field_names = set(contract.document_specific_field_names)

    async def apply_schema_operations(self, collection: Collection, schema_ops: List[dict]) -> None:
        fields = [dict(field) for field in (collection.fields or [])]
        original_fields = [dict(field) for field in fields]
        previous_user_fields = [
            dict(field) for field in fields if field.get("category") == "user"
        ]
        original_vector_signature = self.host._vector_signature(fields)
        original_needs_vector = self.host._fields_require_table_vector_search(fields)

        for op in schema_ops:
            action = op["op"]
            if action == "add":
                fields = await self._schema_add_field(collection, fields, dict(op["field"]))
            elif action == "alter":
                fields = await self._schema_alter_field(collection, fields, op["name"], dict(op["field"]))
            elif action == "rename":
                fields = await self._schema_rename_field(collection, fields, op["name"], op["new_name"])
            elif action == "remove":
                fields = await self._schema_remove_field(collection, fields, op["name"])
            else:
                raise InvalidSchemaError(f"Unsupported schema operation '{action}'")

        self.contract.validate_fields(fields, collection.collection_type)

        current_user_fields = [
            dict(field) for field in fields if field.get("category") == "user"
        ]
        await self.host._rebuild_structural_indexes(
            collection.table_name,
            previous_user_fields,
            current_user_fields,
        )

        collection.fields = fields
        self.contract.normalize_default_sort(collection, fields)

        if collection.collection_type == CollectionType.TABLE.value:
            current_needs_vector = self.host._fields_require_table_vector_search(fields)
            current_vector_signature = self.host._vector_signature(fields)
            vector_schema_changed = original_vector_signature != current_vector_signature
            if vector_schema_changed:
                details = dict(collection.status_details or {})
                details["revectorization_required"] = True
                details["revectorization_reason"] = "vector_schema_changed"
                details["vector_signature_before"] = original_vector_signature
                details["vector_signature_after"] = current_vector_signature
                collection.status_details = details

            if not original_needs_vector and current_needs_vector:
                await self.host._ensure_table_vector_infra(collection)
                await self.host._reset_table_vector_state(collection)
            elif original_needs_vector and not current_needs_vector:
                await self.host._drop_table_vector_infra(collection)
            elif current_needs_vector and vector_schema_changed:
                await self.host._ensure_table_vector_infra(collection)
                await self.host._reset_table_vector_state(collection)

        await self.host.sync_collection_status(collection, persist=False)

        self.host.logger.info(
            "collection_schema_updated",
            extra={
                "collection_id": str(collection.id),
                "collection_slug": collection.slug,
                "operations": [op["op"] for op in schema_ops],
                "original_field_count": len(original_fields),
                "current_field_count": len(fields),
            },
        )

    def _find_field_index(self, fields: List[dict], field_name: str) -> int:
        for idx, field in enumerate(fields):
            if field.get("name") == field_name:
                return idx
        raise InvalidSchemaError(f"Field '{field_name}' not found")

    def _assert_user_field_mutable(self, field: dict, field_name: str) -> None:
        if field.get("category") != "user":
            raise InvalidSchemaError(
                f"Field '{field_name}' is immutable because it is not a user field"
            )

    async def _schema_add_field(
        self,
        collection: Collection,
        fields: List[dict],
        field: dict,
    ) -> List[dict]:
        self.contract.validate_admin_defined_fields([field], collection.collection_type)
        if any(existing.get("name") == field["name"] for existing in fields):
            raise InvalidSchemaError(f"Field '{field['name']}' already exists")

        if field.get("required", False) and await self.host._table_has_rows(collection.table_name):
            raise InvalidSchemaError(
                f"Cannot add required field '{field['name']}' to non-empty collection"
            )

        pg_type = self.field_type_to_pg[field["data_type"]]
        nullable = "NOT NULL" if field.get("required", False) else ""
        await self.session.execute(
            text(
                f"ALTER TABLE {collection.table_name} "
                f"ADD COLUMN {field['name']} {pg_type} {nullable}".strip()
            )
        )
        return fields + [field]

    async def _schema_alter_field(
        self,
        collection: Collection,
        fields: List[dict],
        field_name: str,
        new_field: dict,
    ) -> List[dict]:
        idx = self._find_field_index(fields, field_name)
        existing = dict(fields[idx])
        self._assert_user_field_mutable(existing, field_name)
        self.contract.validate_admin_defined_fields([new_field], collection.collection_type)

        if new_field["name"] != field_name:
            raise InvalidSchemaError("Rename must use a separate rename operation")

        if existing["data_type"] != new_field["data_type"]:
            pg_type = self.field_type_to_pg[new_field["data_type"]]
            try:
                await self.session.execute(
                    text(
                        f"ALTER TABLE {collection.table_name} "
                        f"ALTER COLUMN {field_name} TYPE {pg_type} "
                        f"USING {field_name}::{pg_type}"
                    )
                )
            except Exception as exc:
                raise InvalidSchemaError(
                    f"Field '{field_name}' cannot be converted from {existing['data_type']} to {new_field['data_type']}: {exc}"
                ) from exc

        if not existing.get("required", False) and new_field.get("required", False):
            null_count = await self.host._count_nulls(collection.table_name, field_name)
            if null_count > 0:
                raise InvalidSchemaError(
                    f"Cannot make field '{field_name}' required while {null_count} rows contain NULL"
                )
            await self.session.execute(
                text(
                    f"ALTER TABLE {collection.table_name} "
                    f"ALTER COLUMN {field_name} SET NOT NULL"
                )
            )
        elif existing.get("required", False) and not new_field.get("required", False):
            await self.session.execute(
                text(
                    f"ALTER TABLE {collection.table_name} "
                    f"ALTER COLUMN {field_name} DROP NOT NULL"
                )
            )

        fields[idx] = new_field
        return fields

    async def _schema_rename_field(
        self,
        collection: Collection,
        fields: List[dict],
        field_name: str,
        new_name: str,
    ) -> List[dict]:
        idx = self._find_field_index(fields, field_name)
        existing = dict(fields[idx])
        self._assert_user_field_mutable(existing, field_name)

        if not re.match(r"^[a-z][a-z0-9_]*$", new_name):
            raise InvalidSchemaError(
                f"Field '{new_name}' must start with letter, contain only lowercase letters, numbers, underscores"
            )
        if any(field.get("name") == new_name for field in fields):
            raise InvalidSchemaError(f"Field '{new_name}' already exists")
        if new_name in {
            "id",
            "_created_at",
            "_updated_at",
            "_vector_status",
            "_vector_chunk_count",
            "_vector_error",
        } | self.document_specific_field_names:
            raise InvalidSchemaError(f"Field name '{new_name}' is reserved")

        await self.session.execute(
            text(
                f"ALTER TABLE {collection.table_name} "
                f"RENAME COLUMN {field_name} TO {new_name}"
            )
        )

        existing["name"] = new_name
        fields[idx] = existing

        if collection.time_column == field_name:
            collection.time_column = new_name
        if collection.default_sort and collection.default_sort.get("field") == field_name:
            collection.default_sort = {
                **collection.default_sort,
                "field": new_name,
            }

        return fields

    async def _schema_remove_field(
        self,
        collection: Collection,
        fields: List[dict],
        field_name: str,
    ) -> List[dict]:
        idx = self._find_field_index(fields, field_name)
        existing = dict(fields[idx])
        self._assert_user_field_mutable(existing, field_name)

        await self.session.execute(
            text(
                f"ALTER TABLE {collection.table_name} "
                f"DROP COLUMN {field_name}"
            )
        )

        if collection.time_column == field_name:
            collection.time_column = None
        if collection.default_sort and collection.default_sort.get("field") == field_name:
            collection.default_sort = None

        return [field for pos, field in enumerate(fields) if pos != idx]
