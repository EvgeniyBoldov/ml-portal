"""Model failures must be retried locally without publishing partial knowledge."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import httpx
import portal
import document_operations as operations
from test_portal import models


def response(content='{"named_entities":["Router"]}', finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": content}}]}


class LLMResilienceTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        for module in (portal, operations):
            patcher = patch.object(module, "DATA", self.root)
            patcher.start()
            self.addCleanup(patcher.stop)

    def infer(self):
        llm = portal.GatewayLLM(portal.config(models()), models())
        return llm.infer(messages=[{"role": "user", "content": "Source"}],
                         _schema_model=portal.NamedEntitiesOutput)

    def test_rate_limit_then_success_respects_retry_after_and_caches_success(self):
        error = httpx.HTTPStatusError("rate limit", request=httpx.Request("POST", "http://api/chat"),
            response=httpx.Response(429, headers={"Retry-After": "3"}))
        with patch.object(portal, "callback", side_effect=[error, response()]) as call, patch("time.sleep") as sleep:
            text, metadata, cached = self.infer()
            self.assertEqual(json.loads(text)["named_entities"], ["Router"])
            self.assertEqual(metadata["attempts"], 2)
            self.assertFalse(cached)
            sleep.assert_called_once_with(3.0)
            self.assertTrue(self.infer()[2])
            self.assertEqual(call.call_count, 2)

    def test_invalid_json_is_retried_and_only_valid_result_is_cached(self):
        with patch.object(portal, "callback", side_effect=[response("invalid"), response()]) as call, patch("time.sleep"):
            self.infer()
            self.assertEqual(call.call_count, 2)
        saved = next(self.root.rglob("*.json"))
        self.assertEqual(json.loads(saved.read_text())["text"], response()["choices"][0]["message"]["content"])

    def test_timeout_exhaustion_is_bounded_and_does_not_cache_failure(self):
        with patch.object(portal, "callback", side_effect=httpx.ReadTimeout("timeout")) as call, patch("time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "timeout") as error:
                self.infer()
            self.assertTrue(error.exception.retryable)
            self.assertEqual(call.call_count, portal.LLM_MAX_ATTEMPTS)
        self.assertEqual(list(self.root.rglob("*.json")), [])

    def test_authentication_error_is_not_retried(self):
        error = httpx.HTTPStatusError("unauthorized", request=httpx.Request("POST", "http://api/chat"),
            response=httpx.Response(401))
        with patch.object(portal, "callback", side_effect=error) as call, patch("time.sleep") as sleep:
            with self.assertRaises(RuntimeError) as failure:
                self.infer()
            self.assertFalse(failure.exception.retryable)
            call.assert_called_once()
            sleep.assert_not_called()

    def test_truncation_grows_output_within_context_and_bounded_attempts(self):
        with patch.object(portal, "callback", side_effect=[response("partial", "length"), response()]) as call, patch("time.sleep"):
            self.infer()
            self.assertGreater(call.call_args_list[1].args[2]["max_tokens"],
                               call.call_args_list[0].args[2]["max_tokens"])

    def test_refusal_is_permanent_and_cannot_become_empty_success(self):
        with patch.object(portal, "callback", return_value=response("", "content_filter")) as call, patch("time.sleep"):
            with self.assertRaises(RuntimeError) as failure:
                self.infer()
            self.assertFalse(failure.exception.retryable)
            call.assert_called_once()

    def test_long_provider_cooldown_is_deferred_without_premature_local_retry(self):
        error = httpx.HTTPStatusError("rate limit", request=httpx.Request("POST", "http://api/chat"),
            response=httpx.Response(429, headers={"Retry-After": "120"}))
        with patch.object(portal, "callback", side_effect=error) as call, patch("time.sleep") as sleep:
            with self.assertRaises(portal.ModelRequestError) as failure:
                self.infer()
            self.assertEqual(failure.exception.retry_after_seconds, 120)
            self.assertTrue(failure.exception.retryable)
            call.assert_called_once()
            sleep.assert_not_called()

    def test_failed_document_resumes_from_cached_successful_stage_calls(self):
        document = portal.Document(id="doc", content="A" * portal.CHUNK_TOKENS + "B" * 100)
        body = portal.DocumentCommand(operation_id="operation", document_id="doc", generation=1,
                                      document=document, models=models())
        operations.admit("operation", "doc", 1, "add")
        success = response('{"triples":[["Router","requires","backup"]]}')
        results = [response(), success, response()] + [httpx.ReadTimeout("timeout")] * portal.LLM_MAX_ATTEMPTS
        with patch.object(portal, "callback", side_effect=results), patch("time.sleep"), patch.object(portal, "graph") as graph:
            portal.execute_document_command(body, "add")
        record = operations.get("operation")
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["retryable"])
        self.assertIn("Triple extraction", record["error"])
        self.assertIn("timeout", record["error"])
        self.assertFalse(portal.snapshot_path(document).exists())
        graph.assert_not_called()
        operations.admit("operation", "doc", 1, "add")
        engine = Mock()
        engine.graph.vcount.return_value = 3
        engine.graph.ecount.return_value = 2
        with patch.object(portal, "callback", return_value=success) as call, patch.object(portal, "graph", return_value=(engine, "index")):
            portal.execute_document_command(body, "add")
        self.assertEqual(operations.get("operation")["status"], "completed")
        call.assert_called_once()  # Only the previously failed triple request.
        self.assertTrue(portal.snapshot_path(document).exists())

    def test_chunk_failure_preserves_cause_and_retryability_in_operation(self):
        document = portal.Document(id="doc", content="Source")
        body = portal.DocumentCommand(operation_id="operation", document_id="doc", generation=1,
                                      document=document, models=models())
        operations.admit("operation", "doc", 1, "add")
        key = portal.compute_mdhash_id("Source", prefix="chunk-")
        error_response = httpx.Response(400, json={"detail": {"code": "llm_structured_output_unsupported",
            "message": "LLM does not support structured output", "retryable": False}},
            request=httpx.Request("POST", "http://api/chat"))
        with patch.object(portal.CLIENT, "post", return_value=error_response), patch.object(portal, "graph") as graph:
            portal.execute_document_command(body, "add")
        record = operations.get("operation")
        self.assertEqual(record["status"], "failed")
        self.assertFalse(record["retryable"])
        self.assertEqual(record["error_code"], "llm_structured_output_unsupported")
        self.assertIn("NER", record["error"])
        self.assertIn(key, record["error"])
        self.assertIn("structured output", record["error"])
        self.assertFalse(portal.snapshot_path(document).exists())
        graph.assert_not_called()


if __name__ == "__main__":
    unittest.main()
