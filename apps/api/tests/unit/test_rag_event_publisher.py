from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.rag_event_publisher import RAGEventPublisher


@pytest.fixture
def redis_client() -> AsyncMock:
    redis = AsyncMock()
    redis.publish = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def publisher(redis_client: AsyncMock) -> RAGEventPublisher:
    return RAGEventPublisher(redis_client)


@pytest.mark.asyncio
async def test_publish_status_update_broadcasts_to_all_channels(
    publisher: RAGEventPublisher, redis_client: AsyncMock
):
    tenant_id = uuid4()
    await publisher.publish_status_update(
        doc_id=uuid4(),
        tenant_id=tenant_id,
        stage="extract",
        status="processing",
        metrics={"word_count": 10},
    )

    assert redis_client.publish.await_count == 3
    channels = [call.args[0] for call in redis_client.publish.await_args_list]
    assert RAGEventPublisher.CHANNEL_ADMIN in channels
    assert RAGEventPublisher.CHANNEL_LEGACY in channels
    assert RAGEventPublisher.CHANNEL_TENANT_FMT.format(tenant_id=str(tenant_id)) in channels


@pytest.mark.asyncio
async def test_publish_status_update_payload_shape(
    publisher: RAGEventPublisher, redis_client: AsyncMock
):
    doc_id = uuid4()
    await publisher.publish_status_update(
        doc_id=doc_id,
        tenant_id=uuid4(),
        stage="extract",
        status="completed",
        metrics={"duration_sec": 1.5},
    )

    payload = json.loads(redis_client.publish.await_args_list[0].args[1])
    assert payload["event_type"] == "status_update"
    assert payload["doc_id"] == str(doc_id)
    assert payload["stage"] == "extract"
    assert payload["status"] == "completed"
    assert payload["metrics"] == {"duration_sec": 1.5}


@pytest.mark.asyncio
async def test_publish_aggregate_status_sets_legacy_status_alias(
    publisher: RAGEventPublisher, redis_client: AsyncMock
):
    await publisher.publish_aggregate_status(
        doc_id=uuid4(),
        tenant_id=uuid4(),
        agg_status="ready",
        agg_details={"foo": "bar"},
    )
    payload = json.loads(redis_client.publish.await_args_list[0].args[1])
    assert payload["event_type"] == "aggregate_update"
    assert payload["agg_status"] == "ready"
    assert payload["status"] == "ready"
    assert payload["agg_details"] == {"foo": "bar"}


@pytest.mark.asyncio
async def test_publish_document_archived_and_unarchived(
    publisher: RAGEventPublisher, redis_client: AsyncMock
):
    await publisher.publish_document_archived(doc_id=uuid4(), tenant_id=uuid4(), archived=True)
    archived_payload = json.loads(redis_client.publish.await_args_list[0].args[1])
    assert archived_payload["event_type"] == "document_archived"
    assert archived_payload["archived"] is True

    redis_client.publish.reset_mock()
    await publisher.publish_document_archived(doc_id=uuid4(), tenant_id=uuid4(), archived=False)
    unarchived_payload = json.loads(redis_client.publish.await_args_list[0].args[1])
    assert unarchived_payload["event_type"] == "document_unarchived"
    assert unarchived_payload["archived"] is False
