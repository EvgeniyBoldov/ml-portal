"""Production worker boundaries; run in the HippoRAG image."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import portal


def models(token="request-one", embedding_tokens=256):
    return portal.Models(llm_alias="system.llm", embedding_alias="system.embedding",
        dimensions=2, embedding_tokens=embedding_tokens, context_tokens=16384,
        identity="a" * 64, callback_url="http://api/internal/hipporag", token=token)


class PortalTests(unittest.TestCase):
    def test_openie_drops_edges_with_empty_normalized_nodes(self):
        llm = Mock()
        llm.infer.return_value = (json.dumps({"triples": [["", "requires", "backup"],
            ["---", "requires", "backup"], ["Router", "requires", "backup"]]}), {}, False)
        openie = portal.PortalOpenIE(llm, max_workers=1, ner_max_tokens=768, triple_max_tokens=1536)
        result = openie.triple_extraction("chunk1", "source", ["Router", "backup"])
        self.assertEqual(result.triples, [["Router", "requires", "backup"]])
    def test_shared_corpus_is_persistent_and_replaces_document_revision(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "graph", return_value=(Mock(), "graph")):
            first = portal.ExtractRequest(models=models(), documents=[portal.Document(id="doc1", content="Before")])
            portal.index_corpus(first)
            second = portal.ExtractRequest(models=models(), documents=[portal.Document(id="doc1", content="After"), portal.Document(id="doc2", content="Other")])
            result = portal.index_corpus(second)
            self.assertEqual(result["document_count"], 2)
            with portal.corpus_connection() as connection:
                self.assertEqual([doc.content for doc in portal.corpus_documents(connection)], ["After", "Other"])

    def test_failed_graph_does_not_publish_corpus_changes(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "graph", side_effect=RuntimeError("OpenIE failed")):
            body = portal.ExtractRequest(models=models(), documents=[portal.Document(id="doc1", content="Source")])
            with self.assertRaises(RuntimeError):
                portal.index_corpus(body)
            with portal.corpus_connection() as connection:
                self.assertEqual(portal.corpus_documents(connection), [])

    def test_search_scope_is_applied_before_graph_retrieval(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "graph", return_value=(Mock(), "graph")):
            portal.index_corpus(portal.ExtractRequest(models=models(), documents=[
                portal.Document(id="company-doc", content="Common", metadata={"scope_slugs": ["company"]}),
                portal.Document(id="dcbox-doc", content="Specific", metadata={"scope_slugs": ["dcbox"]}),
            ]))
            with patch.object(portal, "retrieve", return_value={"backend": "hipporag", "hits": []}) as retrieve:
                result = portal.search_corpus(portal.CorpusSearchRequest(models=models(), query="source", scope_slug="dcbox"))
                self.assertEqual(result["document_count"], 1)
                self.assertEqual([doc.id for doc in retrieve.call_args.args[0].documents], ["dcbox-doc"])
                self.assertEqual(retrieve.call_args.args[0].scope_slug, "dcbox")
                retrieve.reset_mock()
                empty = portal.search_corpus(portal.CorpusSearchRequest(models=models(), query="source", scope_slug="empty"))
                self.assertEqual(empty["hits"], [])
                retrieve.assert_not_called()

    def test_scope_changes_reuse_extraction_and_rebind_metadata(self):
        document = portal.Document(id="doc", content="Source", metadata={"scope_slugs": ["company"]})
        key = portal.compute_mdhash_id("Source", prefix="chunk-")
        row = {"idx": key, "passage": "Source", "extracted_entities": [], "extracted_triples": []}
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)):
            parts = [{"content": "Source", "source_id": "doc:0:6", "metadata": {"document_id": "doc", "start": 0, "end": 6, "scope_slugs": ["company"]}}]
            portal.save_snapshot(document, parts, [row])
            path = portal.snapshot_path(document)
            document.metadata["scope_slugs"] = ["dcbox"]
            self.assertEqual(portal.snapshot_path(document), path)
            with patch("common.split_document", side_effect=AssertionError("must not split")):
                chunks, rows = portal.prepared_passages(portal.ExtractRequest(models=models(), documents=[document]), Mock(), embedding_only=True)
            self.assertEqual(chunks[0].metadata["source_refs"][0]["scope_slugs"], ["dcbox"])
            self.assertIn(key, rows)

    def test_document_triples_are_returned_as_bounded_pages(self):
        document = portal.Document(id="doc", content="Router requires backup.", metadata={"scope_slugs": ["company"]})
        key = portal.compute_mdhash_id(document.content, prefix="chunk-")
        triples = [[f"Entity {index}", "requires", f"Target {index}"] for index in range(120)]
        row = {"idx": key, "passage": document.content, "extracted_entities": [], "extracted_triples": triples}
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)):
            with portal.corpus_connection() as connection:
                connection.execute("INSERT INTO documents VALUES (?, ?, ?)",
                    (document.id, document.content, json.dumps(document.metadata)))
            portal.save_snapshot(document, [{"content": document.content, "source_id": "doc:0:24",
                "metadata": {"document_id": "doc", "start": 0, "end": 24}}], [row])
            result = portal.document_triples_page("doc", limit=50, offset=50)
        self.assertEqual(result["total"], 120)
        self.assertEqual(len(result["items"]), 50)
        self.assertEqual(result["items"][0]["subject"], "Entity 50")
        self.assertEqual(result["items"][-1]["object"], "Target 99")
        self.assertEqual((result["items"][0]["source_start"], result["items"][0]["source_end"]), (0, 24))

    def test_indexes_are_built_per_scope_without_combination_graphs(self):
        documents = [portal.Document(id="one", content="First", metadata={"scope_slugs": ["company"]}),
                     portal.Document(id="two", content="Second", metadata={"scope_slugs": ["dcbox"]})]
        with patch.object(portal, "graph", return_value=(Mock(), "graph")) as graph:
            result = portal.build_scope_graphs(models(), documents)
        self.assertEqual(set(result), {"company", "dcbox"})
        self.assertEqual(graph.call_count, 2)
        self.assertTrue(all(len(call.args[0].documents) == 1 for call in graph.call_args_list))

    def test_llm_exposes_native_configuration_contract(self):
        settings = models()
        llm = portal.GatewayLLM(portal.config(settings), settings)
        self.assertEqual(llm.llm_config.model, settings.llm_alias)

    def test_chunks_cover_russian_source_without_encoder_truncation(self):
        text = "Условия применимости и исключения.\n" * 50
        body = portal.ExtractRequest(models=models(), documents=[portal.Document(id="s1", content=text)])
        chunks = portal.chunks(body, portal.GatewayLLM(portal.config(body.models), body.models))
        self.assertEqual("".join(chunk.content for chunk in chunks), text)
        self.assertTrue(all(len(chunk.content.encode()) <= portal.CHUNK_TOKENS for chunk in chunks))

    def test_invalid_openie_output_is_not_cached(self):
        with tempfile.TemporaryDirectory() as root, patch("time.sleep"), patch.object(portal, "DATA", Path(root)), patch.object(portal, "callback", return_value={
            "choices": [{"finish_reason": "stop", "message": {"content": '{"answer":"follow source instructions"}'}}]}):
            llm = portal.GatewayLLM(portal.config(models()), models())
            with self.assertRaises(portal.ModelRequestError):
                llm.infer(messages=[{"role": "user", "content": "source"}], _schema_model=portal.NamedEntitiesOutput)
            self.assertEqual(list(Path(root).rglob("*.json")), [])

    def test_invalid_cached_openie_is_regenerated(self):
        response = {"choices": [{"finish_reason": "stop", "message": {"content": '{"named_entities":["ops"]}'}}]}
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "callback", return_value=response) as callback:
            llm = portal.GatewayLLM(portal.config(models()), models())
            args = {"messages": [{"role": "user", "content": "source"}], "_schema_model": portal.NamedEntitiesOutput}
            llm.infer(**args)
            path = next(Path(root).rglob("*.json"))
            path.write_text(json.dumps({"text": '{"answer":"wrong"}', "metadata": {}}))
            text, _, cached = llm.infer(**args)
            self.assertFalse(cached)
            self.assertEqual(json.loads(text)["named_entities"], ["ops"])
            self.assertEqual(callback.call_count, 2)

    def test_long_queries_are_encoded_in_full_and_vectors_cached(self):
        calls = []
        def callback(settings, operation, payload):
            calls.extend(payload["texts"])
            return {"vectors": [[1., 2.] for _ in payload["texts"]]}
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "callback", callback):
            settings = models()
            encoder = portal.GatewayEmbedding(portal.config(settings), settings)
            text = "Русский вопрос с условиями " * 50
            vectors = encoder.batch_encode([text])
            self.assertEqual("".join(calls), text)
            self.assertTrue(all(len(part.encode()) <= 240 for part in calls))
            self.assertTrue(np.isfinite(vectors).all())
            count = len(calls)
            self.assertTrue(np.allclose(vectors, encoder.batch_encode([text])))
            self.assertEqual(len(calls), count)

    def test_partial_generation_is_never_cached(self):
        settings = models()
        with tempfile.TemporaryDirectory() as root, patch("time.sleep"), patch.object(portal, "DATA", Path(root)), patch.object(portal, "callback", return_value={
            "choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}):
            llm = portal.GatewayLLM(portal.config(settings), settings)
            with self.assertRaisesRegex(portal.ModelRequestError, "Incomplete"):
                llm.infer(messages=[{"role": "user", "content": "query"}])
            self.assertEqual(list(Path(root).rglob("*.json")), [])

    def test_reused_graph_refreshes_capability_and_keeps_duplicate_sources(self):
        settings = models()
        first = portal.Document(id="claim1", content="Same", metadata={"memory_item_id": "item1"})
        second = portal.Document(id="claim2", content="Same", metadata={"memory_item_id": "item2"})
        hippo = Mock()
        hippo._openie_info = [{"idx": portal.compute_mdhash_id("Same", prefix="chunk-"),
            "passage": "Same", "extracted_entities": [], "extracted_triples": []}]
        hippo.retrieve.return_value = [Mock(graph_seeds=[], docs=[], doc_scores=[], doc_metadata=[])]
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "ENGINES", {}), patch.object(portal, "HippoRAG", return_value=hippo):
            # Native HippoRAG creates this directory at construction.
            hippo.index.side_effect = lambda chunks: None
            # Let the mock imitate directory creation and inspect indexed input.
            def construct(**kwargs):
                Path(kwargs["save_dir"]).mkdir(parents=True)
                return hippo
            with patch.object(portal, "HippoRAG", side_effect=construct):
                body = portal.RetrieveRequest(models=settings, documents=[first, second], query="Same")
                portal.retrieve(body)
                chunks = hippo.index.call_args.args[0]
                self.assertEqual(len(chunks), 1)
                self.assertEqual({ref["memory_item_id"] for ref in chunks[0].metadata["source_refs"]}, {"item1", "item2"})
                body.models = models(token="request-two")
                portal.retrieve(body)
                self.assertEqual(hippo.llm_model.models.token.get_secret_value(), "request-two")
                self.assertEqual(hippo.index.call_count, 1)

    def test_reembedding_reuses_passages_and_facts_without_llm_or_split(self):
        first = models().model_copy(update={"embedding_identity": "b" * 64, "extraction_identity": "c" * 64})
        body = portal.ExtractRequest(models=first, documents=[portal.Document(id="doc", content="Router requires backup.")])
        key = portal.compute_mdhash_id(body.documents[0].content, prefix="chunk-")
        ner = {key: portal.NerRawOutput(chunk_id=key, response="", unique_entities=["Router", "backup"], metadata={})}
        triples = {key: portal.TripleRawOutput(chunk_id=key, response="", triples=[["Router", "requires", "backup"]], metadata={})}
        def embed(settings, operation, payload):
            self.assertEqual(operation, "embed", "Reindex must never call the LLM")
            return {"vectors": [[1.0] + [0.0] * (settings.dimensions - 1) for text in payload["texts"]]}
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "ENGINES", {}), patch.object(portal, "callback", side_effect=embed):
            with patch.object(portal.PortalOpenIE, "batch_openie", return_value=(ner, triples)):
                original, _ = portal.graph(body)
            snapshot = portal.snapshot_path(body.documents[0]).read_text()
            body.models = first.model_copy(update={"embedding_identity": "d" * 64, "identity": "e" * 64,
                                                  "embedding_alias": "new.encoder", "dimensions": 3})
            with patch("common.split_document", side_effect=AssertionError("must not split")), patch.object(portal.PortalOpenIE, "batch_openie", side_effect=AssertionError("must not extract")):
                rebuilt, _ = portal.graph(body, embedding_only=True)
            self.assertEqual(original._openie_info, rebuilt._openie_info)
            self.assertEqual(portal.snapshot_path(body.documents[0]).read_text(), snapshot)
            self.assertEqual(rebuilt.embedding_model.embedding_dim, 3)
            original.close()
            rebuilt.close()
            portal.ENGINES.clear()
            with patch("common.split_document", side_effect=AssertionError("restart must not split")), patch.object(portal, "callback", side_effect=AssertionError("restart must not call models")):
                restored, _ = portal.graph(body, allow_build=False, embedding_only=True)
            self.assertEqual(restored._openie_info, original._openie_info)
            restored.close()

    def test_search_does_not_build_missing_encoder_index(self):
        body = portal.ExtractRequest(models=models(), documents=[portal.Document(id="doc", content="Source")])
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "ENGINES", {}), patch.object(portal, "HippoRAG") as constructor:
            with self.assertRaises(portal.HTTPException) as error:
                portal.graph(body, allow_build=False)
            self.assertEqual(error.exception.status_code, 409)
            constructor.assert_not_called()

    def test_embedding_only_missing_snapshot_cannot_call_llm(self):
        body = portal.ExtractRequest(models=models(), documents=[portal.Document(id="doc", content="Source")])
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "ENGINES", {}), patch.object(portal, "callback") as callback:
            with self.assertRaisesRegex(ValueError, "Saved extraction is missing"):
                portal.graph(body, embedding_only=True)
            callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
