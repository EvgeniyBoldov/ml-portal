from uuid import uuid4

import pytest

from app.models.glossary import GlossaryEntry, GlossaryObservation, GlossaryStatus
from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.glossary_reconciler import GlossaryReconciler


class _Result:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, results) -> None:
        self._results = list(results)
        self.added = []

    async def execute(self, _statement):
        return _Result(self._results.pop(0) if self._results else None)

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None


def _candidate(*, source_ref: str) -> FactDTO:
    return FactDTO(
        scope=FactScope.TENANT,
        kind="glossary",
        subject="evpn",
        value="Ethernet VPN",
        source=FactSource.USER_UTTERANCE,
        metadata={
            "aliases": ["Ethernet VPN", "ethernet vpn"],
            "evidence": [{
                "source_type": "user_message",
                "source_ref": source_ref,
                "label": "user message",
            }],
        },
    )


@pytest.mark.asyncio
async def test_first_glossary_candidate_is_pending_with_one_observation() -> None:
    session = _Session([None, None])

    changed = await GlossaryReconciler(session).apply(
        candidates=[_candidate(source_ref="turn-1")],
        user_id=uuid4(),
        tenant_id=uuid4(),
    )

    entry = next(item for item in session.added if isinstance(item, GlossaryEntry))
    observation = next(item for item in session.added if isinstance(item, GlossaryObservation))
    assert changed == 1
    assert entry.status == GlossaryStatus.PENDING.value
    assert entry.support_count == 1
    assert entry.aliases == ["Ethernet VPN"]
    assert observation.source_ref == "turn-1"


@pytest.mark.asyncio
async def test_third_independent_evidence_confirms_glossary_candidate() -> None:
    entry = GlossaryEntry(
        id=uuid4(), scope="tenant", tenant_id=uuid4(), canonical_term="evpn",
        aliases=[], status=GlossaryStatus.PENDING.value, support_count=2,
    )
    session = _Session([entry, None])

    changed = await GlossaryReconciler(session).apply(
        candidates=[_candidate(source_ref="turn-3")], user_id=uuid4(), tenant_id=entry.tenant_id,
    )

    assert changed == 1
    assert entry.status == GlossaryStatus.CONFIRMED.value
    assert entry.support_count == 3
    assert entry.first_confirmed_at is not None


@pytest.mark.asyncio
async def test_existing_evidence_does_not_increase_candidate_support() -> None:
    entry = GlossaryEntry(
        id=uuid4(), scope="tenant", tenant_id=uuid4(), canonical_term="evpn",
        aliases=[], status=GlossaryStatus.PENDING.value, support_count=1,
    )
    session = _Session([entry, object()])

    changed = await GlossaryReconciler(session).apply(
        candidates=[_candidate(source_ref="turn-1")], user_id=uuid4(), tenant_id=entry.tenant_id,
    )

    assert changed == 0
    assert entry.status == GlossaryStatus.PENDING.value
    assert entry.support_count == 1
