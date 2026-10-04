"""Administrative links editing, using only synthetic rows in a disposable schema."""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.api.v1.routers.admin import semantic_memory as routes
from app.core.config import get_settings
from app.models.document_memory_staging import (
    DocumentMemorySnapshot, GlossaryTerm, MemoryCandidateDecision, MemoryExtractionCandidate,
)
from app.models.memory import MemoryClaim, MemoryItem
from app.models.memory_scope import MemoryCandidateScope, MemoryClaimScope, MemoryScope
from app.runtime.memory.read_policy import applicable_claim
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService, _scope_signature
from app.services.memory_links_service import MemoryLinksService

pytestmark = pytest.mark.skipif(os.getenv("MEMORY_WORKFLOW_PG") != "1", reason="requires opt-in PostgreSQL")


@pytest_asyncio.fixture
async def db():
    schema = "memory_links_" + uuid4().hex
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    scoped = None
    tables = ("memory_items", "memory_claims", "memory_scopes", "memory_claim_scopes",
              "memory_candidate_scopes", "memory_extraction_candidates", "memory_candidate_decisions",
              "glossary_terms", "memory_candidate_project_bindings", "document_memory_snapshots",
              "memory_candidate_scope_proposals", "memory_scope_proposals", "memory_scope_glossary_terms",
              "memory_conflict_cases", "memory_conflict_members", "memory_item_sources")
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            for table in tables:
                await conn.execute(text(f'CREATE TABLE "{schema}".{table} (LIKE public.{table} INCLUDING ALL)'))
        scoped = create_async_engine(get_settings().ASYNC_DB_URL,
            connect_args={"server_settings": {"search_path": f'"{schema}",public'}})
        async with AsyncSession(scoped, expire_on_commit=False) as session:
            yield session
            await session.rollback()
    finally:
        if scoped:
            await scoped.dispose()
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


async def seed(db, *, resolved=True):
    old = MemoryScope(scope_type="team", key="team.old", name="Old team")
    team = MemoryScope(scope_type="team", key="team.ops", name="Operations")
    project = MemoryScope(scope_type="project", key="project.test", name="Test project")
    term = GlossaryTerm(canonical_term="Network", normalized_term="network", definition="Synthetic definition")
    db.add_all([old, team, project, term])
    await db.flush()
    content = {"statement": "Record equipment", "effect": "require", "conditions": ["Before changes"]}
    item = MemoryItem(scope="company", item_type="rule", subject="Equipment", normalized_subject="equipment",
                      scope_signature=_scope_signature([old]), content=content, content_text="Synthetic content",
                      applicability={}, visibility={"mode": "source"})
    db.add(item)
    await db.flush()
    candidates, claims = [], []
    for ordinal in range(2 if resolved else 1):
        snapshot = DocumentMemorySnapshot(document_id=uuid4(), canonical_checksum=uuid4().hex,
                                          status="approved" if resolved else "awaiting_review")
        db.add(snapshot)
        await db.flush()
        candidate = MemoryExtractionCandidate(snapshot_id=snapshot.id, ordinal=ordinal, candidate_type="rule",
            subject=item.subject, normalized_subject=item.normalized_subject, content=content,
            content_text=item.content_text, scope_candidate="scoped", evidence_section_ids=["s1"],
            resolution_status="resolved" if resolved else "needs_review",
            related_entities=[{"type": "system", "name": "Synthetic system"}], visibility_tenant_id=uuid4())
        db.add(candidate)
        await db.flush()
        db.add(MemoryCandidateScope(candidate_id=candidate.id, scope_id=old.id, role="applies_to",
                                    status="confirmed", method="manual", confidence=1))
        if resolved:
            claim = MemoryClaim(memory_item_id=item.id, approved_candidate_id=candidate.id,
                document_id=snapshot.document_id, canonical_checksum=snapshot.canonical_checksum, scope="company",
                scope_signature=item.scope_signature, item_type="rule", normalized_subject=item.normalized_subject,
                content=content, content_text=item.content_text, evidence_section_ids=["s1"],
                applicability=item.applicability, visibility_tenant_id=candidate.visibility_tenant_id)
            db.add(claim)
            await db.flush()
            db.add(MemoryClaimScope(claim_id=claim.id, scope_id=old.id))
            claims.append(claim)
        candidates.append(candidate)
    await db.commit()
    return item, old, team, project, term, candidates, claims


@pytest.mark.asyncio
async def test_published_atom_updates_all_sources_and_runtime_filter_without_changing_evidence(db):
    item, old, team, project, term, candidates, claims = await seed(db)
    visibility = [claim.visibility_tenant_id for claim in claims]
    await MemoryLinksService(db).update_item(item_id=item.id, actor_id=uuid4(),
        scope_ids=[team.id, project.id], glossary_term_ids=[term.id])
    await db.commit()
    for candidate, claim, tenant_id in zip(candidates, claims, visibility):
        bindings = (await db.execute(select(MemoryCandidateScope.scope_id, MemoryCandidateScope.status)
                                     .where(MemoryCandidateScope.candidate_id == candidate.id))).all()
        assert dict(bindings) == {old.id: "rejected", team.id: "confirmed", project.id: "confirmed"}
        assert set(await db.scalars(select(MemoryClaimScope.scope_id).where(MemoryClaimScope.claim_id == claim.id))) == {team.id, project.id}
        assert candidate.related_entities == [{"type": "system", "name": "Synthetic system"},
            {"type": "glossary_term", "id": str(term.id), "name": "Network"}]
        assert candidate.resolution_status == "resolved" and candidate.visibility_tenant_id == tenant_id
        assert claim.content == item.content and claim.evidence_section_ids == ["s1"]
        assert claim.visibility_tenant_id == tenant_id and claim.applicability == item.applicability
        assert claim.scope_signature == item.scope_signature == _scope_signature([team, project])
    assert item.content_text == "Synthetic content" and item.visibility == {"mode": "source"}
    for keys, expected in [(["team.old"], set()), (["team.ops", "project.test"], {claim.id for claim in claims})]:
        assert set(await db.scalars(select(MemoryClaim.id).join(MemoryItem, MemoryItem.id == MemoryClaim.memory_item_id).where(
            applicable_claim(project_ids=[], scope_keys=keys, tenant_id=None)))) == expected
    assert len(list(await db.scalars(select(MemoryCandidateDecision)))) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("project_branch", ["empty", "all", "concrete", "no_scopes"])
async def test_project_selection_distinguishes_all_concrete_and_non_project_memory(db, project_branch):
    item, _, team, project, _, _, claims = await seed(db)
    all_projects = MemoryScope(scope_type="project", key="project.all", name="All projects", is_all=True)
    db.add(all_projects)
    await db.flush()
    selected = [] if project_branch == "no_scopes" else [team.id]
    if project_branch == "all":
        selected.append(all_projects.id)
    elif project_branch == "concrete":
        selected.append(project.id)
    await MemoryLinksService(db).update_item(item_id=item.id, actor_id=uuid4(),
        scope_ids=selected, glossary_term_ids=[])
    await db.commit()
    for keys, expected in [(["team.ops"], project_branch in {"empty", "no_scopes"}),
                           (["team.ops", "project.test"], project_branch in {"all", "concrete"}),
                           (["team.ops", "project.other"], project_branch == "all")]:
        visible = set(await db.scalars(select(MemoryClaim.id).join(MemoryItem, MemoryItem.id == MemoryClaim.memory_item_id)
            .where(MemoryItem.id == item.id, applicable_claim(project_ids=[], scope_keys=keys, tenant_id=None))))
        assert visible == ({claim.id for claim in claims} if expected else set())


@pytest.mark.asyncio
async def test_identity_collision_rejects_edit_without_altering_bindings(db):
    item, old, team, _, _, _, claims = await seed(db)
    duplicate = MemoryItem(scope="company", item_type=item.item_type, subject=item.subject,
        normalized_subject=item.normalized_subject, scope_signature=_scope_signature([team]),
        content=item.content, content_text=item.content_text)
    db.add(duplicate)
    await db.commit()
    item_id, claim_id, old_id = item.id, claims[0].id, old.id
    with pytest.raises(ValueError, match="уже существует"):
        await MemoryLinksService(db).update_item(item_id=item_id, actor_id=uuid4(),
            scope_ids=[team.id], glossary_term_ids=[])
    await db.rollback()
    assert list(await db.scalars(select(MemoryClaimScope.scope_id).where(MemoryClaimScope.claim_id == claim_id))) == [old_id]
    assert not list(await db.scalars(select(MemoryCandidateDecision)))


@pytest.mark.asyncio
async def test_approval_failure_rolls_back_submitted_links(db, monkeypatch):
    _, old, team, _, term, candidates, _ = await seed(db, resolved=False)
    candidate_id, old_id = candidates[0].id, old.id
    dispatch = AsyncMock()
    monkeypatch.setattr(routes, "dispatch_memory_index", dispatch)
    monkeypatch.setattr(ShadowMemoryPublicationService, "approve", AsyncMock(side_effect=ValueError("Synthetic approval failure")))
    request = routes.ShadowCandidateDecisionRequest(tags=routes.ShadowCandidateTagsRequest(
        scope_ids=[team.id], glossary_term_ids=[term.id]))
    with pytest.raises(HTTPException, match="Synthetic approval failure"):
        await routes.approve_shadow_candidate(candidate_id, request, db=db, user=SimpleNamespace(id=str(uuid4())))
    candidate = await db.get(MemoryExtractionCandidate, candidate_id)
    assert candidate.resolution_status == "needs_review"
    assert candidate.related_entities == [{"type": "system", "name": "Synthetic system"}]
    assert list(await db.scalars(select(MemoryCandidateScope.scope_id).where(
        MemoryCandidateScope.candidate_id == candidate_id, MemoryCandidateScope.status == "confirmed"))) == [old_id]
    assert not list(await db.scalars(select(MemoryCandidateDecision)))
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_approval_saves_links_and_returns_published_identity(db, monkeypatch):
    _, _, team, _, term, candidates, _ = await seed(db, resolved=False)
    dispatch = AsyncMock()
    monkeypatch.setattr(routes, "dispatch_memory_index", dispatch)
    response = await routes.approve_shadow_candidate(candidates[0].id,
        routes.ShadowCandidateDecisionRequest(tags=routes.ShadowCandidateTagsRequest(
            scope_ids=[team.id], glossary_term_ids=[term.id])),
        db=db, user=SimpleNamespace(id=str(uuid4())))
    assert response.resolution_status == "resolved" and response.published_item_id is not None
    assert response.scope_ids == [team.id] and response.glossary_term_ids == [term.id]
    dispatch.assert_awaited_once_with({response.published_item_id})


@pytest.mark.asyncio
async def test_manual_approval_accepts_empty_branches_without_separate_confirmation(db, monkeypatch):
    _, _, _, _, _, candidates, _ = await seed(db, resolved=False)
    candidate = candidates[0]
    candidate.scope_candidate = "unknown"
    await db.execute(delete(MemoryCandidateScope).where(MemoryCandidateScope.candidate_id == candidate.id))
    await db.commit()
    monkeypatch.setattr(routes, "dispatch_memory_index", AsyncMock())
    response = await routes.approve_shadow_candidate(candidate.id, routes.ShadowCandidateDecisionRequest(),
        db=db, user=SimpleNamespace(id=str(uuid4())))
    assert response.resolution_status == "resolved" and response.scope_candidate == "global"
    assert response.scope_ids == [] and response.published_item_id is not None
