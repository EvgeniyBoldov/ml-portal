def test_ingest_chain_calls_apply_async(monkeypatch):
    from app.services import rag_service
    called = {"ok": False}
    class DummySign:
        def __or__(self, other): return self
        def apply_async(self_inner): called["ok"] = True
    # monkeypatch each task signature .s to return DummySign
    from app.tasks import normalize, chunk, embed, index
    monkeypatch.setattr(normalize.process, "s", lambda *a, **k: DummySign())
    monkeypatch.setattr(chunk.split, "s", lambda *a, **k: DummySign())
    monkeypatch.setattr(embed.compute, "s", lambda *a, **k: DummySign())
    monkeypatch.setattr(index.finalize, "s", lambda *a, **k: DummySign())
    rag_service.start_ingest_chain("doc-1")
    assert called["ok"] is True
