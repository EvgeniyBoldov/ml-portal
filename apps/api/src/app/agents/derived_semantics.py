from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.collection_resolver import CollectionResolver, ResolvedCollection
from app.models.tool_instance import ToolInstance

DerivedSemanticProfile = ResolvedCollection


async def load_derived_collection_semantic_profile(
    session: AsyncSession,
    instance: ToolInstance,
) -> Optional[DerivedSemanticProfile]:
    resolver = CollectionResolver(session)
    return await resolver.resolve_for_instance(instance)


def build_collection_semantic_profile(
    instance: ToolInstance,
    collection,
) -> DerivedSemanticProfile:
    return CollectionResolver.build(instance=instance, collection=collection)
