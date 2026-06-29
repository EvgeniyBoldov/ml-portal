from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.agents.runtime.published_capabilities import build_published_collection_summary
from app.models.collection import Collection
from app.services.collection.version_service import CollectionVersionService


def test_published_collection_summary_does_not_fallback_to_collection_description():
    collection = SimpleNamespace(
        collection_slug="devices",
        slug="devices",
        collection_type="table",
        name="Devices",
        usage_purpose=None,
        data_description=None,
        usage_rules=None,
        description="legacy description",
        readiness=None,
    )

    summary = build_published_collection_summary(collection, operations=[])

    assert summary.data_description is None
    assert summary.purpose is None


def test_initial_version_does_not_copy_collection_description_into_semantic_fields():
    collection = Collection(
        id=uuid4(),
        data_instance_id=uuid4(),
        tenant_id=uuid4(),
        slug="devices",
        name="Devices",
        description="legacy description",
        collection_type="table",
        status="ready",
        fields=[],
    )

    version = CollectionVersionService.build_initial_version(collection)

    assert version.data_description is None
    assert version.usage_purpose is None
    assert version.usage_rules is None
    assert version.notes == "Initial version"
