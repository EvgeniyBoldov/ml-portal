from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, InvalidSchemaError
from app.models.collection import Collection, CollectionStatus, CollectionType, FieldType
from app.models.tool_instance import ToolInstance


def _expected_data_connector_subtype(collection_type: str) -> Optional[str]:
    normalized = str(collection_type or "").strip().lower()
    if normalized == CollectionType.SQL.value:
        return "sql"
    if normalized == CollectionType.API.value:
        return "api"
    return None


def _ensure_type_specific_fields(contract, fields: List[dict], collection_type: str) -> List[dict]:
    expected_subtype = _expected_data_connector_subtype(collection_type)
    if expected_subtype == "sql":
        return contract.ensure_sql_preset_fields(fields)
    # API/table no longer auto-inject specific fields; document keeps admin-defined preset path.
    return list(fields or [])


class CollectionLifecycleService:
    """Collection create/delete orchestration extracted from CollectionService."""

    def __init__(self, session: AsyncSession, host, contract) -> None:
        self.session = session
        self.host = host
        self.contract = contract

    async def create_collection(
        self,
        *,
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
        self.contract.validate_slug(slug)

        existing = await self.host.get_by_slug(tenant_id, slug)
        if existing:
            raise self.host.CollectionExistsError(f"Collection '{slug}' already exists")

        if data_instance_id is None:
            raise InvalidSchemaError("data_instance_id is required")

        data_instance = await self._resolve_and_validate_data_instance(
            tenant_id=tenant_id,
            data_instance_id=data_instance_id,
            collection_type=collection_type,
        )

        expected_subtype = _expected_data_connector_subtype(collection_type)
        is_remote = expected_subtype is not None
        if is_remote:
            return await self.create_remote_collection(
                tenant_id=tenant_id,
                slug=slug,
                name=name,
                fields=fields,
                description=description,
                source_contract=source_contract,
                collection_type=collection_type,
                data_instance_id=data_instance_id,
                data_instance=data_instance,
                table_name=table_name,
                table_schema=table_schema,
            )

        return await self.create_local_collection(
            tenant_id=tenant_id,
            slug=slug,
            name=name,
            fields=fields,
            description=description,
            source_contract=source_contract,
            vector_config=vector_config,
            collection_type=collection_type,
            data_instance_id=data_instance_id,
        )

    async def create_local_collection(
        self,
        *,
        tenant_id: uuid.UUID,
        slug: str,
        name: str,
        fields: List[dict],
        description: Optional[str] = None,
        source_contract: Optional[dict] = None,
        vector_config: Optional[dict] = None,
        collection_type: str = CollectionType.TABLE.value,
        data_instance_id: Optional[uuid.UUID] = None,
    ) -> Collection:
        if data_instance_id is None:
            raise InvalidSchemaError("data_instance_id is required")
        self.contract.validate_admin_defined_fields(fields, collection_type)
        fields = _ensure_type_specific_fields(self.contract, fields, collection_type)

        if collection_type == CollectionType.DOCUMENT.value:
            if not vector_config:
                vector_config = {
                    "chunk_strategy": "by_paragraphs",
                    "chunk_size": 512,
                    "overlap": 50,
                }

        self.contract.validate_fields(fields, collection_type)

        table_name = self.host._generate_table_name(tenant_id, slug)

        has_retrieval_fields = any(
            field.get("used_in_retrieval", False)
            and field.get("data_type") == FieldType.TEXT.value
            for field in fields
        )

        needs_vector = has_retrieval_fields or collection_type == CollectionType.DOCUMENT.value
        if needs_vector and not vector_config:
            vector_config = {
                "chunk_strategy": "by_paragraphs",
                "chunk_size": 512,
                "overlap": 50,
            }

        qdrant_collection_name = None
        if needs_vector:
            tenant_short = str(tenant_id).replace("-", "")[:8]
            qdrant_collection_name = f"coll_{tenant_short}_{slug}"

        collection = Collection(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            collection_type=collection_type,
            slug=slug,
            name=name,
            description=description,
            fields=fields,
            source_contract=source_contract,
            status=CollectionStatus.CREATED.value,
            table_name=table_name,
            vector_config=vector_config,
            qdrant_collection_name=qdrant_collection_name,
            data_instance_id=data_instance_id,
            total_rows=0,
            vectorized_rows=0,
            total_chunks=0,
            failed_rows=0,
            is_active=True,
        )

        try:
            create_table_sql = self.host._build_create_table_sql(table_name, fields)
            await self.session.execute(text(create_table_sql))

            if needs_vector:
                await self.session.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN _vector_status TEXT DEFAULT 'pending', "
                        f"ADD COLUMN _vector_chunk_count INTEGER DEFAULT 0, "
                        f"ADD COLUMN _vector_error TEXT"
                    )
                )
                await self.session.execute(
                    text(
                        f"CREATE INDEX idx_{table_name}_vector_status "
                        f"ON {table_name} (_vector_status)"
                    )
                )

            await self.session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            for index_sql in self.host._build_indexes_sql(table_name, fields):
                await self.session.execute(text(index_sql))

            if qdrant_collection_name:
                await self.host._provision_qdrant_collection(tenant_id, qdrant_collection_name)

            self.session.add(collection)
            await self.session.flush()

            initial_version = self.host._build_initial_version(collection)
            self.session.add(initial_version)
            await self.session.flush()
            collection.current_version_id = initial_version.id
            await self.session.flush()

            await self.host.sync_collection_status(collection, persist=False)
            return collection
        except Exception:
            await self.host._cleanup_collection_creation_artifacts(
                table_name=table_name,
                qdrant_collection_name=qdrant_collection_name,
            )
            raise

    async def create_remote_collection(
        self,
        *,
        tenant_id: uuid.UUID,
        slug: str,
        name: str,
        fields: List[dict],
        description: Optional[str] = None,
        source_contract: Optional[dict] = None,
        collection_type: str = CollectionType.SQL.value,
        data_instance_id: Optional[uuid.UUID] = None,
        data_instance: Optional[ToolInstance] = None,
        table_name: Optional[str] = None,
        table_schema: Optional[dict] = None,
    ) -> Collection:
        if data_instance_id is None:
            raise InvalidSchemaError("data_instance_id is required")
        self.contract.validate_admin_defined_fields(fields, collection_type)
        fields = _ensure_type_specific_fields(self.contract, fields, collection_type)
        self.contract.validate_fields(fields, collection_type)
        if data_instance is None:
            await self._resolve_and_validate_data_instance(
                tenant_id=tenant_id,
                data_instance_id=data_instance_id,
                collection_type=collection_type,
            )

        initial_status = (
            CollectionStatus.DISCOVERED.value
            if table_schema
            else CollectionStatus.CREATED.value
        )

        collection = Collection(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            collection_type=collection_type,
            slug=slug,
            name=name,
            description=description,
            fields=fields,
            source_contract=source_contract,
            status=initial_status,
            table_name=table_name,
            data_instance_id=data_instance_id,
            table_schema=table_schema,
            is_active=True,
        )

        self.session.add(collection)
        await self.session.flush()

        initial_version = self.host._build_initial_version(collection)
        self.session.add(initial_version)
        await self.session.flush()
        collection.current_version_id = initial_version.id
        await self.session.flush()

        return collection

    async def _resolve_and_validate_data_instance(
        self,
        *,
        tenant_id: uuid.UUID,
        data_instance_id: uuid.UUID,
        collection_type: str,
    ) -> ToolInstance:
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

        # ToolInstance currently has no explicit tenant_id column in schema.
        # Enforce tenant affinity when legacy tenant_id is present in config.
        cfg_tenant_id = str((instance.config or {}).get("tenant_id") or "").strip()
        if cfg_tenant_id and cfg_tenant_id != str(tenant_id):
            raise ConflictError("data instance belongs to another tenant")

        expected_subtype = _expected_data_connector_subtype(collection_type)
        if expected_subtype and str(instance.connector_subtype or "").strip().lower() != expected_subtype:
            raise InvalidSchemaError(
                f"Connector {data_instance_id} is not {expected_subtype} subtype"
            )
        return instance

    async def delete_collection(
        self, tenant_id: uuid.UUID, slug: str, *, drop_table: bool = True
    ) -> bool:
        collection = await self.host.get_by_slug(tenant_id, slug)
        if not collection:
            return False

        table_name = getattr(collection, "table_name", None)
        qdrant_collection_name = getattr(collection, "qdrant_collection_name", None)

        await self.session.delete(collection)
        await self.session.flush()

        if drop_table and table_name:
            await self.session.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))

        if qdrant_collection_name:
            from app.adapters.impl.qdrant import QdrantVectorStore

            vector_store = QdrantVectorStore()
            if await vector_store.collection_exists(qdrant_collection_name):
                await vector_store.delete_collection(qdrant_collection_name)

        return True
