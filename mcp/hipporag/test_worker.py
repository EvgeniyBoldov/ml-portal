"""Boundary checks, runnable inside the worker image using standard unittest."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import server


class WorkerTests(unittest.TestCase):
    def test_embeddings_are_batched_and_keep_order(self):
        calls = []

        def http(url, payload=None):
            if payload is None:
                return {'dimensions': 2}
            calls.append(payload['texts'])
            return {'vectors': [[int(t) + 1, 1] for t in payload['texts']]}

        with patch.object(server, 'request', side_effect=http):
            embedding = server.PortalEmbedding(server.BaseConfig())
            vectors = embedding.batch_encode([str(i) for i in range(35)])
        self.assertEqual([len(c) for c in calls], [16, 16, 3])
        self.assertEqual(vectors.shape, (35, 2))
        self.assertTrue(server.np.allclose(vectors[:, 0] / vectors[:, 1], server.np.arange(1, 36)))

    def test_unicode_adapter_only_changes_entity_serialization(self):
        openie = server.StrictOpenIE(Mock(global_config=server.BaseConfig()), max_workers=1)
        passage = 'Владелец сервиса. Literal code: \\u0410'
        messages = openie.prompt_template_manager.render(name='triple_extraction', passage=passage,
                                                        named_entity_json=json.dumps({'named_entities': ['Владелец сервиса']}))
        self.assertIn('"Владелец сервиса"', messages[-1]['content'])
        self.assertIn(passage, messages[-1]['content'])
        self.assertIn('not all possible pairs', messages[0]['content'])

    def test_chunks_preserve_every_character_and_offsets(self):
        text = '# Заголовок\n```sh\n# комментарий, не раздел\n' + 'Связь и условие.\n' * 80 + '```\n'
        doc = server.Document(id='doc', content=text)
        with patch.object(server, 'CHUNK_TOKENS', 100):
            chunks = server.split_document(doc, Mock(tokens=len))
        self.assertEqual(''.join(c.content for c in chunks), text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.content), 100)
            self.assertEqual(text[chunk.metadata['start']:chunk.metadata['end']], chunk.content)

    def test_complete_prompt_is_checked_before_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            llm = server.LocalLLM(server.BaseConfig(), Path(temp))
            with patch.object(server, 'DATA', Path(temp)), patch.object(server, 'request', return_value={'prompt': 'long template'}) as http, patch.object(llm, 'tokens', return_value=server.BUDGET):
                with self.assertRaisesRegex(ValueError, 'exceeds request budget'):
                    llm.infer(messages=[{'role': 'user', 'content': 'tiny input'}])
                self.assertEqual(http.call_count, 1)
                self.assertEqual(len(llm.errors), 1)

    def test_truncated_output_is_not_cached(self):
        with tempfile.TemporaryDirectory() as temp:
            llm = server.LocalLLM(server.BaseConfig(), Path(temp))
            results = [{'prompt': 'short'}, {'choices': [{'finish_reason': 'length', 'message': {'content': 'partial'}}]}]
            with patch.object(server, 'DATA', Path(temp)), patch.object(server, 'request', side_effect=results), patch.object(llm, 'tokens', return_value=20):
                with self.assertRaisesRegex(ValueError, 'Incomplete'):
                    llm.infer(messages=[{'role': 'user', 'content': 'test'}], max_new_tokens=server.OUTPUT_TOKENS)
            self.assertEqual(list((Path(temp) / 'llm-cache').rglob('*.json')), [])

    def test_length_retry_is_bounded_and_only_complete_result_cached(self):
        with tempfile.TemporaryDirectory() as temp:
            llm = server.LocalLLM(server.BaseConfig(), Path(temp))
            responses = [{'prompt': 'short'},
                         {'choices': [{'finish_reason': 'length', 'message': {'content': 'partial'}}]},
                         {'choices': [{'finish_reason': 'stop', 'message': {'content': 'complete'}}], 'usage': {'completion_tokens': 140}}]
            with patch.object(server, 'DATA', Path(temp)), patch.object(server, 'request', side_effect=responses) as http, patch.object(llm, 'tokens', return_value=20):
                text, metadata, cached = llm.infer(messages=[{'role': 'user', 'content': 'retry'}], max_new_tokens=128)
                self.assertEqual(text, 'complete')
                self.assertEqual(metadata['final_output_limit'], 256)
                self.assertFalse(cached)
                self.assertEqual(llm.errors, [])
                self.assertEqual(http.call_count, 3)
            self.assertEqual(len(list((Path(temp) / 'llm-cache').rglob('*.json'))), 1)

    def test_job_restart_and_http_boundaries(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(server, 'DATA', Path(temp)), patch.object(server, 'POOL', Mock()), patch.object(server, 'ENGINES', {}), patch.object(server, 'CLIENT', Mock()):
            with TestClient(server.app) as client:
                body = {'index': 'test', 'documents': [{'id': 'one', 'content': 'text'}]}
                accepted = client.post('/indexes', json=body)
                self.assertEqual(accepted.status_code, 202)
                job_id = accepted.json()['job_id']
                self.assertEqual(client.post('/indexes', json=body).status_code, 409)
                self.assertEqual(client.post('/indexes', json={**body, 'index': '../escape'}).status_code, 422)
                self.assertEqual(client.post('/search', json={'index': 'test', 'query': 'x'}).status_code, 409)
                init = client.post('/mcp', json={'id': 1, 'method': 'initialize'})
                headers = {'mcp-session-id': init.headers['mcp-session-id']}
                tools = client.post('/mcp', json={'id': 2, 'method': 'tools/list'}, headers=headers).json()['result']['tools']
                self.assertEqual(len(tools), 4)
                self.assertEqual(tools[0]['inputSchema'], server.IndexRequest.model_json_schema())
                failed = client.post('/mcp', json={'id': 3, 'method': 'tools/call', 'params': {'name': 'hipporag_search', 'arguments': {'index': 'test', 'query': 'x'}}}, headers=headers).json()
                self.assertTrue(failed['result']['isError'])
                self.assertEqual(client.post('/mcp', json={'id': 4, 'method': 'tools/list'}).json()['error']['code'], -32002)
            with TestClient(server.app) as client:
                restored = client.get('/jobs/' + job_id).json()
                self.assertEqual(restored['status'], 'failed')
                self.assertIn('restarted', restored['error'])
                root = Path(temp) / 'indexes' / 'test'
                root.mkdir(parents=True)
                (root / 'input.json').write_text(json.dumps(body))
                changed = {**body, 'retry': True, 'documents': [{'id': 'one', 'content': 'changed'}]}
                self.assertEqual(client.post('/indexes', json=changed).status_code, 409)
                retried = client.post('/indexes', json={**body, 'retry': True})
                self.assertEqual(retried.status_code, 202)
                self.assertEqual(retried.json()['job_id'], job_id)


if __name__ == '__main__':
    unittest.main()
