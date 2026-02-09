"""
Collection service for managing dynamic data collections
"""
import uuid
import re
from typing import List, Optional, Any
from datetime import datetime

from sqlalchemy import text, TextClause
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.collection import Collection, FieldType, SearchMode
from app.models.permission_set import PermissionSet
from app.models.tool_instance import ToolInstance
from app.models.tool_group import ToolGroup
from app.core.logging import get_logger

logger = get_logger(__name__)


FIELD_TYPE_TO_PG = {
    FieldType.STRING.value: "VARCHAR(255)",
    FieldType.TEXT.value: "TEXT",
    FieldType.INTEGER.value: "BIGINT",
    FieldType.FLOAT.value: "DOUBLE PRECISION",
    FieldType.BOOLEAN.value: "BOOLEAN",
    FieldType.DATETIME.value: "TIMESTAMPTZ",
    FieldType.DATE.value: "DATE",
    FieldType.ENUM.value: "VARCHAR(100)",
    FieldType.JSON.value: "JSONB",
}

VALID_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class CollectionServiceError(Exception):
    """Base exception for collection service"""
    pass


class CollectionNotFoundError(CollectionServiceError):
    """Collection not found"""
    pass


class CollectionExistsError(CollectionServiceError):
    """Collection with this slug already exists"""
    pass


class InvalidSchemaError(CollectionServiceError):
    """Invalid collection schema"""
    pass


class CollectionService:
    """Service for managing collections and their dynamic tables"""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _generate_table_name(self, tenant_id: uuid.UUID, slug: str) -> str:
        """Generate unique table name for collection data"""
        tenant_short = str(tenant_id).replace("-", "")[:8]
        return f"coll_{tenant_short}_{slug}"

    def _validate_slug(self, slug: str) -> None:
        """Validate collection slug"""
        if not slug or len(slug) > 50:
            raise InvalidSchemaError("Slug must be 1-50 characters")
        if not VALID_SLUG_PATTERN.match(slug):
            raise InvalidSchemaError(
                "Slug must start with letter, contain only lowercase letters, numbers, underscores"
            )

    def _validate_fields(self, fields: List[dict]) -> None:
        """Validate fields schema with search_modes support"""
        if not fields:
            raise InvalidSchemaError("At least one field is required")

        field_names = set()
        reserved_names = {"id", "_created_at", "_updated_at", "_vector_status", "_vector_chunk_count", "_vector_error"}

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

            field_type = field.get("type")
            if field_type not in [ft.value for ft in FieldType]:
                raise InvalidSchemaError(
                    f"Invalid field type '{field_type}' for field '{name}'"
                )

            # Validate search_modes (array)
            search_modes = field.get("search_modes", ["exact"])
            if not isinstance(search_modes, list):
                raise InvalidSchemaError(
                    f"Field '{name}': search_modes must be an array"
                )
            
            valid_modes = {sm.value for sm in SearchMode}
            for mode in search_modes:
                if mode not in valid_modes:
                    raise InvalidSchemaError(
                        f"Field '{name}': invalid search mode '{mode}'"
                    )
            
            # Vector only for text fields
            if "vector" in search_modes and field_type != FieldType.TEXT.value:
                raise InvalidSchemaError(
                    f"Field '{name}': vector search only available for text fields"
                )
            
            # Vector requires like
            if "vector" in search_modes and "like" not in search_modes:
                raise InvalidSchemaError(
                    f"Field '{name}': vector search requires 'like' in search_modes"
                )
            
            # Like only for text fields
            if "like" in search_modes and field_type != FieldType.TEXT.value:
                raise InvalidSchemaError(
                    f"Field '{name}': like search only available for text fields"
                )
            
            # Range only for numeric/date fields
            if "range" in search_modes and field_type not in [
                FieldType.INTEGER.value,
                FieldType.FLOAT.value,
                FieldType.DATETIME.value,
                FieldType.DATE.value,
            ]:
                raise InvalidSchemaError(
                    f"Field '{name}': range search not valid for field type '{field_type}'"
                )

    def _build_create_table_sql(self, table_name: str, fields: List[dict]) -> str:
        """Build CREATE TABLE SQL statement"""
        columns = [
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid()",
        ]

        for field in fields:
            name = field["name"]
            pg_type = FIELD_TYPE_TO_PG[field["type"]]
            nullable = "NOT NULL" if field.get("required", False) else ""
            columns.append(f"{name} {pg_type} {nullable}".strip())

        columns.append("_created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL")

        columns_sql = ",\n    ".join(columns)
        return f"CREATE TABLE {table_name} (\n    {columns_sql}\n)"

    def _build_indexes_sql(self, table_name: str, fields: List[dict]) -> List[str]:
        """Build CREATE INDEX statements based on search_modes"""
        indexes = []

        for field in fields:
            name = field["name"]
            search_modes = field.get("search_modes", [])
            
            # Create indexes based on search modes
            if "like" in search_modes:
                # GIN trigram index for LIKE search
                indexes.append(
                    f"CREATE INDEX idx_{table_name}_{name}_trgm "
                    f"ON {table_name} USING GIN ({name} gin_trgm_ops)"
                )
            elif "range" in search_modes:
                # B-tree index for range queries
                indexes.append(
                    f"CREATE INDEX idx_{table_name}_{name}_btree "
                    f"ON {table_name} ({name})"
                )
            elif "exact" in search_modes:
                # B-tree index for exact match
                indexes.append(
                    f"CREATE INDEX idx_{table_name}_{name} "
                    f"ON {table_name} ({name})"
                )

        return indexes

    async def create_collection(
        self,
        tenant_id: uuid.UUID,
        slug: str,
        name: str,
        fields: List[dict],
        description: Optional[str] = None,
        vector_config: Optional[dict] = None,
    ) -> Collection:
        """
        Create a new collection with its dynamic table.
        Automatically creates Qdrant collection if any field has 'vector' in search_modes.
        
        Args:
            tenant_id: Tenant UUID
            slug: Unique identifier (within tenant)
            name: Human-readable name
            fields: List of field definitions with search_modes
            description: Optional description for LLM
            vector_config: Optional vector search configuration
        
        Returns:
            Created Collection object
        """
        self._validate_slug(slug)
        self._validate_fields(fields)

        existing = await self.get_by_slug(tenant_id, slug)
        if existing:
            raise CollectionExistsError(f"Collection '{slug}' already exists")

        table_name = self._generate_table_name(tenant_id, slug)
        
        # Check if any field has vector search
        has_vector_fields = any(
            "vector" in field.get("search_modes", []) 
            for field in fields
        )
        
        # Auto-generate vector config if needed
        if has_vector_fields and not vector_config:
            vector_config = {
                "chunk_strategy": "by_paragraphs",
                "chunk_size": 512,
                "overlap": 50,
            }
        
        # Generate Qdrant collection name if vector search enabled
        qdrant_collection_name = None
        if has_vector_fields:
            tenant_short = str(tenant_id).replace("-", "")[:8]
            qdrant_collection_name = f"coll_{tenant_short}_{slug}"

        collection = Collection(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            slug=slug,
            name=name,
            description=description,
            fields=fields,
            table_name=table_name,
            row_count=0,
            vector_config=vector_config,
            qdrant_collection_name=qdrant_collection_name,
            total_rows=0,
            vectorized_rows=0,
            total_chunks=0,
            failed_rows=0,
            is_active=True,
        )

        # Create SQL table
        create_table_sql = self._build_create_table_sql(table_name, fields)
        await self.session.execute(text(create_table_sql))
        
        # Add vector metadata columns if needed
        if has_vector_fields:
            await self.session.execute(text(
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN _vector_status TEXT DEFAULT 'pending', "
                f"ADD COLUMN _vector_chunk_count INTEGER DEFAULT 0, "
                f"ADD COLUMN _vector_error TEXT"
            ))
            await self.session.execute(text(
                f"CREATE INDEX idx_{table_name}_vector_status "
                f"ON {table_name} (_vector_status)"
            ))

        # Create trigram extension for LIKE search
        await self.session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        # Create indexes
        for index_sql in self._build_indexes_sql(table_name, fields):
            await self.session.execute(text(index_sql))
        
        # TODO: Create Qdrant collection here when vector service is implemented
        # if qdrant_collection_name:
        #     await self._create_qdrant_collection(qdrant_collection_name, vector_config)

        self.session.add(collection)
        await self.session.flush()
        
        # Auto-create ToolInstance for this collection
        tool_instance = await self._create_tool_instance_for_collection(collection)
        if tool_instance:
            collection.tool_instance_id = tool_instance.id
            await self.session.flush()
        
        # Auto-add instance to default permission set (use instance slug, not collection slug)
        if tool_instance:
            await self._add_instance_to_default_permissions(tool_instance.slug)

        return collection
    
    async def _add_instance_to_default_permissions(self, instance_slug: str):
        """Add new instance to default permission set with 'denied' status"""
        # Get default permission set
        stmt = select(PermissionSet).where(
            PermissionSet.scope == "default",
            PermissionSet.tenant_id.is_(None),
            PermissionSet.user_id.is_(None)
        )
        result = await self.session.execute(stmt)
        default_perms = result.scalar_one_or_none()
        
        if not default_perms:
            logger.warning("Default permission set not found, skipping auto-add")
            return
        
        # Check if instance already in permissions
        instance_permissions = dict(default_perms.instance_permissions or {})
        if instance_slug in instance_permissions:
            return
        
        # Add with 'denied' status by default
        instance_permissions[instance_slug] = "denied"
        default_perms.instance_permissions = instance_permissions
        
        self.session.add(default_perms)
        await self.session.flush()
        
        logger.info(f"Added instance '{instance_slug}' to default permissions (status: denied)")

    async def _create_tool_instance_for_collection(self, collection: Collection) -> Optional[ToolInstance]:
        """
        Auto-create ToolInstance for a collection.
        
        Each collection gets its own ToolInstance in the 'collection' tool group.
        This allows binding collections to agents through the standard bindings mechanism.
        """
        # Get or create 'collection' tool group
        stmt = select(ToolGroup).where(ToolGroup.slug == "collection")
        result = await self.session.execute(stmt)
        tool_group = result.scalar_one_or_none()
        
        if not tool_group:
            logger.warning("ToolGroup 'collection' not found, cannot create ToolInstance for collection")
            return None
        
        # Create ToolInstance
        instance_slug = f"collection-{collection.slug}"
        
        # Check if instance already exists (by name + group)
        stmt = select(ToolInstance).where(
            ToolInstance.tool_group_id == tool_group.id,
            ToolInstance.name == f"Collection: {collection.name}",
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.info(f"ToolInstance for collection '{collection.slug}' already exists, reusing")
            return existing
        
        tool_instance = ToolInstance(
            id=uuid.uuid4(),
            tool_group_id=tool_group.id,
            name=f"Collection: {collection.name}",
            description=collection.description or f"Data collection: {collection.name}",
            url="",
            config={
                "collection_id": str(collection.id),
                "collection_slug": collection.slug,
                "tenant_id": str(collection.tenant_id),
                "table_name": collection.table_name,
                "entity_type": collection.entity_type,
                "row_count": collection.row_count,
                "has_vector_search": collection.has_vector_search,
                "primary_key_field": collection.primary_key_field,
                "time_column": collection.time_column,
            },
            is_active=True,
        )
        
        self.session.add(tool_instance)
        await self.session.flush()
        
        logger.info(f"Created ToolInstance '{instance_slug}' for collection '{collection.slug}'")
        return tool_instance

    async def get_by_id(self, collection_id: uuid.UUID) -> Optional[Collection]:
        """Get collection by ID"""
        result = await self.session.execute(
            select(Collection).where(Collection.id == collection_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(
        self, tenant_id: uuid.UUID, slug: str
    ) -> Optional[Collection]:
        """Get collection by tenant and slug"""
        result = await self.session.execute(
            select(Collection).where(
                Collection.tenant_id == tenant_id,
                Collection.slug == slug,
            )
        )
        return result.scalar_one_or_none()

    async def list_collections(
        self,
        tenant_id: uuid.UUID,
        active_only: bool = True,
    ) -> List[Collection]:
        """List all collections for a tenant"""
        query = select(Collection).where(Collection.tenant_id == tenant_id)
        if active_only:
            query = query.where(Collection.is_active == True)
        query = query.order_by(Collection.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_collection(
        self, tenant_id: uuid.UUID, slug: str, drop_table: bool = True
    ) -> bool:
        """
        Delete a collection and optionally its data table.
        
        Args:
            tenant_id: Tenant UUID
            slug: Collection slug
            drop_table: If True, also drop the data table
        
        Returns:
            True if deleted, False if not found
        """
        collection = await self.get_by_slug(tenant_id, slug)
        if not collection:
            return False

        if drop_table:
            await self.session.execute(
                text(f"DROP TABLE IF EXISTS {collection.table_name} CASCADE")
            )

        await self.session.delete(collection)
        await self.session.flush()

        return True

    async def update_row_count(self, collection_id: uuid.UUID) -> int:
        """Update and return the row count for a collection"""
        collection = await self.get_by_id(collection_id)
        if not collection:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")

        result = await self.session.execute(
            text(f"SELECT COUNT(*) FROM {collection.table_name}")
        )
        count = result.scalar()

        collection.row_count = count
        await self.session.flush()

        return count

    async def insert_rows(
        self,
        collection: Collection,
        rows: List[dict],
    ) -> int:
        """
        Insert rows into collection table.
        
        Args:
            collection: Collection object
            rows: List of row dictionaries
        
        Returns:
            Number of inserted rows
        """
        if not rows:
            return 0

        field_names = [f["name"] for f in collection.fields]
        columns = ", ".join(field_names)
        placeholders = ", ".join([f":{name}" for name in field_names])

        insert_sql = text(
            f"INSERT INTO {collection.table_name} ({columns}) VALUES ({placeholders})"
        )

        for row in rows:
            filtered_row = {k: v for k, v in row.items() if k in field_names}
            await self.session.execute(insert_sql, filtered_row)

        collection.row_count += len(rows)
        await self.session.flush()

        return len(rows)

    async def search(
        self,
        collection: Collection,
        filters: dict,
        limit: int = 50,
        offset: int = 0,
        query: Optional[str] = None,
    ) -> List[dict]:
        """
        Search collection with filters.
        
        Args:
            collection: Collection object
            filters: Dict of field_name -> value or {op: value}
            limit: Max results
            offset: Offset for pagination
            query: Free text search query (searches all LIKE fields with OR)
        
        Returns:
            List of matching rows as dicts
        """
        where_clauses = []
        params = {}

        # Handle free text query - search across all LIKE fields with OR
        if query:
            like_clauses = []
            for field_def in collection.get_searchable_fields():
                field_name = field_def["name"]
                search_mode = field_def.get("search_mode", SearchMode.EXACT.value)
                if search_mode == SearchMode.LIKE.value:
                    like_clauses.append(f"{field_name} ILIKE :query_param")
            if like_clauses:
                params["query_param"] = f"%{query}%"
                where_clauses.append(f"({' OR '.join(like_clauses)})")

        # Handle specific field filters
        for field_def in collection.get_searchable_fields():
            field_name = field_def["name"]
            if field_name not in filters:
                continue

            value = filters[field_name]
            search_mode = field_def.get("search_mode", SearchMode.EXACT.value)

            if search_mode == SearchMode.LIKE.value:
                where_clauses.append(f"{field_name} ILIKE :p_{field_name}")
                params[f"p_{field_name}"] = f"%{value}%"

            elif search_mode == SearchMode.RANGE.value:
                if isinstance(value, dict):
                    if "from" in value:
                        where_clauses.append(f"{field_name} >= :p_{field_name}_from")
                        params[f"p_{field_name}_from"] = value["from"]
                    if "to" in value:
                        where_clauses.append(f"{field_name} <= :p_{field_name}_to")
                        params[f"p_{field_name}_to"] = value["to"]
                else:
                    where_clauses.append(f"{field_name} = :p_{field_name}")
                    params[f"p_{field_name}"] = value

            else:
                where_clauses.append(f"{field_name} = :p_{field_name}")
                params[f"p_{field_name}"] = value

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

        sql_query = text(
            f"SELECT * FROM {collection.table_name} "
            f"WHERE {where_sql} "
            f"ORDER BY _created_at DESC "
            f"LIMIT :limit OFFSET :offset"
        )
        params["limit"] = limit
        params["offset"] = offset

        result = await self.session.execute(sql_query, params)
        rows = result.mappings().all()

        return [dict(row) for row in rows]

    async def count(
        self,
        collection: Collection,
        filters: dict,
        query: Optional[str] = None,
    ) -> int:
        """Count matching rows"""
        where_clauses = []
        params = {}

        # Handle free text query - search across all LIKE fields with OR
        if query:
            like_clauses = []
            for field_def in collection.get_searchable_fields():
                field_name = field_def["name"]
                search_mode = field_def.get("search_mode", SearchMode.EXACT.value)
                if search_mode == SearchMode.LIKE.value:
                    like_clauses.append(f"{field_name} ILIKE :query_param")
            if like_clauses:
                params["query_param"] = f"%{query}%"
                where_clauses.append(f"({' OR '.join(like_clauses)})")

        for field_def in collection.get_searchable_fields():
            field_name = field_def["name"]
            if field_name not in filters:
                continue

            value = filters[field_name]
            search_mode = field_def.get("search_mode", SearchMode.EXACT.value)

            if search_mode == SearchMode.LIKE.value:
                where_clauses.append(f"{field_name} ILIKE :p_{field_name}")
                params[f"p_{field_name}"] = f"%{value}%"
            elif search_mode == SearchMode.RANGE.value:
                if isinstance(value, dict):
                    if "from" in value:
                        where_clauses.append(f"{field_name} >= :p_{field_name}_from")
                        params[f"p_{field_name}_from"] = value["from"]
                    if "to" in value:
                        where_clauses.append(f"{field_name} <= :p_{field_name}_to")
                        params[f"p_{field_name}_to"] = value["to"]
                else:
                    where_clauses.append(f"{field_name} = :p_{field_name}")
                    params[f"p_{field_name}"] = value
            else:
                where_clauses.append(f"{field_name} = :p_{field_name}")
                params[f"p_{field_name}"] = value

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

        sql_query = text(
            f"SELECT COUNT(*) FROM {collection.table_name} WHERE {where_sql}"
        )

        result = await self.session.execute(sql_query, params)
        return result.scalar()

    async def delete_rows(self, collection: Collection, ids: List[int]) -> int:
        """
        Delete rows from collection by IDs.
        
        Args:
            collection: Collection object
            ids: List of row IDs to delete
        
        Returns:
            Number of deleted rows
        """
        if not ids:
            return 0

        placeholders = ", ".join([f":id_{i}" for i in range(len(ids))])
        params = {f"id_{i}": id_val for i, id_val in enumerate(ids)}

        delete_sql = text(
            f"DELETE FROM {collection.table_name} WHERE _id IN ({placeholders})"
        )

        result = await self.session.execute(delete_sql, params)
        deleted_count = result.rowcount

        collection.row_count = max(0, collection.row_count - deleted_count)
        await self.session.flush()

        return deleted_count
