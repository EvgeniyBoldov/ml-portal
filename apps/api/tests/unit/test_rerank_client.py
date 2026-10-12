from types import SimpleNamespace

from app.agents.runtime.rerank_client import RerankScoredIndex, apply_rerank_to_items
from app.agents.runtime.rerank_client import _build_rerank_candidate_urls


def test_apply_rerank_to_items_reorders_and_overrides_score():
    items = [
        {"id": "a", "score": 0.9},
        {"id": "b", "score": 0.8},
        {"id": "c", "score": 0.7},
    ]
    reranked = [
        RerankScoredIndex(index=2, score=1.7),
        RerankScoredIndex(index=0, score=1.2),
    ]

    result = apply_rerank_to_items(items, reranked, score_field="score")

    assert [entry["id"] for entry in result] == ["c", "a", "b"]
    assert result[0]["score"] == 1.7
    assert result[1]["score"] == 1.2
    assert result[2]["score"] == 0.8


def test_apply_rerank_to_items_ignores_invalid_indexes():
    items = [
        {"id": "x", "score": 0.6},
        {"id": "y", "score": 0.5},
    ]
    reranked = [
        RerankScoredIndex(index=42, score=10.0),
        RerankScoredIndex(index=-1, score=9.0),
        RerankScoredIndex(index=1, score=1.1),
    ]

    result = apply_rerank_to_items(items, reranked, score_field="score")

    assert [entry["id"] for entry in result] == ["y", "x"]
    assert result[0]["score"] == 1.1
    assert result[1]["score"] == 0.6


def test_build_rerank_candidate_urls_supports_legacy_service_name():
    model = SimpleNamespace(
        base_url="http://reranker:8002",
        instance=None,
        extra_config=None,
    )

    urls = _build_rerank_candidate_urls(model, "http://rerank:8002")

    assert urls == ["http://reranker:8002", "http://rerank:8002"]


def test_selected_bge_never_uses_minilm_fallback():
    model = SimpleNamespace(base_url='http://rerank-bge:8002', instance=None, extra_config=None)
    assert _build_rerank_candidate_urls(model, 'http://rerank:8002') == ['http://rerank-bge:8002']


import pytest
from unittest.mock import AsyncMock
from app.agents.runtime import rerank_client as module


@pytest.mark.asyncio
async def test_http_timeout_comes_from_selected_model(monkeypatch):
    model = SimpleNamespace(base_url='http://rerank-bge:8002', instance=None, extra_config=None,
                            request_timeout_s=120, alias='rerank.bge')
    monkeypatch.setattr(module, '_resolve_active_rerank_model', AsyncMock(return_value=model))
    monkeypatch.setattr(module, 'get_settings', lambda: SimpleNamespace(RERANK_ENABLED=True,
                       RERANK_SERVICE_URL='http://rerank:8002', HTTP_TIMEOUT_SECONDS=30))
    observed = {}
    class Client:
        def __init__(self, **kwargs): observed.update(kwargs)
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            observed['url'], observed['headers'] = url, kwargs.get('headers')
            return SimpleNamespace(status_code=200, json=lambda: {'results': [{'index': 0, 'score': 0.8}]})
    monkeypatch.setattr(module.httpx, 'AsyncClient', Client)
    await module.rerank_scores(session=AsyncMock(), query='q', documents=['doc'], top_k=1)
    assert observed['timeout'] == 120
    assert observed['url'] == 'http://rerank-bge:8002/rerank'
    assert float(observed['headers']['X-Request-Timeout-Seconds']) == 120


def test_unconfigured_tool_timeout_uses_remaining_run_budget():
    from app.agents.runtime.policy import PolicyLimits
    from app.agents.runtime.agent import AgentToolRuntime
    policy = PolicyLimits.from_policy({})
    assert policy.tool_timeout_ms is None
    assert AgentToolRuntime._effective_tool_timeout_s(configured_timeout_ms=policy.tool_timeout_ms,
                                                    remaining_wall_time_ms=210000) == 210
    assert PolicyLimits.from_policy({}, {'tool_timeout_ms': 30000}).tool_timeout_ms == 30000


@pytest.mark.asyncio
async def test_unavailable_selected_model_does_not_fall_back(monkeypatch):
    from app.models.model_registry import ModelStatus
    repo = SimpleNamespace(get_global_by_type=AsyncMock(return_value=SimpleNamespace(
        deleted_at=None, enabled=True, status=ModelStatus.UNAVAILABLE)))
    monkeypatch.setattr(module, 'AsyncModelRegistryRepository', lambda _: repo)
    with pytest.raises(module.RerankClientError, match='selected rerank model'):
        await module._resolve_active_rerank_model(AsyncMock())
