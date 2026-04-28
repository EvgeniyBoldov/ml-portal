from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.fact_selection import FactSelectionPolicy, LexicalFactRanker


def _fact(
    *,
    scope: FactScope,
    subject: str,
    value: str,
    observed_at: datetime,
    confidence: float = 0.9,
    user_id=None,
    tenant_id=None,
) -> FactDTO:
    return FactDTO(
        scope=scope,
        subject=subject,
        value=value,
        source=FactSource.SYSTEM,
        user_id=user_id,
        tenant_id=tenant_id,
        observed_at=observed_at,
        confidence=confidence,
    )


def test_relevant_old_fact_beats_irrelevant_recent_fact():
    now = datetime.now(timezone.utc)
    uid = uuid4()
    tid = uuid4()
    relevant_old = _fact(
        scope=FactScope.USER,
        subject="runtime.mcp",
        value="pipeline uses memory components",
        observed_at=now - timedelta(days=30),
        user_id=uid,
    )
    irrelevant_recent = _fact(
        scope=FactScope.TENANT,
        subject="office.coffee",
        value="beans arrived yesterday",
        observed_at=now - timedelta(hours=1),
        tenant_id=tid,
    )
    policy = FactSelectionPolicy(ranker=LexicalFactRanker())
    result = policy.select(
        query="mcp runtime memory",
        facts=[irrelevant_recent, relevant_old],
        limit=2,
    )

    assert result.selected
    assert result.selected[0].fact.id == relevant_old.id


def test_policy_omits_low_confidence_and_stale_without_query_match():
    now = datetime.now(timezone.utc)
    uid = uuid4()
    stale_low_conf = _fact(
        scope=FactScope.USER,
        subject="misc.note",
        value="unrelated text",
        observed_at=now - timedelta(days=365),
        confidence=0.2,
        user_id=uid,
    )
    strong_match = _fact(
        scope=FactScope.USER,
        subject="runtime.goal",
        value="focus on memory retrieval",
        observed_at=now - timedelta(days=1),
        confidence=0.8,
        user_id=uid,
    )
    policy = FactSelectionPolicy(ranker=LexicalFactRanker())
    result = policy.select(
        query="runtime memory retrieval",
        facts=[stale_low_conf, strong_match],
        limit=2,
    )

    selected_ids = {item.fact.id for item in result.selected}
    assert strong_match.id in selected_ids
    assert stale_low_conf.id not in selected_ids
    assert int(result.diagnostics.get("omitted_low_confidence", 0)) >= 1


def test_policy_marks_contradictions_and_keeps_both_values():
    now = datetime.now(timezone.utc)
    uid = uuid4()
    tid = uuid4()
    user_fact = _fact(
        scope=FactScope.USER,
        subject="incident.owner",
        value="team-alpha",
        observed_at=now - timedelta(hours=2),
        user_id=uid,
    )
    company_fact = _fact(
        scope=FactScope.TENANT,
        subject="incident.owner",
        value="team-bravo",
        observed_at=now - timedelta(hours=3),
        tenant_id=None,
    )
    dept_fact = _fact(
        scope=FactScope.TENANT,
        subject="incident.status",
        value="investigating",
        observed_at=now - timedelta(hours=1),
        tenant_id=tid,
    )
    policy = FactSelectionPolicy(ranker=LexicalFactRanker())
    result = policy.select(
        query="incident owner status",
        facts=[dept_fact, company_fact, user_fact],
        limit=5,
    )

    selected_subject_values = {(item.fact.subject, item.fact.value) for item in result.selected}
    assert ("incident.owner", "team-alpha") in selected_subject_values
    assert ("incident.owner", "team-bravo") in selected_subject_values
    contradictions = set(result.diagnostics.get("contradiction_subjects") or [])
    assert "incident.owner" in contradictions
