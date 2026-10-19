"""Document lifecycle regression checks; use only temporary worker data."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import document_operations as operations
import portal
from test_portal import models


class DocumentOperationsTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        for module in (portal, operations):
            patcher = patch.object(module, 'DATA', Path(self.root.name))
            patcher.start()
            self.addCleanup(patcher.stop)
        ready = Path(self.root.name) / "portal-indexes" / "generation" / "ready"
        ready.parent.mkdir(parents=True)
        ready.write_text("generation")
        self.engine = Mock()
        self.engine.graph.vcount.return_value = 3
        self.engine.graph.ecount.return_value = 2
        patcher = patch.object(portal, 'graph', return_value=(self.engine, 'generation'))
        self.graph = patcher.start()
        self.addCleanup(patcher.stop)

    def command(self, operation_id, document_id, generation, document=None):
        return portal.DocumentCommand(operation_id=operation_id, document_id=document_id, generation=generation,
            models=models(), document=document)

    def execute(self, body, action):
        operations.admit(body.operation_id, body.document_id, body.generation, action)
        portal.execute_document_command(body, action)
        return operations.get(body.operation_id)

    def test_delete_preserves_shared_passage_in_other_document(self):
        docs = [portal.Document(id='first', content='Shared text'), portal.Document(id='second', content='Shared text')]
        portal.index_corpus(portal.ExtractRequest(models=models(), documents=docs))
        record = self.execute(self.command('remove-first', 'first', 1), 'delete')
        self.assertEqual(record['status'], 'completed')
        self.assertEqual(record['steps']['index']['status'], 'completed')
        with portal.corpus_connection() as db:
            self.assertEqual([doc.id for doc in portal.corpus_documents(db)], ['second'])
        selected = self.graph.call_args.args[0].documents
        self.assertEqual([doc.id for doc in selected], ['second'])
        self.assertTrue(self.graph.call_args.kwargs['embedding_only'])
        self.assertEqual(portal.document_info_route('first')['availability'], 'absent')

    def test_old_add_cannot_resurrect_after_delete_admission(self):
        add = self.command('old-add', 'doc', 1, portal.Document(id='doc', content='Source'))
        operations.admit('old-add', 'doc', 1, 'add')
        operations.admit('new-delete', 'doc', 2, 'delete')
        portal.execute_document_command(add, 'add')
        self.assertEqual(operations.get('old-add')['status'], 'cancelled')
        with portal.corpus_connection() as db:
            self.assertEqual(portal.corpus_documents(db), [])
        self.graph.assert_not_called()

    def test_failed_index_is_observable_and_does_not_publish_document(self):
        document = portal.Document(id='doc', content='Source')
        body = self.command('add-doc', 'doc', 1, document)
        with patch.object(portal, 'extract_document', return_value={'facts': 1}), patch.object(portal, 'graph', side_effect=ValueError('Broken graph')):
            record = self.execute(body, 'add')
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['steps']['index']['status'], 'failed')
        self.assertIn('Broken graph', record['error'])
        with portal.corpus_connection() as db:
            self.assertEqual(portal.corpus_documents(db), [])

    def test_extraction_counts_and_reuse_do_not_require_new_llm_calls(self):
        document = portal.Document(id='doc', content='Source')
        key = portal.compute_mdhash_id('Source', prefix='chunk-')
        rows = [{'idx': key, 'passage': 'Source', 'extracted_entities': ['A', 'B', 'Unused'],
                 'extracted_triples': [['A', 'uses', 'B'], ['A', 'uses', 'B']]}]
        portal.save_snapshot(document, [{'content': 'Source', 'source_id': 'doc:0:6',
            'metadata': {'document_id': 'doc', 'start': 0, 'end': 6}}], rows)
        with patch.object(portal, 'PortalOpenIE', side_effect=AssertionError('must reuse extraction')):
            record = self.execute(self.command('add-doc', 'doc', 1, document), 'add')
        self.assertEqual(record['status'], 'completed')
        metrics = record['steps']['extract']['metrics']
        self.assertEqual((metrics['passages'], metrics['entities'], metrics['facts'], metrics['extracted_triples']), (1, 2, 1, 2))
        self.assertTrue(metrics['reused_extraction'])
        self.assertEqual(portal.document_info_route('doc')['availability'], 'ready')
        self.assertEqual(record['steps']['index']['metrics']['scope_edges'], 2)

    def test_missing_published_graph_reports_unknown_without_calling_models(self):
        doc = portal.Document(id='doc', content='Source')
        with patch.object(portal, 'extract_document', return_value={}):
            self.execute(self.command('add-doc', 'doc', 1, doc), 'add')
        (Path(self.root.name) / 'portal-indexes' / 'generation' / 'ready').unlink()
        with patch.object(portal, 'GatewayLLM', side_effect=AssertionError('status must not call models')):
            self.assertEqual(portal.document_info_route('doc')['availability'], 'unknown')

    def test_operation_id_is_idempotent_and_input_conflicts_are_rejected(self):
        _, admitted = operations.admit('id', 'doc', 1, 'add')
        self.assertTrue(admitted)
        _, admitted = operations.admit('id', 'doc', 1, 'add')
        self.assertFalse(admitted)
        with self.assertRaises(ValueError):
            operations.admit('id', 'other', 1, 'add')
        operations.recover_interrupted()
        self.assertEqual(operations.get('id')['status'], 'failed')
        _, admitted = operations.admit('id', 'doc', 1, 'add')
        self.assertTrue(admitted)

    def test_pending_delete_excludes_all_source_refs_for_deleted_document(self):
        portal.index_corpus(portal.ExtractRequest(models=models(), documents=[
            portal.Document(id='first', content='Shared'), portal.Document(id='second', content='Shared')]))
        operations.admit('delete', 'first', 1, 'delete')
        with patch.object(portal, 'retrieve', return_value={'hits': [{'text': 'Shared', 'score': 1,
            'metadata': {'source_refs': [{'document_id': 'first'}, {'document_id': 'second'}]}}]}):
            result = portal.search_corpus(portal.CorpusSearchRequest(models=models(), query='Shared', scope_slug='company'))
        self.assertEqual(result['hits'][0]['metadata']['source_refs'], [{'document_id': 'second'}])
        self.assertEqual(result['document_count'], 1)


class NativeDocumentLifecycleTests(unittest.TestCase):
    def test_native_graph_retains_shared_fact_after_one_document_is_removed(self):
        with tempfile.TemporaryDirectory() as root, patch.object(portal, 'DATA', Path(root)), patch.object(operations, 'DATA', Path(root)), patch.object(portal, 'ENGINES', {}):
            text = 'Router requires backup.'
            key = portal.compute_mdhash_id(text, prefix='chunk-')
            docs = [portal.Document(id=id_, content=text) for id_ in ('first', 'second')]
            row = {'idx': key, 'passage': text, 'extracted_entities': ['Router', 'backup'],
                   'extracted_triples': [['Router', 'requires', 'backup']]}
            for doc in docs:
                portal.save_snapshot(doc, [{'content': text, 'source_id': f'{doc.id}:0:{len(text)}',
                    'metadata': {'document_id': doc.id, 'start': 0, 'end': len(text)}}], [row])
            def embed(settings, operation, payload):
                self.assertEqual(operation, 'embed')
                return {'vectors': [[1.0, 0.0] for _ in payload['texts']]}
            try:
                with patch.object(portal, 'callback', side_effect=embed), patch.object(portal.PortalOpenIE, 'batch_openie', side_effect=AssertionError('no extraction')):
                    for doc in docs:
                        body = portal.DocumentCommand(operation_id='add-' + doc.id, document_id=doc.id, generation=1, models=models(), document=doc)
                        operations.admit(body.operation_id, doc.id, 1, 'add')
                        portal.execute_document_command(body, 'add')
                        self.assertEqual(operations.get(body.operation_id)['status'], 'completed')
                    body = portal.DocumentCommand(operation_id='remove-first', document_id='first', generation=2, models=models())
                    operations.admit(body.operation_id, 'first', 2, 'delete')
                    portal.execute_document_command(body, 'delete')
                    self.assertEqual(operations.get(body.operation_id)['status'], 'completed')
                    engine, _ = portal.graph(portal.ExtractRequest(models=models(), documents=[docs[1]], scope_slug='company'), allow_build=False)
                    self.assertEqual(len(engine.fact_embedding_store.get_all_ids()), 1)
                    self.assertEqual({ref['document_id'] for value in engine.chunk_metadata.values() for ref in value['source_refs']}, {'second'})
            finally:
                for engine in portal.ENGINES.values():
                    engine.close()


if __name__ == '__main__':
    unittest.main()
