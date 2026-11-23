"""Opt-in PostgreSQL parity check in a disposable schema, with synthetic rows."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models.memory import MemoryItem, MemoryClaim
from app.models.memory_scope import MemoryScope, MemoryClaimScope
from app.runtime.memory.read_policy import applicable_claim
from app.runtime.memory.effective_scope import memory_visible_for_scope

pytestmark = pytest.mark.skipif(os.getenv("MEMORY_WORKFLOW_PG") != "1", reason="requires opt-in PostgreSQL")


@pytest.mark.asyncio
async def test_sql_and_prompt_filters_agree_for_flat_scope_bindings():
    schema = "scope_matrix_" + uuid4().hex
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    scoped = None
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            for table in ("memory_items", "memory_claims", "memory_scopes", "memory_claim_scopes", "memory_conflict_cases", "memory_conflict_members"):
                await conn.execute(text(f'CREATE TABLE "{schema}".{table} (LIKE public.{table} INCLUDING ALL)'))
        scoped = create_async_engine(get_settings().ASYNC_DB_URL, connect_args={"server_settings": {"search_path": f'"{schema}",public'}})
        async with AsyncSession(scoped) as session:
            keys = ["company", "ops", "project-a", "project-b"]
            scopes = {key: MemoryScope(scope_type="project", key=key, name=key) for key in keys}
            session.add_all(scopes.values())
            await session.flush()
            atoms = [["company"], ["ops"], ["project-a"], ["ops", "project-a"], ["project-a", "project-b"]]
            claims = []
            for ordinal, bound in enumerate(atoms):
                item = MemoryItem(scope="company", item_type="rule", subject=str(ordinal), normalized_subject=str(ordinal),
                    content={"statement": "synthetic", "effect": "require"}, content_text="synthetic", visibility={})
                session.add(item)
                await session.flush()
                claim = MemoryClaim(memory_item_id=item.id, approved_candidate_id=uuid4(), document_id=uuid4(), canonical_checksum="synthetic", scope="company",
                    item_type="rule", normalized_subject=str(ordinal), content=item.content, content_text="synthetic", evidence_section_ids=[])
                session.add(claim)
                await session.flush()
                session.add_all([MemoryClaimScope(claim_id=claim.id, scope_id=scopes[key].id) for key in bound])
                claims.append(claim)
            await session.flush()
            queries = [[], ["company"], ["ops"], ["project-a"], ["ops", "project-b"], ["other"]]
            for query in queries:
                actual = set((await session.scalars(select(MemoryClaim.id).join(MemoryItem, MemoryItem.id == MemoryClaim.memory_item_id)
                    .where(applicable_claim(project_ids=[], scope_keys=query, tenant_id=None)))).all())
                expected = {claim.id for claim, bound in zip(claims, atoms) if memory_visible_for_scope({"scope_keys": bound}, query)}
                assert actual == expected, query
            await session.rollback()
    finally:
        if scoped:
            await scoped.dispose()
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
