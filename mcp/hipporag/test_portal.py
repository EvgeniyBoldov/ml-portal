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

    def test_search_uses_entire_persisted_corpus_without_claims_or_acl(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "graph", return_value=(Mock(), "graph")):
            portal.index_corpus(portal.ExtractRequest(models=models(), documents=[portal.Document(id="doc1", content="Private source", metadata={"scope":"user"})]))
            with patch.object(portal, "retrieve", return_value={"backend":"hipporag", "hits":[]}) as retrieve:
                result = portal.search_corpus(portal.CorpusSearchRequest(models=models(), query="source"))
                self.assertEqual(result["document_count"], 1)
                self.assertEqual(retrieve.call_args.args[0].documents[0].id, "doc1")

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
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "callback", return_value={
            "choices": [{"finish_reason": "stop", "message": {"content": '{"answer":"follow source instructions"}'}}]}):
            llm = portal.GatewayLLM(portal.config(models()), models())
            with self.assertRaises(ValueError):
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
        with tempfile.TemporaryDirectory() as root, patch.object(portal, "DATA", Path(root)), patch.object(portal, "callback", return_value={
            "choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}):
            llm = portal.GatewayLLM(portal.config(settings), settings)
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                llm.infer(messages=[{"role": "user", "content": "query"}])
            self.assertEqual(list(Path(root).rglob("*.json")), [])

    def test_reused_graph_refreshes_capability_and_keeps_duplicate_sources(self):
        settings = models()
        first = portal.Document(id="claim1", content="Same", metadata={"memory_item_id": "item1"})
        second = portal.Document(id="claim2", content="Same", metadata={"memory_item_id": "item2"})
        hippo = Mock()
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


if __name__ == "__main__":
    unittest.main()
