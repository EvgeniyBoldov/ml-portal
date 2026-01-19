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

from app.models.collection import Collection, CollectionType, FieldType, SearchMode


FIELD_TYPE_TO_PG = {
    FieldType.TEXT.value: "TEXT",
    FieldType.INTEGER.value: "BIGINT",
    FieldType.FLOAT.value: "DOUBLE PRECISION",
    FieldType.BOOLEAN.value: "BOOLEAN",
    FieldType.DATETIME.value: "TIMESTAMPTZ",
    FieldType.DATE.value: "DATE",
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
        """Validate fields schema"""
        if not fields:
            raise InvalidSchemaError("At least one field is required")

        field_names = set()
        reserved_names = {"id", "_created_at", "_updated_at"}

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

            search_mode = field.get("search_mode")
            if search_mode and search_mode not in [sm.value for sm in SearchMode]:
                raise InvalidSchemaError(
                    f"Invalid search mode '{search_mode}' for field '{name}'"
                )

            if search_mode == SearchMode.LIKE.value and field_type != FieldType.TEXT.value:
                raise InvalidSchemaError(
                    f"Search mode 'like' only valid for text fields, not '{field_type}'"
                )

            if search_mode == SearchMode.RANGE.value and field_type not in [
                FieldType.INTEGER.value,
                FieldType.FLOAT.value,
                FieldType.DATETIME.value,
                FieldType.DATE.value,
            ]:
                raise InvalidSchemaError(
                    f"Search mode 'range' not valid for field type '{field_type}'"
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
        """Build CREATE INDEX statements for searchable fields"""
        indexes = []

        for field in fields:
            if not field.get("searchable", False):
                continue

            name = field["name"]
            search_mode = field.get("search_mode", SearchMode.EXACT.value)
            field_type = field["type"]

            if search_mode == SearchMode.LIKE.value:
                indexes.append(
                    f"CREATE INDEX idx_{table_name}_{name}_trgm "
                    f"ON {table_name} USING GIN ({name} gin_trgm_ops)"
                )
            elif search_mode == SearchMode.RANGE.value:
                indexes.append(
                    f"CREATE INDEX idx_{table_name}_{name}_btree "
                    f"ON {table_name} ({name})"
                )
            else:
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
        collection_type: CollectionType = CollectionType.SQL,
    ) -> Collection:
        """
        Create a new collection with its dynamic table.
        
        Args:
            tenant_id: Tenant UUID
            slug: Unique identifier (within tenant)
            name: Human-readable name
            fields: List of field definitions
            description: Optional description for LLM
            collection_type: Type of collection (sql, vector, hybrid)
        
        Returns:
            Created Collection object
        """
        self._validate_slug(slug)
        self._validate_fields(fields)

        existing = await self.get_by_slug(tenant_id, slug)
        if existing:
            raise CollectionExistsError(f"Collection '{slug}' already exists")

        table_name = self._generate_table_name(tenant_id, slug)

        collection = Collection(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            slug=slug,
            name=name,
            description=description,
            type=collection_type.value,
            fields=fields,
            table_name=table_name,
            row_count=0,
            is_active=True,
        )

        create_table_sql = self._build_create_table_sql(table_name, fields)
        await self.session.execute(text(create_table_sql))

        await self.session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        for index_sql in self._build_indexes_sql(table_name, fields):
            await self.session.execute(text(index_sql))

        self.session.add(collection)
        await self.session.flush()

        return collection

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
    ) -> List[dict]:
        """
        Search collection with filters.
        
        Args:
            collection: Collection object
            filters: Dict of field_name -> value or {op: value}
            limit: Max results
            offset: Offset for pagination
        
        Returns:
            List of matching rows as dicts
        """
        where_clauses = []
        params = {}

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

        query = text(
            f"SELECT * FROM {collection.table_name} "
            f"WHERE {where_sql} "
            f"ORDER BY _created_at DESC "
            f"LIMIT :limit OFFSET :offset"
        )
        params["limit"] = limit
        params["offset"] = offset

        result = await self.session.execute(query, params)
        rows = result.mappings().all()

        return [dict(row) for row in rows]

    async def count(self, collection: Collection, filters: dict) -> int:
        """Count matching rows"""
        where_clauses = []
        params = {}

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

        query = text(
            f"SELECT COUNT(*) FROM {collection.table_name} WHERE {where_sql}"
        )

        result = await self.session.execute(query, params)
        return result.scalar()
