from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService, ShadowStudyItem, _scope_proposal


def review(scopes=(), terms=(), proposal_bindings=()):
    attempt = uuid4()
    row = NS(id=uuid4(), snapshot_id=uuid4(), attempt_id=attempt, candidate_type='rule',
             resolution_status='needs_review', scope_candidate='unknown', related_entities=[],
             unresolved_scope_references=[{'reason': 'missing_term'}], related_project_keys=[])
    snapshot = NS(status='awaiting_review', active_attempt_id=attempt)
    db = NS(get=AsyncMock(return_value=snapshot), scalars=AsyncMock(), add=Mock(), flush=AsyncMock())
    values = ([NS(all=lambda: list(terms))] if terms else []) + [NS(all=lambda: []), NS(all=lambda: []), NS(all=lambda: list(proposal_bindings))]
    db.scalars.side_effect = values
    service = ShadowMemoryPublicationService(db)
    service._required_candidate = AsyncMock(return_value=row)
    service._scopes_for = AsyncMock(return_value=list(scopes))
    service._confirm_scope_bindings = AsyncMock()
    return service, row, snapshot, db


@pytest.mark.asyncio
async def test_confirm_existing_scope_fixes_unknown_and_preserves_source_visibility():
    scope = NS(id=uuid4(), scope_type='team', is_all=False, project_id=None)
    proposal = NS(id=uuid4(), status='suggested')
    service, row, _, db = review(scopes=[scope], proposal_bindings=[proposal])
    row.visibility_tenant_id = uuid4()
    visibility = row.visibility_tenant_id
    await service.update_review_tags(candidate_id=row.id, actor_id=None, scope_ids=[scope.id],
                                    company_wide=False, glossary_term_ids=[], reason='Правило для команды')
    assert row.scope_candidate == 'scoped'
    assert not row.unresolved_scope_references
    assert row.visibility_tenant_id == visibility
    assert proposal.status == 'superseded'
    assert db.add.call_args.args[0].payload['before']['unresolved_scope_references']
    assert db.add.call_args.args[0].payload['superseded_proposal_bindings'] == [str(proposal.id)]


@pytest.mark.asyncio
@pytest.mark.parametrize('company_wide,expected', [(False, 'unknown'), (True, 'global')])
async def test_empty_selection_and_company_wide_are_distinct(company_wide, expected):
    service, row, _, _ = review()
    await service.update_review_tags(candidate_id=row.id, actor_id=None, scope_ids=[],
                                    company_wide=company_wide, glossary_term_ids=[], reason='Выбор проверяющего')
    assert row.scope_candidate == expected


@pytest.mark.asyncio
async def test_term_links_are_saved_independently_from_applicability():
    term = NS(id=uuid4(), canonical_term='Изменение')
    service, row, _, db = review(terms=[term])
    row.related_entities = [{'type': 'system', 'name': 'Network'}]
    await service.update_review_tags(candidate_id=row.id, actor_id=None, scope_ids=[], company_wide=False,
                                    glossary_term_ids=[term.id], reason='Связано с изменением')
    assert row.scope_candidate == 'global'
    assert row.related_entities == [{'type': 'system', 'name': 'Network'},
                                    {'type': 'glossary_term', 'id': str(term.id), 'name': 'Изменение'}]


@pytest.mark.asyncio
@pytest.mark.parametrize('change,error', [
    ({'company_wide': True, 'scope_ids': [uuid4()]}, 'не совмещается'),
])
async def test_invalid_selections_are_rejected_before_mutation(change, error):
    service, row, _, db = review()
    kwargs = dict(candidate_id=row.id, actor_id=None, scope_ids=[], company_wide=False,
                  glossary_term_ids=[], reason='Обоснование')
    kwargs.update(change)
    with pytest.raises(ValueError, match=error):
        await service.update_review_tags(**kwargs)
    assert not db.add.called
    service._confirm_scope_bindings.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['resolved', 'rejected', 'stale'])
async def test_closed_candidates_cannot_be_retagged(state):
    service, row, _, _ = review()
    row.resolution_status = state
    with pytest.raises(ValueError, match='на проверке'):
        await service.update_review_tags(candidate_id=row.id, actor_id=None, scope_ids=[], company_wide=True,
                                        glossary_term_ids=[], reason='Обоснование')


@pytest.mark.asyncio
async def test_old_attempt_cannot_be_retagged():
    service, row, snapshot, _ = review()
    snapshot.active_attempt_id = uuid4()
    with pytest.raises(ValueError, match='предыдущей попытке'):
        await service.update_review_tags(candidate_id=row.id, actor_id=None, scope_ids=[], company_wide=True,
                                        glossary_term_ids=[], reason='Обоснование')


@pytest.mark.asyncio
async def test_unknown_term_id_does_not_clear_required_scope_blocker():
    service, row, _, db = review()
    db.scalars.side_effect = None
    db.scalars.return_value = NS(all=lambda: [])
    with pytest.raises(ValueError, match='опубликованные термины'):
        await service.update_review_tags(candidate_id=row.id, actor_id=None, scope_ids=[], company_wide=True,
                                        glossary_term_ids=[uuid4()], reason='Обоснование')
    assert row.unresolved_scope_references
    service._confirm_scope_bindings.assert_not_awaited()


@pytest.mark.asyncio
async def test_redundant_all_scope_of_same_type_is_rejected():
    scopes = [NS(id=uuid4(), scope_type='team', is_all=all_value) for all_value in (True, False)]
    service, row, _, _ = review(scopes=scopes)
    with pytest.raises(ValueError, match='того же типа'):
        await service.update_review_tags(candidate_id=row.id, actor_id=None, scope_ids=[scope.id for scope in scopes],
                                        company_wide=False, glossary_term_ids=[], reason='Обоснование')


@pytest.mark.asyncio
async def test_extractor_links_catalog_term_without_changing_scope():
    term = NS(id=uuid4(), canonical_term='Сеть')
    db = NS(scalars=AsyncMock(return_value=NS(all=lambda: [term])))
    row = NS(related_entities=[], scope_candidate='unknown')
    item = ShadowStudyItem(candidate_type='description', subject='Архитектура', glossary_term_ids=[term.id])
    await ShadowDocumentStudyService(db)._persist_term_links(row, item)
    assert row.related_entities == [{'type': 'glossary_term', 'id': str(term.id), 'name': 'Сеть'}]
    assert row.scope_candidate == 'unknown'


def test_existing_scope_tags_resolve_default_unknown_without_widening():
    item = ShadowStudyItem(candidate_type='rule', subject='Backup', scope_keys=['team.ops'])
    assert _scope_proposal(item, {'team.ops': NS(scope_type='team')}, {})[3] == 'scoped'
    assert _scope_proposal(item, {}, {})[3] == 'unknown'


@pytest.mark.asyncio
async def test_extractor_receives_full_glossary_with_stable_ids():
    terms = [NS(id=uuid4(), canonical_term=f'Term {i}', definition='Definition', aliases=[]) for i in range(85)]
    db = NS(execute=AsyncMock(return_value=NS(scalars=lambda: NS(all=lambda: terms))))
    catalog = await ShadowDocumentStudyService(db).glossary_context()
    assert len(catalog) == 85 and catalog[0]['id'] == str(terms[0].id)
    assert 'LIMIT' not in str(db.execute.call_args.args[0])
