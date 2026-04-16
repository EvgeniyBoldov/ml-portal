"""Backward-compatible facade for collection semantic resolvers."""
from __future__ import annotations

from app.agents.collection_resolvers import CollectionResolverRouter, ResolvedCollection
from app.agents.collection_resolvers.local_document import LocalDocumentCollectionResolver
from app.agents.collection_resolvers.local_table import LocalTableCollectionResolver
from app.agents.collection_resolvers.remote_sql import RemoteSqlCollectionResolver


class CollectionResolver(CollectionResolverRouter):
    """Compatibility alias used by runtime code paths."""

    @staticmethod
    def build(instance, collection) -> ResolvedCollection:
        for resolver in (
            LocalTableCollectionResolver(),
            LocalDocumentCollectionResolver(),
            RemoteSqlCollectionResolver(),
        ):
            if resolver.supports(collection):
                return resolver.build(instance=instance, collection=collection)
        return LocalTableCollectionResolver().build(instance=instance, collection=collection)
