from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.routers.collections.stream_shared import _resolve_document_membership


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_resolve_document_membership_no_source():
    tenant_id = uuid4()
    collection_id = uuid4()
    doc_id = uuid4()

    class _Session:
        async def execute(self, *_args, **_kwargs):
            return _ScalarResult(None)

    membership = await _resolve_document_membership(
        session=_Session(),
        tenant_id=tenant_id,
        collection_id=collection_id,
        doc_id=doc_id,
    )

    assert membership.source is None
    assert membership.in_tenant is False
    assert membership.in_collection is False


@pytest.mark.asyncio
async def test_resolve_document_membership_foreign_collection():
    tenant_id = uuid4()
    collection_id = uuid4()
    foreign_collection_id = uuid4()
    doc_id = uuid4()
    source = SimpleNamespace(meta={"collection": {"id": str(foreign_collection_id)}})

    class _Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return _ScalarResult(None)  # explicit membership missing
            return _ScalarResult(source)  # fallback source lookup

    membership = await _resolve_document_membership(
        session=_Session(),
        tenant_id=tenant_id,
        collection_id=collection_id,
        doc_id=doc_id,
    )

    assert membership.source is source
    assert membership.in_tenant is True
    assert membership.in_collection is False


@pytest.mark.asyncio
async def test_resolve_document_membership_without_membership_is_not_in_collection():
    tenant_id = uuid4()
    collection_id = uuid4()
    doc_id = uuid4()
    source = SimpleNamespace(meta={})

    class _Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return _ScalarResult(None)  # explicit membership missing
            return _ScalarResult(source)  # fallback source lookup

    membership = await _resolve_document_membership(
        session=_Session(),
        tenant_id=tenant_id,
        collection_id=collection_id,
        doc_id=doc_id,
    )

    assert membership.source is source
    assert membership.in_tenant is True
    assert membership.in_collection is False
