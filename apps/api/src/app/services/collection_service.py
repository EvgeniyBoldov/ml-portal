"""
Collection service for managing dynamic data collections
"""
import uuid
from typing import List, Optional, Any

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import (
    Collection,
    CollectionType,
    CollectionVersion,
    FieldType,
)
from app.core.exceptions import (
    CollectionNotFoundError,
    CollectionAlreadyExistsError as CollectionExistsError,
    InvalidSchemaError,
)
from app.models.tool_instance import ToolInstance
from app.core.logging import get_logger
from app.services.tool_instance_service import ToolInstanceService
from app.services.collection.ddl import (
    FIELD_TYPE_TO_PG,
    build_create_table_sql as _build_create_table_sql,
    build_indexes_sql as _build_indexes_sql,
    build_drop_indexes_sql as _build_drop_indexes_sql,
    apply_typed_binds as _apply_typed_binds,
)
from app.services.collection.field_coercion import (
    RowValidationError,
    coerce_value as _coerce_value,
    validate_and_prepare_payload as _validate_and_prepare_payload,
)
from app.services.collection.version_service import CollectionVersionService
from app.services.collection.row_service import CollectionRowService
from app.services.collection.vector_lifecycle import CollectionVectorLifecycleService
from app.services.collection.status_snapshot_service import CollectionStatusSnapshotService
from app.services.collection.schema_evolution_service import CollectionSchemaEvolutionService
from app.services.collection.lifecycle_service import CollectionLifecycleService
from app.services.collection.schema_contract_service import CollectionSchemaContractService
from app.services.collection.query_service import CollectionQueryService

logger = get_logger(__name__)
_UNSET = object()

class CollectionService:
    """Service for managing collections and their dynamic tables"""
    CollectionExistsError = CollectionExistsError
    FieldType = FieldType
    logger = logger

    def __init__(self, session: AsyncSession):
        self.session = session
        self.tool_instance_service = ToolInstanceService(session)
        self.versions = CollectionVersionService(session)
        self.rows = CollectionRowService(session)
        self.vector = CollectionVectorLifecycleService(session)
        self.status_snapshot = CollectionStatusSnapshotService(session)
        self.contract = CollectionSchemaContractService()
        self.query = CollectionQueryService(session, self)
        self.schema_evolution = CollectionSchemaEvolutionService(
            session,
            self,
            self.contract,
            field_type_to_pg=FIELD_TYPE_TO_PG,
        )
        self.lifecycle = CollectionLifecycleService(session, self, self.contract)

    @staticmethod
    def get_type_specific_field_presets() -> dict[str, list[dict]]:
        return CollectionSchemaContractService.get_type_specific_field_presets()

    def _generate_table_name(self, tenant_id: uuid.UUID, slug: str) -> str:
        tenant_short = str(tenant_id).replace("-", "")[:8]
        return f"coll_{tenant_short}_{slug}"

    def _validate_slug(self, slug: str) -> None:
        self.contract.validate_slug(slug)

    def _validate_fields(self, fields: List[dict], collection_type: str) -> None:
        self.contract.validate_fields(fields, collection_type)

    def _validate_admin_defined_fields(self, fields: List[dict], collection_type: str) -> None:
        self.contract.validate_admin_defined_fields(fields, collection_type)

    def _build_create_table_sql(self, table_name: str, fields: List[dict]) -> str:
        return _build_create_table_sql(table_name, fields)

    def _build_indexes_sql(self, table_name: str, fields: List[dict]) -> List[str]:
        return _build_indexes_sql(table_name, fields)

    def _coerce_row_value(self, field_name: str, field_type: str, value: Any) -> Any:
        return _coerce_value(field_name, field_type, value)

    def _validate_and_prepare_row_payload(
        self, collection: Collection, payload: dict, *, partial: bool
    ) -> dict:
        return _validate_and_prepare_payload(collection, payload, partial=partial)

    @staticmethod
    def _apply_typed_binds(sql, field_defs: List[dict]):
        return _apply_typed_binds(sql, field_defs)

    def _build_drop_indexes_sql(self, table_name: str, field_name: str) -> List[str]:
        return _build_drop_indexes_sql(table_name, field_name)

    def _fields_require_table_vector_search(self, fields: List[dict]) -> bool:
        """Check if table collection fields require vector infra."""
        return self.vector.fields_require_table_vector_search(fields)

    def _vector_signature(self, fields: List[dict]) -> List[tuple[str, str, bool]]:
        """Stable signature of user field retrieval semantics."""
        return self.vector.vector_signature(fields)

    async def _table_has_rows(self, table_name: str) -> bool:
        """Check if dynamic table contains data."""
        return await self.vector.table_has_rows(table_name)

    async def _count_nulls(self, table_name: str, field_name: str) -> int:
        """Count rows where the field is NULL."""
        return await self.vector.count_nulls(table_name, field_name)

    async def _ensure_table_vector_infra(self, collection: Collection) -> None:
        """Ensure table collection has vector metadata columns and qdrant identity."""
        await self.vector.ensure_table_vector_infra(collection)

    async def _drop_table_vector_infra(self, collection: Collection) -> None:
        """Remove table collection vector infra when no retrieval fields remain."""
        await self.vector.drop_table_vector_infra(collection)

    async def _reset_table_vector_state(self, collection: Collection) -> None:
        """Reset row-level and collection-level table vector state after schema-affecting changes."""
        await self.vector.reset_table_vector_state(collection)

    async def _resolve_primary_vector_model(self, tenant_id: uuid.UUID) -> Optional[str]:
        """Resolve primary embedding model alias for vector collection provisioning."""
        return await self.vector.resolve_primary_vector_model(tenant_id)

    async def _resolve_embedding_dimensions(self, model_alias: str) -> int:
        """Resolve vector dimensions for embedding model; fallback to 384."""
        return await self.vector.resolve_embedding_dimensions(model_alias)

    async def _provision_qdrant_collection(
        self,
        tenant_id: uuid.UUID,
        qdrant_collection_name: str,
    ) -> None:
        """Create dedicated Qdrant collection for a platform collection."""
        if not qdrant_collection_name:
            return

        from app.adapters.impl.qdrant import QdrantVectorStore

        model_alias = await self._resolve_primary_vector_model(tenant_id)
        vector_dim = await self._resolve_embedding_dimensions(model_alias) if model_alias else 384

        vector_store = QdrantVectorStore()
        await vector_store.ensure_collection(qdrant_collection_name, vector_dim)

    async def _cleanup_qdrant_collection(self, qdrant_collection_name: str) -> None:
        """Best-effort cleanup for partially provisioned Qdrant collections."""
        await self.vector.cleanup_qdrant_collection(qdrant_collection_name)

    async def _cleanup_collection_creation_artifacts(
        self,
        *,
        table_name: Optional[str],
        qdrant_collection_name: Optional[str],
    ) -> None:
        """Best-effort cleanup for partially created collection artifacts."""
        try:
            if table_name:
                await self.session.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
        except Exception as cleanup_err:
            logger.warning(
                "Failed to drop table during collection cleanup",
                extra={"table_name": table_name, "error": str(cleanup_err)},
            )
        await self._cleanup_qdrant_collection(qdrant_collection_name or "")

    async def get_status_snapshot(self, collection: Collection) -> dict:
        """Build effective readiness status and diagnostics for a collection."""
        return await self.status_snapshot.get_status_snapshot(collection)

    async def sync_collection_status(
        self,
        collection: Collection,
        *,
        persist: bool = True,
    ) -> dict:
        """Recompute collection readiness status from actual underlying state."""
        return await self.status_snapshot.sync_collection_status(collection, persist=persist)

    async def _rebuild_structural_indexes(
        self,
        table_name: str,
        previous_fields: List[dict],
        current_fields: List[dict],
    ) -> None:
        """Rebuild generated field indexes after schema changes."""
        touched_names = {field["name"] for field in previous_fields} | {field["name"] for field in current_fields}
        for field_name in touched_names:
            for drop_sql in self._build_drop_indexes_sql(table_name, field_name):
                await self.session.execute(text(drop_sql))
        for create_sql in self._build_indexes_sql(table_name, current_fields):
            await self.session.execute(text(create_sql))

    def _normalize_default_sort(self, collection: Collection, fields: List[dict]) -> None:
        self.contract.normalize_default_sort(collection, fields)

    def _ensure_document_preset_fields(self, fields: List[dict]) -> List[dict]:
        return self.contract.ensure_document_preset_fields(fields)

    def _ensure_sql_preset_fields(self, fields: List[dict]) -> List[dict]:
        return self.contract.ensure_sql_preset_fields(fields)

    async def ensure_sql_storage_table(self, collection: Collection) -> None:
        """
        Ensure SQL collection has local catalog storage for discovered table rows.

        Legacy SQL collections may have no local table/fields; this method bootstraps
        required schema on first read/write from collection data endpoints.
        """
        collection_type = str(collection.collection_type or "").strip().lower()
        if collection_type not in {CollectionType.SQL.value, CollectionType.API.value}:
            return

        changed = False
        current_fields = list(collection.fields or [])
        if collection_type == CollectionType.SQL.value:
            next_fields = self.contract.ensure_sql_preset_fields(current_fields)
        else:
            next_fields = current_fields
        if next_fields != current_fields:
            collection.fields = next_fields
            changed = True

        table_name = str(collection.table_name or "").strip()
        if not table_name:
            table_name = self._generate_table_name(collection.tenant_id, collection.slug)
            collection.table_name = table_name
            changed = True

        await self.session.execute(text(self._build_create_table_sql(table_name, collection.fields)))
        await self.session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        for field in collection.get_row_writable_fields():
            field_name = str(field.get("name") or "").strip()
            if not field_name:
                continue
            pg_type = FIELD_TYPE_TO_PG.get(str(field.get("data_type") or ""), "TEXT")
            required = bool(field.get("required", False))
            constraint = "NOT NULL" if required else ""
            await self.session.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN IF NOT EXISTS {field_name} {pg_type} {constraint}".strip()
                )
            )

        for index_sql in self._build_indexes_sql(table_name, collection.fields):
            await self.session.execute(text(index_sql))

        if collection.collection_type == CollectionType.SQL.value:
            await self.session.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table_name}_table_name_uniq "
                    f"ON {table_name} (lower(btrim(table_name))) "
                    f"WHERE table_name IS NOT NULL"
                )
            )

        if changed:
            self.session.add(collection)
            await self.session.flush()

    async def create_collection(
        self,
        tenant_id: uuid.UUID,
        slug: str,
        name: str,
        fields: List[dict],
        description: Optional[str] = None,
        source_contract: Optional[dict] = None,
        vector_config: Optional[dict] = None,
        collection_type: str = CollectionType.TABLE.value,
        data_instance_id: Optional[uuid.UUID] = None,
        table_name: Optional[str] = None,
        table_schema: Optional[dict] = None,
    ) -> Collection:
        return await self.lifecycle.create_collection(
            tenant_id=tenant_id,
            slug=slug,
            name=name,
            fields=fields,
            description=description,
            source_contract=source_contract,
            vector_config=vector_config,
            collection_type=collection_type,
            data_instance_id=data_instance_id,
            table_name=table_name,
            table_schema=table_schema,
        )

    async def _create_local_collection(
        self,
        tenant_id: uuid.UUID,
        slug: str,
        name: str,
        fields: List[dict],
        description: Optional[str] = None,
        source_contract: Optional[dict] = None,
        vector_config: Optional[dict] = None,
        collection_type: str = CollectionType.TABLE.value,
    ) -> Collection:
        return await self.lifecycle.create_local_collection(
            tenant_id=tenant_id,
            slug=slug,
            name=name,
            fields=fields,
            description=description,
            source_contract=source_contract,
            vector_config=vector_config,
            collection_type=collection_type,
        )

    async def _create_remote_collection(
        self,
        tenant_id: uuid.UUID,
        slug: str,
        name: str,
        fields: List[dict],
        description: Optional[str] = None,
        source_contract: Optional[dict] = None,
        collection_type: str = CollectionType.SQL.value,
        data_instance_id: Optional[uuid.UUID] = None,
        table_name: Optional[str] = None,
        table_schema: Optional[dict] = None,
    ) -> Collection:
        return await self.lifecycle.create_remote_collection(
            tenant_id=tenant_id,
            slug=slug,
            name=name,
            fields=fields,
            description=description,
            source_contract=source_contract,
            collection_type=collection_type,
            data_instance_id=data_instance_id,
            table_name=table_name,
            table_schema=table_schema,
        )

    def _build_initial_version(self, collection: Collection) -> CollectionVersion:
        return CollectionVersionService.build_initial_version(collection)

    async def update_collection(
        self,
        collection_id: uuid.UUID,
        *,
        name: Any = _UNSET,
        description: Any = _UNSET,
        is_active: Any = _UNSET,
        data_instance_id: Any = _UNSET,
        table_name: Any = _UNSET,
        table_schema: Any = _UNSET,
        schema_ops: Optional[List[dict]] = None,
    ) -> Collection:
        """
        Update mutable collection metadata and apply controlled schema evolution.

        Schema evolution is limited to `user` fields and is executed transactionally
        against the dynamic SQL table.
        """
        collection = await self.get_by_id(collection_id)
        if not collection:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")

        if name is not _UNSET:
            collection.name = name
        if description is not _UNSET:
            collection.description = description
        if is_active is not _UNSET:
            collection.is_active = is_active
        if data_instance_id is not _UNSET:
            if data_instance_id is not None:
                result = await self.session.execute(
                    select(ToolInstance).where(ToolInstance.id == data_instance_id)
                )
                instance = result.scalar_one_or_none()
                if not instance:
                    raise InvalidSchemaError(f"Data instance {data_instance_id} not found")
                if not instance.is_active:
                    raise InvalidSchemaError(f"Data instance {data_instance_id} is not active")
                if instance.connector_type != "data":
                    raise InvalidSchemaError(f"Connector {data_instance_id} is not a data connector")
                expected_subtype = None
                normalized_type = str(collection.collection_type or "").strip().lower()
                if normalized_type == CollectionType.SQL.value:
                    expected_subtype = "sql"
                elif normalized_type == CollectionType.API.value:
                    expected_subtype = "api"
                if expected_subtype and str(instance.connector_subtype or "").strip().lower() != expected_subtype:
                    raise InvalidSchemaError(f"Connector {data_instance_id} is not {expected_subtype} subtype")
            collection.data_instance_id = data_instance_id
        if table_name is not _UNSET:
            collection.table_name = table_name
        if table_schema is not _UNSET:
            collection.table_schema = table_schema

        if schema_ops:
            await self._apply_schema_operations(collection, schema_ops)

        await self.sync_collection_status(collection, persist=False)

        self.session.add(collection)
        await self.session.flush()
        return collection

    async def list_versions(self, collection_id: uuid.UUID) -> List[CollectionVersion]:
        return await self.versions.list_versions(collection_id)

    async def get_version(self, collection_id: uuid.UUID, version: int) -> CollectionVersion:
        return await self.versions.get_version(collection_id, version)

    async def create_version(
        self,
        collection_id: uuid.UUID,
        *,
        notes: Optional[str] = None,
    ) -> CollectionVersion:
        return await self.versions.create_version(collection_id, notes=notes)

    async def update_version(
        self,
        collection_id: uuid.UUID,
        version: int,
        *,
        notes: Any = _UNSET,
    ) -> CollectionVersion:
        return await self.versions.update_version(
            collection_id, version,
            notes=notes if notes is not _UNSET else None,
            _UNSET=_UNSET,
        )

    async def publish_version(self, collection_id: uuid.UUID, version: int) -> CollectionVersion:
        return await self.versions.publish_version(collection_id, version)

    async def set_current_version(self, collection_id: uuid.UUID, version_id: uuid.UUID) -> Collection:
        return await self.versions.set_current_version(collection_id, version_id)

    async def archive_version(self, collection_id: uuid.UUID, version: int) -> CollectionVersion:
        return await self.versions.archive_version(collection_id, version)

    async def delete_version(self, collection_id: uuid.UUID, version: int) -> None:
        return await self.versions.delete_version(collection_id, version)

    async def activate_version(self, collection_id: uuid.UUID, version: int) -> CollectionVersion:
        return await self.versions.activate_version(collection_id, version)

    async def deactivate_version(self, collection_id: uuid.UUID, version: int) -> CollectionVersion:
        return await self.versions.deactivate_version(collection_id, version)

    async def _apply_schema_operations(
        self,
        collection: Collection,
        schema_ops: List[dict],
    ) -> None:
        return await self.schema_evolution.apply_schema_operations(collection, schema_ops)
    

    async def _create_tool_instance_for_collection(self, collection: Collection) -> Optional[ToolInstance]:
        """
        Resolve canonical local service instance for a collection.

        Collection no longer creates dedicated local DATA instances.
        It is linked directly to the shared local SERVICE provider by type.
        """
        local_service = await self.tool_instance_service.resolve_local_service_for_collection_type(
            collection.collection_type
        )
        return local_service

    async def get_by_id(self, collection_id: uuid.UUID) -> Optional[Collection]:
        return await self.query.get_by_id(collection_id)

    async def get_by_slug(
        self, tenant_id: uuid.UUID, slug: str
    ) -> Optional[Collection]:
        return await self.query.get_by_slug(tenant_id, slug)

    async def list_collections(
        self,
        tenant_id: uuid.UUID,
        active_only: bool = True,
    ) -> List[Collection]:
        return await self.query.list_collections(tenant_id, active_only=active_only)

    async def delete_collection(
        self, tenant_id: uuid.UUID, slug: str, drop_table: bool = True
    ) -> bool:
        return await self.lifecycle.delete_collection(
            tenant_id, slug, drop_table=drop_table
        )

    async def _delete_tool_instance_for_collection(self, instance_id: uuid.UUID) -> None:
        """Auto-delete the ToolInstance linked to a collection."""
        try:
            instance = await self.tool_instance_service.get_instance(instance_id)
            if instance.connector_type != "data":
                return
            await self.tool_instance_service.delete_local_instance(instance_id)
            logger.info(f"Deleted tool instance '{instance.slug}' for collection")
        except Exception as e:
            logger.error(f"Failed to delete tool instance {instance_id}: {e}")

    async def update_row_count(self, collection_id: uuid.UUID) -> int:
        return await self.query.update_row_count(collection_id)

    async def insert_rows(self, collection: Collection, rows: List[dict]) -> int:
        count = await self.rows.insert_rows(collection, rows)
        await self.sync_collection_status(collection, persist=False)
        return count

    async def create_row(self, collection: Collection, payload: dict) -> dict:
        row = await self.rows.create_row(collection, payload)
        await self.sync_collection_status(collection, persist=False)
        return row

    async def get_row_by_id(
        self, collection: Collection, row_id: uuid.UUID
    ) -> Optional[dict]:
        return await self.rows.get_row_by_id(collection, row_id)

    async def update_row(
        self, collection: Collection, row_id: uuid.UUID, payload: dict
    ) -> Optional[dict]:
        row = await self.rows.update_row(collection, row_id, payload)
        if row is not None:
            await self.sync_collection_status(collection, persist=False)
        return row

    async def search(
        self,
        collection: Collection,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
        query: Optional[str] = None,
    ) -> List[dict]:
        return await self.rows.search(collection, filters=filters, limit=limit, offset=offset, query=query)

    async def count(
        self,
        collection: Collection,
        filters: Optional[dict] = None,
        query: Optional[str] = None,
    ) -> int:
        return await self.rows.count(collection, filters=filters, query=query)

    async def delete_rows(self, collection: Collection, ids: List[uuid.UUID]) -> int:
        count = await self.rows.delete_rows(collection, ids)
        await self.sync_collection_status(collection, persist=False)
        return count
