from __future__ import annotations

import uuid
from typing import Any, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.collection import Collection, CollectionType, FieldCategory, FieldType

logger = get_logger(__name__)


def normalize_embedding_model_aliases(raw_aliases: Any) -> list[str]:
    if isinstance(raw_aliases, str):
        values = [raw_aliases]
    elif isinstance(raw_aliases, (list, tuple, set)):
        values = list(raw_aliases)
    else:
        values = []

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        alias = str(value or "").strip()
        if not alias or alias in seen:
            continue
        seen.add(alias)
        normalized.append(alias)
    return normalized


def get_vector_config_model_aliases(vector_config: Any) -> list[str]:
    if not isinstance(vector_config, dict):
        return []
    aliases = normalize_embedding_model_aliases(vector_config.get("embed_model_aliases"))
    if aliases:
        return aliases
    legacy_alias = str(vector_config.get("embed_model_alias") or "").strip()
    return [legacy_alias] if legacy_alias else []


def get_model_scoped_qdrant_collection_name(
    base_collection_name: str,
    model_alias: str,
    primary_model_alias: str | None,
) -> str:
    base = str(base_collection_name or "").strip()
    alias = str(model_alias or "").strip()
    primary = str(primary_model_alias or "").strip()
    if not base or not alias:
        return base
    if primary and alias == primary:
        return base
    return f"{base}__{alias}"


def build_model_scoped_qdrant_collections(
    base_collection_name: str,
    model_aliases: list[str],
) -> list[tuple[str, str]]:
    aliases = normalize_embedding_model_aliases(model_aliases)
    if not aliases:
        return []
    primary_alias = aliases[0]
    return [
        (
            alias,
            get_model_scoped_qdrant_collection_name(
                base_collection_name,
                alias,
                primary_alias,
            ),
        )
        for alias in aliases
    ]


class CollectionVectorLifecycleService:
    """Vector infra lifecycle for collection tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def fields_require_table_vector_search(fields: List[dict]) -> bool:
        return any(
            field.get("used_in_retrieval", False)
            and field.get("data_type") == FieldType.TEXT.value
            for field in fields
        )

    @staticmethod
    def vector_signature(fields: List[dict]) -> List[tuple[str, str, bool]]:
        return sorted(
            (
                field["name"],
                field["data_type"],
                bool(field.get("used_in_retrieval", False)),
            )
            for field in fields
            if field.get("used_in_retrieval", False)
        )

    async def table_has_rows(self, table_name: str) -> bool:
        result = await self.session.execute(
            text(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)")
        )
        return bool(result.scalar())

    async def count_nulls(self, table_name: str, field_name: str) -> int:
        result = await self.session.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE {field_name} IS NULL")
        )
        return int(result.scalar() or 0)

    async def ensure_table_vector_infra(self, collection: Collection) -> None:
        if collection.collection_type not in {CollectionType.TABLE.value, CollectionType.TEMPLATE.value}:
            return

        if not collection.qdrant_collection_name:
            collection.qdrant_collection_name = f"coll_{collection.slug}"
        if not collection.vector_config:
            collection.vector_config = {
                "chunk_strategy": "by_paragraphs",
                "chunk_size": 512,
                "overlap": 50,
            }

        await self.session.execute(
            text(
                f"ALTER TABLE {collection.table_name} "
                f"ADD COLUMN IF NOT EXISTS _vector_status TEXT DEFAULT 'pending', "
                f"ADD COLUMN IF NOT EXISTS _vector_chunk_count INTEGER DEFAULT 0, "
                f"ADD COLUMN IF NOT EXISTS _vector_error TEXT"
            )
        )
        await self.session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{collection.table_name}_vector_status "
                f"ON {collection.table_name} (_vector_status)"
            )
        )

    async def drop_table_vector_infra(self, collection: Collection) -> None:
        if collection.collection_type not in {CollectionType.TABLE.value, CollectionType.TEMPLATE.value}:
            return

        if collection.qdrant_collection_name:
            await self.cleanup_model_scoped_qdrant_collections(
                collection.qdrant_collection_name,
                model_aliases=get_vector_config_model_aliases(collection.vector_config),
            )

        await self.session.execute(text(f"DROP INDEX IF EXISTS idx_{collection.table_name}_vector_status"))
        await self.session.execute(
            text(
                f"ALTER TABLE {collection.table_name} "
                f"DROP COLUMN IF EXISTS _vector_status, "
                f"DROP COLUMN IF EXISTS _vector_chunk_count, "
                f"DROP COLUMN IF EXISTS _vector_error"
            )
        )
        collection.qdrant_collection_name = None
        collection.vector_config = None
        collection.vectorized_rows = 0
        collection.failed_rows = 0
        collection.total_chunks = 0

    async def reset_table_vector_state(self, collection: Collection) -> None:
        if collection.collection_type not in {CollectionType.TABLE.value, CollectionType.TEMPLATE.value} or not collection.qdrant_collection_name:
            return

        await self.cleanup_model_scoped_qdrant_collections(
            collection.qdrant_collection_name,
            model_aliases=get_vector_config_model_aliases(collection.vector_config),
        )

        await self.session.execute(
            text(
                f"UPDATE {collection.table_name} "
                f"SET _vector_status = 'pending', _vector_chunk_count = 0, _vector_error = NULL"
            )
        )
        collection.vectorized_rows = 0
        collection.failed_rows = 0
        collection.total_chunks = 0

    async def resolve_primary_vector_model(self, tenant_id: uuid.UUID) -> Optional[str]:
        target_models = await self.resolve_target_vector_models(tenant_id)
        return target_models[0] if target_models else None

    async def resolve_target_vector_models(self, tenant_id: uuid.UUID) -> list[str]:
        try:
            from app.repositories.factory import AsyncRepositoryFactory
            from app.services.rag_status_manager import RAGStatusManager

            repo_factory = AsyncRepositoryFactory(self.session, tenant_id)
            status_manager = RAGStatusManager(self.session, repo_factory)
            target_models = await status_manager.get_target_models_for_tenant(tenant_id)
            if target_models:
                return normalize_embedding_model_aliases(target_models)
        except Exception as e:
            logger.warning(
                "Failed to resolve embedding target models for vector collection provisioning",
                extra={"tenant_id": str(tenant_id), "error": str(e)},
            )
        return []

    async def resolve_embedding_dimensions(self, model_alias: str) -> int:
        try:
            result = await self.session.execute(
                text(
                    "SELECT extra_config "
                    "FROM models "
                    "WHERE alias = :alias AND type = 'EMBEDDING' "
                    "AND enabled = true AND status = 'AVAILABLE' "
                    "LIMIT 1"
                ),
                {"alias": model_alias},
            )
            extra = result.scalar_one_or_none() or {}
            if isinstance(extra, dict):
                raw_dim = extra.get("vector_dim", extra.get("dimensions"))
                if raw_dim is not None:
                    dim = int(raw_dim)
                    if dim > 0:
                        return dim
        except Exception as e:
            logger.warning(
                "Failed to resolve embedding dimensions for vector collection provisioning",
                extra={"model_alias": model_alias, "error": str(e)},
            )
        return 384

    async def provision_qdrant_collection(self, tenant_id: uuid.UUID, qdrant_collection_name: str) -> None:
        if not qdrant_collection_name:
            return

        from app.adapters.impl.qdrant import QdrantVectorStore

        vector_store = QdrantVectorStore()
        target_models = await self.resolve_target_vector_models(tenant_id)
        if not target_models:
            raise RuntimeError(
                f"No embedding target models resolved for tenant {tenant_id} while provisioning {qdrant_collection_name}"
            )

        for model_alias, scoped_collection_name in build_model_scoped_qdrant_collections(
            qdrant_collection_name,
            target_models,
        ):
            vector_dim = await self.resolve_embedding_dimensions(model_alias)
            await vector_store.ensure_collection(scoped_collection_name, vector_dim)

    async def cleanup_qdrant_collection(self, qdrant_collection_name: str) -> None:
        if not qdrant_collection_name:
            return
        try:
            from app.adapters.impl.qdrant import QdrantVectorStore

            vector_store = QdrantVectorStore()
            await vector_store.delete_collection(qdrant_collection_name)
            logger.info(
                "Cleaned up orphaned Qdrant collection",
                extra={"qdrant_collection_name": qdrant_collection_name},
            )
        except Exception as cleanup_err:
            logger.warning(
                "Failed to clean up orphaned Qdrant collection",
                extra={"qdrant_collection_name": qdrant_collection_name, "error": str(cleanup_err)},
            )

    async def cleanup_model_scoped_qdrant_collections(
        self,
        qdrant_collection_name: str,
        *,
        model_aliases: list[str] | None = None,
    ) -> None:
        aliases = normalize_embedding_model_aliases(model_aliases)
        target_names = {str(qdrant_collection_name or "").strip()}
        target_names.update(
            scoped_name
            for _, scoped_name in build_model_scoped_qdrant_collections(
                qdrant_collection_name,
                aliases,
            )
            if scoped_name
        )
        for target_name in target_names:
            if target_name:
                await self.cleanup_qdrant_collection(target_name)

    async def cleanup_collection_creation_artifacts(
        self,
        *,
        table_name: Optional[str],
        qdrant_collection_name: Optional[str],
    ) -> None:
        try:
            if table_name:
                await self.session.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
        except Exception as cleanup_err:
            logger.warning(
                "Failed to drop table during collection cleanup",
                extra={"table_name": table_name, "error": str(cleanup_err)},
            )
        await self.cleanup_qdrant_collection(qdrant_collection_name or "")
