from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.services.status_aggregator import calculate_aggregate_status


def _node(node_key: str, status: str):
    return SimpleNamespace(node_key=node_key, status=status, error_short=None, updated_at=None)


def test_effective_status_archived_has_priority():
    agg_status, details = calculate_aggregate_status(
        doc_id=uuid4(),
        pipeline_nodes=[_node("upload", "completed")],
        embedding_nodes=[],
        target_models=["emb.a"],
        index_nodes=[_node("emb.a", "completed")],
        archived=True,
        default_model_alias="emb.a",
        tenant_secondary_model_alias=None,
        model_availability={"emb.a": True},
    )
    assert agg_status in {"ready", "partial", "processing", "uploaded", "failed"}
    assert details["effective_status"] == "archived"


def test_effective_status_processing_when_active_stage_exists():
    _, details = calculate_aggregate_status(
        doc_id=uuid4(),
        pipeline_nodes=[_node("extract", "processing")],
        embedding_nodes=[],
        target_models=["emb.a"],
        index_nodes=[],
        archived=False,
        default_model_alias="emb.a",
        tenant_secondary_model_alias=None,
        model_availability={"emb.a": True},
    )
    assert details["effective_status"] == "processing"


def test_effective_status_available_when_default_ready_and_healthy():
    _, details = calculate_aggregate_status(
        doc_id=uuid4(),
        pipeline_nodes=[_node("upload", "completed"), _node("extract", "completed"), _node("normalize", "completed"), _node("chunk", "completed")],
        embedding_nodes=[],
        target_models=["emb.a"],
        index_nodes=[_node("emb.a", "completed")],
        archived=False,
        default_model_alias="emb.a",
        tenant_secondary_model_alias="emb.b",
        model_availability={"emb.a": True, "emb.b": False},
    )
    assert details["effective_status"] == "available"


def test_effective_status_extended_when_default_and_secondary_ready():
    _, details = calculate_aggregate_status(
        doc_id=uuid4(),
        pipeline_nodes=[_node("upload", "completed"), _node("extract", "completed"), _node("normalize", "completed"), _node("chunk", "completed")],
        embedding_nodes=[],
        target_models=["emb.a", "emb.b"],
        index_nodes=[_node("emb.a", "completed"), _node("emb.b", "completed")],
        archived=False,
        default_model_alias="emb.a",
        tenant_secondary_model_alias="emb.b",
        model_availability={"emb.a": True, "emb.b": True},
    )
    assert details["effective_status"] == "extended"


def test_effective_status_limited_when_only_secondary_is_usable():
    _, details = calculate_aggregate_status(
        doc_id=uuid4(),
        pipeline_nodes=[_node("upload", "completed"), _node("extract", "completed"), _node("normalize", "completed"), _node("chunk", "completed")],
        embedding_nodes=[],
        target_models=["emb.a", "emb.b"],
        index_nodes=[_node("emb.a", "completed"), _node("emb.b", "completed")],
        archived=False,
        default_model_alias="emb.a",
        tenant_secondary_model_alias="emb.b",
        model_availability={"emb.a": False, "emb.b": True},
    )
    assert details["effective_status"] == "limited"

