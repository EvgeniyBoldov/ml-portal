"""Branch-local overlays for durable user/tenant facts.

Sandbox must not mutate durable memory.  A branch stores only the delta keyed
by ``(scope, subject)``; ``deleted`` tombstones hide a durable fact for that
branch while ``set`` replaces it or adds a new effective fact.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO

OVERLAY_SET = "set"
OVERLAY_DELETED = "deleted"
VALID_STATES = frozenset({OVERLAY_SET, OVERLAY_DELETED})


def normalize_overrides(raw: object) -> dict[str, dict[str, dict[str, Any]]]:
    """Return only valid user/tenant overlay entries from persisted JSON."""
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, dict[str, Any]]] = {}
    for scope in FactScope:
        entries = raw.get(scope.value)
        if not isinstance(entries, dict):
            continue
        clean: dict[str, dict[str, Any]] = {}
        for subject, entry in entries.items():
            if not isinstance(entry, dict) or not isinstance(subject, str) or not subject.strip():
                continue
            state = str(entry.get("state") or "").strip().lower()
            if state not in VALID_STATES:
                continue
            if state == OVERLAY_SET and not _fact_from_entry(scope, subject, entry):
                continue
            clean[subject.strip()] = dict(entry)
        if clean:
            normalized[scope.value] = clean
    return normalized


def apply_overrides(base: Iterable[FactDTO], raw_overrides: object) -> list[FactDTO]:
    """Merge an immutable branch overlay into durable facts."""
    overlays = normalize_overrides(raw_overrides)
    effective = {
        (fact.scope.value, fact.subject): fact
        for fact in base
        if fact.scope in (FactScope.USER, FactScope.TENANT)
    }
    for scope in FactScope:
        for subject, entry in (overlays.get(scope.value) or {}).items():
            key = (scope.value, subject)
            if entry["state"] == OVERLAY_DELETED:
                effective.pop(key, None)
                continue
            fact = _fact_from_entry(scope, subject, entry)
            if fact is not None:
                effective[key] = fact
    return list(effective.values())


def merge_extracted(raw_overrides: object, facts: Iterable[FactDTO]) -> dict[str, dict[str, dict[str, Any]]]:
    """Upsert extracted sandbox facts without disturbing unrelated overrides."""
    merged = normalize_overrides(raw_overrides)
    for fact in facts:
        if fact.scope not in (FactScope.USER, FactScope.TENANT):
            continue
        subject = fact.subject.strip()
        if not subject:
            continue
        merged.setdefault(fact.scope.value, {})[subject] = {
            "state": OVERLAY_SET,
            "fact": fact_to_payload(fact),
        }
    return merged


def fact_to_payload(fact: FactDTO) -> dict[str, Any]:
    return {
        "scope": fact.scope.value,
        "subject": fact.subject,
        "value": fact.value,
        "source": fact.source.value,
        "confidence": fact.confidence,
        "source_ref": fact.source_ref,
    }


def inspector_payload(base: Iterable[FactDTO], raw_overrides: object) -> dict[str, Any]:
    """Safe base/override/effective representation for the sandbox inspector."""
    overlays = normalize_overrides(raw_overrides)
    effective = apply_overrides(base, overlays)
    return {
        "base": _group_facts(base),
        "overrides": overlays,
        "effective": _group_facts(effective),
    }


def _group_facts(facts: Iterable[FactDTO]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {scope.value: [] for scope in FactScope}
    for fact in facts:
        if fact.scope in (FactScope.USER, FactScope.TENANT):
            grouped[fact.scope.value].append(fact_to_payload(fact))
    for entries in grouped.values():
        entries.sort(key=lambda item: str(item["subject"]))
    return grouped


def _fact_from_entry(scope: FactScope, subject: str, entry: dict[str, Any]) -> FactDTO | None:
    payload = entry.get("fact")
    if not isinstance(payload, dict):
        return None
    value = str(payload.get("value") or "").strip()
    if not value:
        return None
    source_raw = str(payload.get("source") or FactSource.USER_UTTERANCE.value)
    try:
        source = FactSource(source_raw)
    except ValueError:
        source = FactSource.USER_UTTERANCE
    return FactDTO(
        scope=scope,
        subject=subject,
        value=value,
        source=source,
        confidence=float(payload.get("confidence") or 1.0),
        source_ref=str(payload.get("source_ref") or "") or None,
        observed_at=datetime.now(timezone.utc),
    )
