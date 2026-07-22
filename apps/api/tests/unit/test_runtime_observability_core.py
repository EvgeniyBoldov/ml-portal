from uuid import uuid4

import pytest
from app.models.runtime_observability import RuntimeBudgetCounter, RuntimeBudgetEntry, RuntimeExecutionEvent
from app.services.runtime_budget_service import RuntimeBudgetService
from app.services.runtime_observation_writer import RuntimeObservationEvent, RuntimeObservationWriter


class _Result:
    def __init__(self, value=None): self.value = value
    def scalar_one_or_none(self): return self.value


class _Session:
    def __init__(self): self.rows = []; self.counter = None
    async def scalar(self, _query): return 0
    async def execute(self, _query): return _Result(self.counter)
    def add(self, value):
        self.rows.append(value)
        if isinstance(value, RuntimeBudgetCounter): self.counter = value
    async def flush(self): return None


@pytest.fixture
def session():
    return _Session()


@pytest.mark.asyncio
async def test_observation_writer_filters_brief_payload(session):
    run_id = uuid4()
    writer = RuntimeObservationWriter(session)
    row = await writer.append(RuntimeObservationEvent(
        run_id=run_id, event_type="llm_called", logging_level="brief",
        payload={"model": "x", "system_prompt": "secret prompt", "tokens_total": 12},
    ))
    assert "system_prompt" not in row.payload
    assert row.payload["system_prompt_length"] > 0
    assert row.payload["tokens_total"] == 12


@pytest.mark.asyncio
async def test_persisted_budget_rejects_over_limit(session):
    service = RuntimeBudgetService(session)
    run_id = uuid4()
    allowed = await service.consume(run_id=run_id, owner_type="run", owner_id=str(run_id), metric="task_attempts", limit=1)
    rejected = await service.consume(run_id=run_id, owner_type="run", owner_id=str(run_id), metric="task_attempts", limit=1)
    assert allowed.allowed is True
    assert rejected.allowed is False
