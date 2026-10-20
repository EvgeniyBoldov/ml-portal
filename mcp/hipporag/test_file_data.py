"""Private file search never treats absent scopes/indexes as empty retrieval."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import portal
from test_portal import models


def engine(document="file", count=1):
    value = Mock()
    value.chunk_embedding_store.get_all_ids.return_value = [f"chunk{i}" for i in range(count)]
    metadata = {"source_refs": [{"document_id": document, "start": 0, "end": 6}]}
    value.chunk_metadata = {f"chunk{i}": metadata for i in range(count)}
    value.retrieve.return_value = [SimpleNamespace(docs=["Source"], doc_scores=[0.8], doc_metadata=[metadata])]
    return value


class FileDataTests(unittest.TestCase):
    def request(self, namespace="a" * 64):
        return portal.FileIndexRequest(models=models(), namespace=namespace,
            documents=[portal.Document(id="file", content="Source")], expires_at=int(time.time()) + 600)

    def search(self, request, **overrides):
        return portal.FileSearchRequest(**{key: value for key, value in request.model_dump().items() if key != "expires_at"},
            expected_index=portal.graph_identity(portal.file_body(request)), expected_chunks=1, **overrides)

    def marker(self, root, request, *, chunks=1, expiry=None):
        identity = portal.graph_identity(portal.file_body(request))
        path = Path(root) / "portal-indexes" / identity
        path.mkdir(parents=True)
        (path / "ready").write_text(identity)
        (path / "private.json").write_text(json.dumps({"namespace": request.namespace, "status": "ready",
            "chunk_count": chunks, "expires_at": expiry if expiry is not None else request.expires_at}))
        return path

    def test_missing_scope_never_retrieves_or_builds(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "graph") as graph:
            result = portal.search_file(self.search(self.request(), query="treasure"))
            self.assertEqual(result["status"], "not_indexed")
            self.assertEqual(result["error_code"], "document_not_indexed")
            self.assertNotIn("hits", result)
            graph.assert_not_called()

    def test_namespace_revision_and_profile_are_part_of_index_identity(self):
        first = self.request()
        second = self.request("b" * 64)
        self.assertNotEqual(portal.graph_identity(portal.file_body(first)), portal.graph_identity(portal.file_body(second)))
        changed = first.model_copy(update={"models": first.models.model_copy(update={"identity": "c" * 64})})
        self.assertNotEqual(portal.graph_identity(portal.file_body(first)), portal.graph_identity(portal.file_body(changed)))

    def test_missing_chunks_expired_or_building_markers_do_not_mean_no_matches(self):
        for state in ("chunks", "wrong_document", "expired", "building", "ready_missing"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)):
                request = self.request()
                path = self.marker(root, request, expiry=1 if state == "expired" else None)
                if state == "building":
                    value = json.loads((path / "private.json").read_text())
                    value["status"] = "building"
                    (path / "private.json").write_text(json.dumps(value))
                if state == "ready_missing":
                    (path / "ready").unlink()
                value = engine(document="foreign" if state == "wrong_document" else "file",
                               count=1 if state == "wrong_document" else 0)
                with patch.object(portal, "graph", return_value=(value, path.name)) as graph:
                    result = portal.search_file(self.search(request, query="treasure"))
                self.assertEqual(result["status"], "not_indexed")
                value.retrieve.assert_not_called()
                if state not in {"chunks", "wrong_document"}:
                    graph.assert_not_called()

    def test_ready_search_uses_read_only_load_and_preserves_exact_source_refs(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)):
            request = self.request()
            path = self.marker(root, request)
            value = engine()
            with patch.object(portal, "graph", return_value=(value, path.name)) as graph:
                result = portal.search_file(self.search(request, query="treasure"))
                graph.assert_called_once()
                self.assertEqual(graph.call_args.kwargs, {"allow_build": False, "load_only": True})
                self.assertEqual(result["hits"][0]["metadata"]["source_refs"][0]["document_id"], "file")
                self.assertEqual(result["status"], "ready")
                value.retrieve.return_value = [SimpleNamespace(docs=[], doc_scores=[], doc_metadata=[])]
                self.assertEqual(portal.search_file(self.search(request, query="absent"))["hits"], [])

    def test_prepare_does_not_publish_into_shared_corpus(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "graph", return_value=(engine(), "unused")):
            result = portal.prepare_file(self.request())
            self.assertEqual(result["chunk_count"], 1)
            self.assertFalse((Path(root) / "portal-corpus.sqlite").exists())

    def test_load_only_does_not_index_or_extract(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "ENGINES", {}):
            request = self.request()
            path = self.marker(root, request)
            value = Mock()
            with patch.object(portal, "HippoRAG", return_value=value), patch.object(portal, "prepared_passages") as extract:
                portal.graph(portal.file_body(request), allow_build=False, load_only=True)
                extract.assert_not_called()
                value.index.assert_not_called()

    def test_expiry_cleanup_preserves_live_indexes_and_shared_graphs(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "ENGINES", {}):
            live = self.request()
            live_path = self.marker(root, live)
            expired = self.request("b" * 64)
            expired_path = self.marker(root, expired, expiry=1)
            shared = Path(root) / "portal-indexes" / ("c" * 64)
            shared.mkdir()
            (shared / "ready").write_text("shared")
            self.assertEqual(portal.cleanup_file_indexes(), {"deleted": 1})
            self.assertTrue(live_path.exists())
            self.assertFalse(expired_path.exists())
            self.assertTrue(shared.exists())

    def test_native_private_graph_survives_cold_load_without_indexing_or_openie(self):
        request = self.request().model_copy(update={"documents": [portal.Document(id="file", content="Router requires backup.")]})
        key = portal.compute_mdhash_id(request.documents[0].content, prefix="chunk-")
        ner = {key: portal.NerRawOutput(chunk_id=key, response="", unique_entities=["Router", "backup"], metadata={})}
        triples = {key: portal.TripleRawOutput(chunk_id=key, response="", triples=[["Router", "requires", "backup"]], metadata={})}
        def embed(settings, operation, payload):
            self.assertEqual(operation, "embed")
            return {"vectors": [[1.0, 0.0] for _ in payload["texts"]]}
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "ENGINES", {}):
            with patch.object(portal, "callback", side_effect=embed), patch.object(portal.PortalOpenIE, "batch_openie", return_value=(ner, triples)):
                prepared = portal.prepare_file(request)
            identity = prepared["index"]
            portal.ENGINES.pop(identity).close()
            with patch.object(portal.HippoRAG, "index", side_effect=AssertionError("search must not index")), \
                 patch.object(portal.PortalOpenIE, "batch_openie", side_effect=AssertionError("search must not extract")), \
                 patch.object(portal, "callback", side_effect=AssertionError("readiness must not call models")):
                health = portal.search_file(self.search(request))
            self.assertEqual(health["status"], "ready")
            self.assertEqual(health["chunk_count"], 1)
            native = portal.ENGINES[identity]
            with patch.object(portal, "callback", side_effect=embed), patch.object(native, "rerank_facts", return_value=([], [], {})):
                found = portal.search_file(self.search(request, query="backup"))
            self.assertEqual(found["hits"][0]["text"], "Router requires backup.")
            self.assertEqual(found["hits"][0]["metadata"]["source_refs"][0]["document_id"], "file")
            native.close()


if __name__ == "__main__":
    unittest.main()
