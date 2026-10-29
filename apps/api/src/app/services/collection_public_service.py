"""Read-only, allowlisted projection for the application collection catalogue."""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection
from app.models.tenant import Tenants, UserTenants
from app.models.user import Users
from app.schemas.collections_public import (
    CollectionCapabilities, CollectionWorkspace, PublicCollectionCount,
    PublicCollectionField, PublicCollectionReadiness, PublicCollectionResponse,
    PublicCollectionSource, PublishedCollectionVersion,
)

_LOCAL_TYPES = {'table', 'document', 'template'}
_SECRET_FIELD = re.compile(r'(^_|password|secret|token|authorization|credential|connection|headers?|cookie|api_key)', re.I)
_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
_FIELD_TYPES = {'string', 'text', 'integer', 'float', 'boolean', 'datetime', 'date', 'enum', 'json', 'file'}


@dataclass(frozen=True)
class CollectionDisplayMetadata:
    source: PublicCollectionSource
    description: str | None
    purpose: str | None
    version: PublishedCollectionVersion | None


def build_collection_display_metadata(collection: Collection) -> CollectionDisplayMetadata:
    """Build safe display metadata without exposing provider configuration."""
    raw_type = getattr(collection, 'collection_type', '')
    collection_type = str(getattr(raw_type, 'value', raw_type) or '')
    local = collection_type in _LOCAL_TYPES

    version_row = getattr(collection, 'current_version', None)
    raw_version_status = getattr(version_row, 'status', None)
    published = (
        version_row is not None
        and getattr(raw_version_status, 'value', raw_version_status) == 'published'
    )
    version = PublishedCollectionVersion(number=version_row.version) if published else None

    data_instance = getattr(collection, 'data_instance', None)
    source_name = getattr(data_instance, 'name', None)
    if source_name is not None:
        source_name = str(source_name)
        has_control_chars = any(
            ord(character) < 32 or ord(character) == 127 for character in source_name
        )
        source_name = source_name.strip()
        if '://' in source_name or has_control_chars:
            source_name = None

    return CollectionDisplayMetadata(
        source=PublicCollectionSource(
            name=source_name or ('Локальное хранилище' if local else 'Внешний источник'),
            type='local' if local else collection_type,
        ),
        description=getattr(version_row, 'data_description', None) if published else None,
        purpose=getattr(version_row, 'usage_purpose', None) if published else None,
        version=version,
    )


def safe_public_fields(collection) -> list[PublicCollectionField]:
    """Expose schema structure only, never enum values, defaults or source bindings."""
    if collection.collection_type not in _LOCAL_TYPES:
        return []
    fields = []
    for field in collection.fields or []:
        name = str(field.get('name') or '')
        dtype = str(field.get('data_type') or '')
        if (field.get('category') == 'system' or not _IDENTIFIER.fullmatch(name)
                or _SECRET_FIELD.search(name) or dtype not in _FIELD_TYPES):
            continue
        fields.append(PublicCollectionField(name=name, data_type=dtype, required=bool(field.get('required'))))
    return fields


class CollectionPublicService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_platform_admin(self, user_id: str) -> bool:
        return (await self.session.scalar(select(Users.is_admin).where(
            Users.id == UUID(str(user_id)), Users.is_active.is_(True),
            Users.lifecycle_status != 'deprecated',
        ))) is True

    async def workspaces(self, user_id: str) -> list[CollectionWorkspace]:
        query = select(Tenants.id, Tenants.name).where(
            Tenants.is_active.is_(True), Tenants.lifecycle_status != 'deprecated',
        )
        if not await self.is_platform_admin(user_id):
            query = query.join(UserTenants, UserTenants.tenant_id == Tenants.id).where(
                UserTenants.user_id == UUID(str(user_id)),
            )
        rows = (await self.session.execute(query.order_by(Tenants.name, Tenants.id))).all()
        return [CollectionWorkspace(id=row[0], name=row[1]) for row in rows]

    async def can_edit(self, user_id: str, tenant_id: UUID) -> bool:
        if await self.is_platform_admin(user_id):
            return True
        return (await self.session.scalar(select(UserTenants.id).where(
            UserTenants.user_id == UUID(str(user_id)), UserTenants.tenant_id == tenant_id,
            UserTenants.is_tenant_admin.is_(True) | UserTenants.is_data_editor.is_(True),
        ))) is not None

    async def _materialized(self, collection) -> bool:
        if collection.collection_type == 'document':
            return True  # Its contents are the authorized document registry, not a CSV table.
        name = str(getattr(collection, 'table_name', '') or '')
        if not _IDENTIFIER.fullmatch(name):
            return False
        if not await self.session.scalar(text('SELECT to_regclass(:table_name)'), {'table_name': name}):
            return False
        rows = await self.session.execute(text(
            'SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(:table_name) '
            'AND attnum > 0 AND NOT attisdropped'
        ), {'table_name': name})
        columns = set(rows.scalars().all())
        required = {'id', *(field.name for field in safe_public_fields(collection))}
        if collection.collection_type == 'template':
            required.update({'status', 'description', 'template_schema', '_vector_status', '_vector_error', '_vector_chunk_count'})
        return required.issubset(columns)

    async def build(self, collection, *, user_id: str, collection_service) -> PublicCollectionResponse:
        ctype = collection.collection_type
        local = ctype in _LOCAL_TYPES
        materialized = local and await self._materialized(collection)
        editable = await self.can_edit(user_id, collection.tenant_id)
        active = bool(collection.is_active) and getattr(collection, 'lifecycle_status', 'active') != 'deprecated'
        available = materialized and active
        caps = CollectionCapabilities(
            view_content=available,
            view_schema=local and active,
            upload_documents=editable and active and ctype == 'document',
            delete_documents=editable and available and ctype == 'document',
            ingest=editable and available and ctype == 'document',
            manage_memory=editable and available and ctype == 'document',
            upload_csv=editable and active and ctype == 'table',
            mutate_rows=editable and available and ctype == 'table',
            reindex=editable and available and ctype in {'table', 'document'},
            upload_templates=editable and active and ctype == 'template',
            analyze_templates=editable and available and ctype == 'template',
            approve_templates=editable and available and ctype == 'template',
            edit_templates=editable and available and ctype == 'template',
            delete_templates=editable and available and ctype == 'template',
            download=available,
        )
        reasons = {}
        for key, allowed in caps.model_dump().items():
            if allowed:
                continue
            reasons[key] = ('collection_inactive' if not active else
                'external_content_unavailable' if not local else
                'storage_unavailable' if not materialized else
                'editing_permission_required' if key not in {'view_content', 'view_schema', 'download'} and not editable else
                'operation_not_supported')
        count = PublicCollectionCount()
        readiness = 'unknown'
        if available:
            if ctype == 'document':
                value = await collection_service.get_effective_total_rows(collection)
            else:
                value = await collection_service.count(collection)
            kind, unit = {'document': ('documents', 'документов'), 'template': ('templates', 'шаблонов'), 'table': ('rows', 'строк')}[ctype]
            count = PublicCollectionCount(value=value, kind=kind, unit=unit)
            if ctype == 'table':
                readiness = 'ready' if value else 'created'
            else:
                # This method computes a projection without assigning ORM status or flushing.
                snapshot = await collection_service.status_snapshot.get_status_snapshot(collection)
                readiness = snapshot['status'] if snapshot.get('status') in {'created', 'discovered', 'ingesting', 'ready', 'degraded', 'error'} else 'unknown'
        elif local:
            readiness = 'created' if active else 'inactive'
        display = build_collection_display_metadata(collection)
        return PublicCollectionResponse(
            id=collection.id, tenant_id=collection.tenant_id, slug=collection.slug,
            name=collection.name, collection_type=ctype,
            description=display.description,
            purpose=display.purpose,
            version=display.version,
            source=display.source, locality='local' if local else 'remote',
            readiness=PublicCollectionReadiness(status=readiness), count=count,
            fields=safe_public_fields(collection) if caps.view_schema else [],
            capabilities=caps, capability_reasons=reasons,
        )
