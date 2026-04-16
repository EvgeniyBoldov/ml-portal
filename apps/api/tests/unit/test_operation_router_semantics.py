from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.derived_semantics import (
    DerivedSemanticProfile,
    build_collection_semantic_profile,
    load_derived_collection_semantic_profile,
)
from app.models.collection import Collection, CollectionStatus
from app.models.tool_instance import ToolInstance


def _make_collection(collection_type: str) -> Collection:
    return Collection(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        slug=f"{collection_type}_collection",
        name=f"{collection_type.title()} Collection",
        description=f"{collection_type.title()} collection description",
        collection_type=collection_type,
        status=CollectionStatus.READY.value,
        table_name=f"{collection_type}_table",
        fields=[
            {
                "name": "file",
                "category": "specific",
                "data_type": "file",
                "required": True,
                "description": "Uploaded file",
            },
            {
                "name": "file_name",
                "category": "specific",
                "data_type": "string",
                "required": False,
                "description": "Original filename",
            },
            {
                "name": "vendor",
                "category": "user",
                "data_type": "text",
                "required": False,
                "description": "Vendor name",
                "filterable": True,
                "sortable": False,
                "used_in_prompt_context": True,
                "used_in_retrieval": collection_type == "table",
            },
        ],
    )


def _make_instance(collection: Collection) -> ToolInstance:
    return ToolInstance(
        id=uuid.uuid4(),
        slug=f"collection-{collection.slug}",
        name=f"Collection: {collection.name}",
        description=collection.description,
        instance_kind="data",
        placement="local",
        domain=f"collection.{collection.collection_type}",
        url="",
        config={
            "binding_type": "collection_asset",
            "collection_id": str(collection.id),
            "collection_slug": collection.slug,
            "tenant_id": str(collection.tenant_id),
            "collection_type": collection.collection_type,
            "table_name": collection.table_name,
        },
        is_active=True,
    )


def test_build_collection_semantic_profile_for_table_collection():
    collection = _make_collection("table")
    instance = _make_instance(collection)

    profile = build_collection_semantic_profile(instance, collection)

    assert isinstance(profile, DerivedSemanticProfile)
    assert profile.id == f"derived:{collection.id}"
    assert profile.entity_types == ["record"]
    assert profile.summary == collection.description
    assert "structured search" in (profile.use_cases or "")
    assert profile.schema_hints is not None
    assert profile.schema_hints["collection_type"] == "table"
    assert profile.schema_hints["filterable_fields"] == ["vendor"]
    assert profile.schema_hints["retrieval_fields"] == ["vendor"]
    assert profile.examples["field_counts"]["user"] == 1


def test_build_collection_semantic_profile_for_document_collection():
    collection = _make_collection("document")
    instance = _make_instance(collection)

    profile = build_collection_semantic_profile(instance, collection)

    assert profile.entity_types == ["document"]
    assert "uploaded documents" in (profile.use_cases or "")
    assert "platform-managed and immutable" in (profile.limitations or "")
    assert profile.schema_hints is not None
    assert profile.schema_hints["collection_type"] == "document"
    assert {field["name"] for field in profile.schema_hints["specific_fields"]} >= {"file", "file_name"}


def test_build_collection_semantic_profile_prefers_current_collection_version():
    collection = _make_collection("table")
    instance = _make_instance(collection)
    collection.current_version = SimpleNamespace(
        version=3,
        semantic_profile={
            "summary": "Current semantic summary",
            "entity_types": ["sale_record"],
            "use_cases": "Versioned use-cases",
            "limitations": "Versioned limitations",
            "examples": {"from_version": True},
        },
        retrieval_params={"vector_fields": ["vendor"]},
        prompt_context_params={"context_fields": ["vendor"]},
    )

    profile = build_collection_semantic_profile(instance, collection)

    assert profile.id == f"collection:{collection.id}:v3"
    assert profile.summary == "Current semantic summary"
    assert profile.entity_types == ["sale_record"]
    assert profile.use_cases == "Versioned use-cases"
    assert "Versioned limitations" in (profile.limitations or "")
    assert profile.schema_hints is not None
    assert profile.schema_hints["retrieval_fields"] == ["vendor"]
    assert profile.examples == {"from_version": True}


@pytest.mark.asyncio
async def test_load_active_semantic_profile_derives_from_collection_when_no_stored_profile():
    collection = _make_collection("table")
    instance = _make_instance(collection)

    result = SimpleNamespace(scalar_one_or_none=lambda: collection)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    profile = await load_derived_collection_semantic_profile(session, instance)

    assert isinstance(profile, DerivedSemanticProfile)
    assert profile.id == f"derived:{collection.id}"
    session.execute.assert_awaited_once()
