"""
services/collection — collection sub-services package.

Re-exports the shared components for external use.
CollectionService itself remains at services/collection_service.py for
backward compatibility with existing imports.
"""
from app.services.collection.ddl import (
    FIELD_TYPE_TO_PG,
    build_create_table_sql,
    build_indexes_sql,
    build_drop_indexes_sql,
    apply_typed_binds,
    VECTOR_INFRA_ALTER_SQL,
    VECTOR_STATUS_INDEX_SQL,
)
from app.services.collection.field_coercion import (
    coerce_value,
    validate_and_prepare_payload,
    parse_string_bool,
    parse_datetime,
    parse_date,
)
from app.services.collection.version_service import CollectionVersionService
from app.services.collection.row_service import CollectionRowService
from app.services.collection.vector_lifecycle import CollectionVectorLifecycleService
from app.services.collection.schema_contract_service import CollectionSchemaContractService
from app.services.collection.query_service import CollectionQueryService

__all__ = [
    "FIELD_TYPE_TO_PG",
    "build_create_table_sql",
    "build_indexes_sql",
    "build_drop_indexes_sql",
    "apply_typed_binds",
    "VECTOR_INFRA_ALTER_SQL",
    "VECTOR_STATUS_INDEX_SQL",
    "coerce_value",
    "validate_and_prepare_payload",
    "parse_string_bool",
    "parse_datetime",
    "parse_date",
    "CollectionVersionService",
    "CollectionRowService",
    "CollectionVectorLifecycleService",
    "CollectionSchemaContractService",
    "CollectionQueryService",
]
