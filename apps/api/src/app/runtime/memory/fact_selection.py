"""Query-scoped ranking and policy selection for runtime facts."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Protocol, Sequence

from app.models.memory import FactScope
from app.runtime.memory.dto import FactDTO


@dataclass(frozen=True)
class RankedFact:
    fact: FactDTO
    score: float
    lexical_hits: int
    is_stale: bool
    is_low_confidence: bool


@dataclass(frozen=True)
class FactSelectionResult:
    selected: List[RankedFact]
    diagnostics: Dict[str, object]


class FactRanker(Protocol):
    """Ranks facts for one query."""

    def rank(self, *, query: str, facts: Sequence[FactDTO]) -> List[RankedFact]: ...


class LexicalFactRanker:
    """Default keyword-aware ranker used in local runtime."""

    def __init__(
        self,
        *,
        stale_after_days: int = 180,
        low_confidence_threshold: float = 0.45,
    ) -> None:
        self._stale_delta = timedelta(days=max(1, stale_after_days))
        self._low_confidence_threshold = max(0.0, min(float(low_confidence_threshold), 1.0))

    def rank(self, *, query: str, facts: Sequence[FactDTO]) -> List[RankedFact]:
        terms = _query_terms(query)
        now = datetime.now(timezone.utc)
        ranked: List[RankedFact] = []
        for idx, fact in enumerate(facts):
            text = f"{fact.subject} {fact.value}".lower()
            lexical_hits = sum(1 for term in terms if term in text)
            if terms and lexical_hits == 0:
                base = 0.05
            else:
                base = 1.0 + lexical_hits
            scope_boost = 0.20 if fact.scope == FactScope.USER else 0.12
            if fact.scope == FactScope.TENANT and fact.tenant_id is None:
                scope_boost = 0.10
            recency_boost = max(0.0, 0.20 - (idx * 0.01))
            confidence = min(max(float(fact.confidence), 0.0), 1.0)
            score = base + scope_boost + recency_boost + confidence

            observed = fact.observed_at or now
            is_stale = (now - observed) > self._stale_delta
            is_low_confidence = confidence < self._low_confidence_threshold
            ranked.append(
                RankedFact(
                    fact=fact,
                    score=score,
                    lexical_hits=lexical_hits,
                    is_stale=is_stale,
                    is_low_confidence=is_low_confidence,
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked


class FactSelectionPolicy:
    """Selection policy for runtime memory facts.

    Rules:
    * low-confidence and stale facts are included only with lexical support;
    * contradictions by subject preserve at least one fact per distinct value;
    * selection stays query-ranked and bounded by `limit`.
    """

    def __init__(self, *, ranker: FactRanker) -> None:
        self._ranker = ranker

    def select(
        self,
        *,
        query: str,
        facts: Sequence[FactDTO],
        limit: int,
    ) -> FactSelectionResult:
        ranked = self._ranker.rank(query=query, facts=facts)
        prefiltered: List[RankedFact] = []
        omitted_low_confidence = 0
        omitted_stale = 0

        for item in ranked:
            if item.is_low_confidence and item.lexical_hits == 0:
                omitted_low_confidence += 1
                continue
            if item.is_stale and item.lexical_hits == 0:
                omitted_stale += 1
                continue
            prefiltered.append(item)

        contradictions = _contradiction_subjects(prefiltered)
        selected: List[RankedFact] = []
        selected_ids = set()

        # Preserve contradiction visibility: include one representative per value.
        for subject in contradictions:
            by_value: Dict[str, List[RankedFact]] = {}
            for item in prefiltered:
                if item.fact.subject != subject:
                    continue
                norm = _normalize_value(item.fact.value)
                by_value.setdefault(norm, []).append(item)
            for group in by_value.values():
                group.sort(key=lambda entry: entry.score, reverse=True)
                top = group[0]
                if top.fact.id in selected_ids:
                    continue
                selected_ids.add(top.fact.id)
                selected.append(top)

        for item in prefiltered:
            if item.fact.id in selected_ids:
                continue
            selected_ids.add(item.fact.id)
            selected.append(item)

        selected = selected[: max(1, limit)]
        diagnostics: Dict[str, object] = {
            "ranker": self._ranker.__class__.__name__,
            "input_facts": len(facts),
            "candidate_facts": len(prefiltered),
            "selected_facts": len(selected),
            "omitted_low_confidence": omitted_low_confidence,
            "omitted_stale": omitted_stale,
            "contradiction_subjects": contradictions,
        }
        return FactSelectionResult(selected=selected, diagnostics=diagnostics)


def _query_terms(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\wа-яА-ЯёЁ]{3,}", (query or "").lower())
        if token not in {"что", "как", "для", "или", "the", "and", "with"}
    }


def _normalize_value(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _contradiction_subjects(items: Sequence[RankedFact]) -> List[str]:
    subject_values: Dict[str, set[str]] = {}
    for item in items:
        subject_values.setdefault(item.fact.subject, set()).add(_normalize_value(item.fact.value))
    return sorted([subject for subject, values in subject_values.items() if len(values) > 1])
