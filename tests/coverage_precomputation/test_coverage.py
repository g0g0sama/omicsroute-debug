from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import coverage, main
from engine import catalog
from scripts.precompute_coverage import generate


class CoverageTests(unittest.TestCase):
    def setUp(self):
        coverage.get_startup_coverage.cache_clear()
        catalog._load_yaml_cached.cache_clear()
        catalog._workflow_context_index_cached.cache_clear()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(coverage.get_startup_coverage.cache_clear)
        self.path = Path(self.temp.name) / "coverage.json"

    def test_generator_round_trip_matches_fresh_catalogue(self):
        expected = catalog.get_global_coverage()
        generate(self.path)
        with patch.object(coverage, "COVERAGE_PATH", self.path):
            self.assertEqual(coverage.get_startup_coverage(), expected)

    def test_catalogue_reads_each_yaml_and_builds_index_once(self):
        with patch.object(catalog.yaml, "safe_load", wraps=catalog.yaml.safe_load) as read:
            with patch.object(catalog, "build_workflow_context_index", wraps=catalog.build_workflow_context_index) as index:
                first = catalog.get_global_coverage()
                self.assertEqual(read.call_count, 2)
                self.assertEqual(index.call_count, 1)
                self.assertEqual(catalog.get_global_coverage(), first)
                self.assertEqual(read.call_count, 2)

    def test_file_changes_refresh_yaml_and_context_index(self):
        data_dir = Path(self.temp.name)
        workflows = data_dir / "workflows.yaml"
        goals = data_dir / "analysis_goals.yaml"
        workflows.write_text("w: {context: {sample_type: S, goal: A}}\n")
        goals.write_text("f: {sample_type: S, goals: [{id: a, label: A}]}\n")
        with patch.object(catalog, "DATA_DIR", data_dir):
            self.assertEqual(catalog.get_global_coverage()["supported"], 1)
            old = workflows.stat()
            # Same length, different content: modification time must invalidate it.
            workflows.write_text("w: {context: {sample_type: S, goal: B}}\n")
            os.utime(workflows, ns=(old.st_atime_ns, old.st_mtime_ns + 1_000_000))
            self.assertEqual(catalog.get_global_coverage()["supported"], 0)
            goals.write_text("f: {sample_type: S, goals: [{id: b, label: B}, {id: c, label: C}]}\n")
            result = catalog.get_global_coverage()
            self.assertEqual((result["supported"], result["total"]), (1, 2))

    def test_returned_contexts_do_not_mutate_cached_index(self):
        original = catalog.get_global_coverage()
        changed = catalog.get_global_coverage()
        goal = next(g for f in changed["families"] for g in f["goals"] if g["contexts"])
        goal["contexts"][0]["goal"] = "changed by caller"
        self.assertEqual(catalog.get_global_coverage(), original)

    def test_missing_artifact_calculates_once(self):
        expected = {"supported": 0, "total": 0, "percentage": 0, "families": []}
        with patch.object(coverage, "COVERAGE_PATH", self.path):
            with patch.object(coverage, "get_global_coverage", return_value=expected) as calculate:
                self.assertEqual(coverage.get_startup_coverage(), expected)
                coverage.get_startup_coverage()
                calculate.assert_called_once_with()

    def test_invalid_artifacts_fail_startup(self):
        for content in ("not JSON", "null", "{}", '{"supported": 1, "total": 2, "percentage": 50, "families": "wrong"}'):
            with self.subTest(content=content):
                coverage.get_startup_coverage.cache_clear()
                self.path.write_text(content)
                with patch.object(coverage, "COVERAGE_PATH", self.path):
                    with self.assertRaisesRegex(RuntimeError, "Regenerate"):
                        with TestClient(main.app):
                            pass

    def test_startup_loads_artifact_and_requests_do_not_recalculate(self):
        expected = generate(self.path)
        with patch.object(coverage, "COVERAGE_PATH", self.path):
            with patch.object(coverage, "get_global_coverage", side_effect=AssertionError("runtime calculation")):
                with TestClient(main.app) as client:
                    self.assertEqual(coverage.get_startup_coverage.cache_info().misses, 1)
                    with patch.object(main, "get_global_coverage", side_effect=AssertionError("request calculation")):
                        for _ in range(2):
                            response = client.get("/v1/catalog/coverage")
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.json(), {**expected, "dependency_audit": False})

    def test_audit_does_not_change_static_response(self):
        generate(self.path)
        with patch.object(coverage, "COVERAGE_PATH", self.path):
            before = deepcopy(main.catalog_coverage(False))
            # Dependency calculation itself is covered by existing validators.
            with patch.object(main, "validate_workflow", return_value={"valid": True}) as validate:
                audited = main.catalog_coverage(True)
                self.assertTrue(audited["dependency_audit"])
                self.assertGreater(validate.call_count, 0)
            self.assertEqual(main.catalog_coverage(False), before)
            self.assertNotIn("dependency_status", before["families"][0]["goals"][0])


if __name__ == "__main__":
    unittest.main()
