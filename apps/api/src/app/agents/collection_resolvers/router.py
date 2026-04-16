"""Dispatcher that selects a concrete collection resolver by collection_type."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.collection_resolvers.base import BaseCollectionTypeResolver, ResolvedCollection
from app.agents.collection_resolvers.local_document import LocalDocumentCollectionResolver
from app.agents.collection_resolvers.local_table import LocalTableCollectionResolver
from app.agents.collection_resolvers.remote_api import RemoteApiCollectionResolver
from app.agents.collection_resolvers.remote_sql import RemoteSqlCollectionResolver
from app.core.logging import get_logger
from app.models.collection import Collection
from app.models.tool_instance import ToolInstance
from app.services.collection_binding import resolve_bound_collection

logger = get_logger(__name__)


class CollectionResolverRouter:
    def __init__(
        self,
        session: AsyncSession,
        resolvers: Optional[List[BaseCollectionTypeResolver]] = None,
    ) -> None:
        self.session = session
        self.resolvers = resolvers or [
            LocalTableCollectionResolver(),
            LocalDocumentCollectionResolver(),
            RemoteSqlCollectionResolver(),
            RemoteApiCollectionResolver(),
        ]

    async def resolve_for_instance(self, instance: ToolInstance) -> Optional[ResolvedCollection]:
        try:
            collection = await resolve_bound_collection(self.session, instance.config)
        except Exception:
            logger.warning(
                "collection_instance_invalid_binding",
                extra={"instance_slug": instance.slug, "config": instance.config or {}},
            )
            return None
        if not collection:
            return None
        try:
            return self.build(instance=instance, collection=collection)
        except ValueError:
            logger.warning(
                "collection_type_resolver_missing",
                extra={
                    "collection_id": str(collection.id),
                    "collection_slug": collection.slug,
                    "collection_type": collection.collection_type,
                    "instance_slug": instance.slug,
                },
            )
            return None

    def build(self, instance: ToolInstance, collection: Collection) -> ResolvedCollection:
        for resolver in self.resolvers:
            if resolver.supports(collection):
                return resolver.build(instance=instance, collection=collection)
        raise ValueError(
            f"Unsupported collection_type '{collection.collection_type}' for instance '{instance.slug}'"
        )
