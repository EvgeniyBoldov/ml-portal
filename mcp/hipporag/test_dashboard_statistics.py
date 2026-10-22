"""Compact dashboard projection reads no document text and never invokes a model."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import portal


class DashboardStatisticsTests(unittest.TestCase):
    def test_counts_only_published_documents_and_reads_index_snapshot(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(portal, "DATA", Path(directory)), \
                patch.object(portal.operations, "unavailable_documents", return_value={"pending"}), \
                patch.object(portal, "graph", side_effect=AssertionError("must not load graph")):
            with portal.corpus_connection() as connection:
                for document_id in ("published", "pending"):
                    connection.execute("INSERT INTO documents VALUES (?,?,?)", (
                        document_id, "private source", json.dumps({"scope_slugs": ["company", "company"]})))
                connection.execute("INSERT INTO scope_indexes VALUES (?,?,?)", ("company", "ready-index", "embedding"))
            root = Path(directory) / "portal-indexes" / "ready-index"
            root.mkdir(parents=True)
            (root / "ready").write_text("ready-index")
            (root / "statistics.json").write_text(json.dumps({"nodes": 12, "edges": 20}))
            result = portal.corpus_statistics_route()
            self.assertEqual(len(result["scopes"]), 1)
            scope = result["scopes"][0]
            self.assertEqual((scope["documents"], scope["nodes"], scope["edges"]), (1, 12, 20))
            self.assertEqual(scope["status"], "ready")
            self.assertNotIn("private source", str(result))

    def test_old_index_without_statistics_reports_unknown_size(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(portal, "DATA", Path(directory)), \
                patch.object(portal.operations, "unavailable_documents", return_value=set()):
            with portal.corpus_connection() as connection:
                connection.execute("INSERT INTO scope_indexes VALUES (?,?,?)", ("company", "old-index", "embedding"))
            root = Path(directory) / "portal-indexes" / "old-index"
            root.mkdir(parents=True)
            (root / "ready").write_text("old-index")
            scope = portal.corpus_statistics_route()["scopes"][0]
            self.assertEqual(scope["status"], "ready")
            self.assertIsNone(scope["nodes"])


if __name__ == "__main__":
    unittest.main()
