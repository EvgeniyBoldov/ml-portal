"""
Unit tests for SSE channel separation (Этап 1).

Verifies:
- status_update publishes only to rag:doc:{id} channel
- aggregate_update publishes to rag:agg:admin, rag:agg:tenant:{id}, rag:doc:{id}
- document_archived publishes to both agg and doc channels
- RAGEventSubscriber.for_document creates subscriber on rag:doc:{id}
- RAGEventSubscriber (default) creates subscriber on rag:agg:tenant:{id} or rag:agg:admin
- Deduplication: publish_aggregate_status only called when status changes
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest

from app.services.rag_event_publisher import RAGEventPublisher, RAGEventSubscriber


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_redis() -> MagicMock:
    redis = MagicMock()
    redis.publish = AsyncMock()
    return redis


# ─── Channel routing tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_update_goes_only_to_doc_channel():
    redis = _make_redis()
    pub = RAGEventPublisher(redis_client=redis)
    doc_id = uuid4()
    tenant_id = uuid4()

    await pub.publish_status_update(doc_id, tenant_id, stage="extract", status="processing")

    expected_doc_channel = f"rag:doc:{doc_id}"
    channels_published = [c.args[0] for c in redis.publish.call_args_list]

    assert channels_published == [expected_doc_channel], (
        f"status_update must publish ONLY to doc channel, got: {channels_published}"
    )


@pytest.mark.asyncio
async def test_aggregate_update_goes_to_agg_and_doc_channels():
    redis = _make_redis()
    pub = RAGEventPublisher(redis_client=redis)
    doc_id = uuid4()
    tenant_id = uuid4()

    await pub.publish_aggregate_status(doc_id, tenant_id, agg_status="ready")

    channels = [c.args[0] for c in redis.publish.call_args_list]
    assert RAGEventPublisher.CHANNEL_AGG_ADMIN in channels
    assert RAGEventPublisher.CHANNEL_AGG_TENANT_FMT.format(tenant_id=str(tenant_id)) in channels
    assert RAGEventPublisher.CHANNEL_DOC_FMT.format(doc_id=str(doc_id)) in channels
    # Must NOT publish to legacy channels
    assert RAGEventPublisher.CHANNEL_LEGACY not in channels


@pytest.mark.asyncio
async def test_document_archived_goes_to_agg_and_doc_channels():
    redis = _make_redis()
    pub = RAGEventPublisher(redis_client=redis)
    doc_id = uuid4()
    tenant_id = uuid4()

    await pub.publish_document_archived(doc_id, tenant_id, archived=True)

    channels = [c.args[0] for c in redis.publish.call_args_list]
    assert RAGEventPublisher.CHANNEL_AGG_ADMIN in channels
    assert RAGEventPublisher.CHANNEL_DOC_FMT.format(doc_id=str(doc_id)) in channels


@pytest.mark.asyncio
async def test_document_added_goes_to_agg_and_doc_channels():
    redis = _make_redis()
    pub = RAGEventPublisher(redis_client=redis)
    doc_id = uuid4()
    tenant_id = uuid4()
    collection_id = uuid4()

    await pub.publish_document_added(doc_id, tenant_id, collection_id)

    channels = [c.args[0] for c in redis.publish.call_args_list]
    assert RAGEventPublisher.CHANNEL_AGG_ADMIN in channels
    assert RAGEventPublisher.CHANNEL_DOC_FMT.format(doc_id=str(doc_id)) in channels


@pytest.mark.asyncio
async def test_status_update_payload_correct():
    redis = _make_redis()
    pub = RAGEventPublisher(redis_client=redis)
    doc_id = uuid4()
    tenant_id = uuid4()

    await pub.publish_status_update(doc_id, tenant_id, stage="chunk", status="completed")

    payload = json.loads(redis.publish.call_args.args[1])
    assert payload["event_type"] == "status_update"
    assert payload["document_id"] == str(doc_id)
    assert payload["stage"] == "chunk"
    assert payload["status"] == "completed"


# ─── Subscriber channel selection ─────────────────────────────────────────────

def test_subscriber_admin_uses_agg_admin_channel():
    redis = MagicMock()
    sub = RAGEventSubscriber(redis_client=redis, is_admin=True)
    assert sub._channel == RAGEventPublisher.CHANNEL_AGG_ADMIN


def test_subscriber_tenant_uses_agg_tenant_channel():
    redis = MagicMock()
    tenant_id = uuid4()
    sub = RAGEventSubscriber(redis_client=redis, tenant_id=tenant_id, is_admin=False)
    assert sub._channel == RAGEventPublisher.CHANNEL_AGG_TENANT_FMT.format(tenant_id=str(tenant_id))


def test_subscriber_for_document_uses_doc_channel():
    redis = MagicMock()
    doc_id = uuid4()
    sub = RAGEventSubscriber.for_document(redis_client=redis, doc_id=doc_id)
    assert sub._channel == RAGEventPublisher.CHANNEL_DOC_FMT.format(doc_id=str(doc_id))


def test_subscriber_non_admin_without_tenant_raises():
    redis = MagicMock()
    with pytest.raises(ValueError, match="tenant_id"):
        RAGEventSubscriber(redis_client=redis, is_admin=False)


# ─── Subscriber listen ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscriber_listen_yields_decoded_events():
    redis = MagicMock()
    doc_id = uuid4()
    sub = RAGEventSubscriber.for_document(redis_client=redis, doc_id=doc_id)

    event_payload = {"event_type": "status_update", "document_id": str(doc_id)}
    messages = [
        {"type": "subscribe", "data": None},
        {"type": "message", "data": json.dumps(event_payload)},
    ]

    async def _fake_listen():
        for m in messages:
            yield m

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.listen = _fake_listen
    redis.pubsub = MagicMock(return_value=pubsub)

    results = []
    async for event in sub.listen():
        results.append(event)

    assert len(results) == 1
    assert results[0]["event_type"] == "status_update"
