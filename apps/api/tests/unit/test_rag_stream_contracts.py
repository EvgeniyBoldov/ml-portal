from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.routers.rag.stream import _ensure_worker_ready, _is_retry_supported, _rag_problem


class TestRagProblem:
    def test_problem_builds_http_exception(self):
        exc = _rag_problem(409, "Ingest already running", "ingest_already_running", stage="extract")
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 409
        assert exc.detail == {
            "error": "Ingest already running",
            "reason": "ingest_already_running",
            "stage": "extract",
        }


class TestRetrySupport:
    def test_extract_supported(self):
        assert _is_retry_supported("extract") is True

    def test_embed_supported(self):
        assert _is_retry_supported("embed.text-embedding-3-small") is True

    def test_index_supported(self):
        assert _is_retry_supported("index.text-embedding-3-small") is True

    def test_chunk_not_supported(self):
        assert _is_retry_supported("chunk") is False


class TestEnsureWorkerReady:
    @pytest.mark.asyncio
    async def test_worker_ready_when_ping_returns_workers(self):
        fake_app = MagicMock()
        fake_app.control.ping.return_value = [{"worker@api": {"ok": "pong"}}]

        with patch("app.celery_app.app", fake_app), patch("asyncio.get_event_loop") as get_loop:
            loop = MagicMock()
            async def run_in_executor(*args, **kwargs):
                return fake_app.control.ping(timeout=2.0)
            loop.run_in_executor = run_in_executor
            get_loop.return_value = loop
            await _ensure_worker_ready()

    @pytest.mark.asyncio
    async def test_worker_not_ready_raises_503(self):
        fake_app = MagicMock()
        fake_app.control.ping.return_value = []

        with patch("app.celery_app.app", fake_app), patch("asyncio.get_event_loop") as get_loop:
            loop = MagicMock()
            async def run_in_executor(*args, **kwargs):
                return []
            loop.run_in_executor = run_in_executor
            get_loop.return_value = loop

            with pytest.raises(HTTPException) as exc_info:
                await _ensure_worker_ready()

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["reason"] == "worker_unavailable"
