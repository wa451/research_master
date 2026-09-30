"""Read-only result browsing, provenance and file access boundaries."""
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from support.research_browser import (
    allowed_files, check_catalog, make_handler, parse_tables, read_catalog,
    safe_path, source_payload,
)


class ResearchBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.table = "# Existing table\n\n| model | F1 | missing | zero |\n|---|---|---|---|\n| model-a | 0.123456789 | N/A | 0 |\n| model-b |  | None | 0.0 |\n"
        files = {
            "docs/research/result_catalog.json": json.dumps({
                "checked_on": "2026-10-01", "comparison_root": "results/comparison",
                "items": [{"id": "table", "table": "example", "columns": ["model", "F1"]}],
                "resources": ["results/comparison/manifest.json"],
            }),
            "results/comparison/tables/table_model_comparison_example.md": self.table,
            "results/comparison/tables/table_model_comparison_example.csv": "model,F1\nmodel-a,0.123456789\n",
            "results/comparison/manifest.json": '{"schema_version":1}',
            "results/private/human_evaluation_blind_key_internal.csv": "private-key",
            "docs/overview.md": "# Overview\n",
            "assets/research_browser.html": "<!doctype html><title>Research</title>",
            "README.md": "# README",
            ".env": "private-secret",
        }
        for relative, text in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def test_preserves_precision_missing_cells_zero_and_provenance(self):
        data = read_catalog(self.root)
        payload = source_payload(self.root, data["items"][0]["path"], allowed_files(self.root, data))
        self.assertEqual(payload["tables"][0]["rows"], [
            ["model-a", "0.123456789", "N/A", "0"], ["model-b", "", "None", "0.0"],
        ])
        self.assertEqual(payload["sha256"], hashlib.sha256(self.table.encode()).hexdigest())
        self.assertEqual(check_catalog(self.root, data), [])

    def test_parses_multiple_tables_and_pipes_in_code(self):
        text = "| label | value |\n|:---|---:|\n| `a|b` | escaped\\|pipe |\n\n" + self.table
        tables = parse_tables(text)
        self.assertEqual(len(tables), 2)
        self.assertEqual(tables[0]["rows"], [["`a|b`", "escaped|pipe"]])
        with self.assertRaises(ValueError):
            parse_tables("| a | b |\n|---|---|\n| one |\n")

    def test_missing_results_are_distinct_from_empty_rows(self):
        data = read_catalog(self.root)
        (self.root / data["items"][0]["path"]).unlink()
        issues = check_catalog(self.root, data)
        self.assertEqual(len(issues), 1)
        self.assertIn("missing", issues[0])

    def test_rejects_external_symlinks_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            safe_path(self.root, "../outside.md")
        (self.root / "docs/outside.md").symlink_to(self.root.parent / "outside.md")
        with self.assertRaises(ValueError):
            safe_path(self.root, "docs/outside.md")
        data = json.loads((self.root / "docs/research/result_catalog.json").read_text())
        data["items"].append(data["items"][0].copy())
        (self.root / "docs/research/result_catalog.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            read_catalog(self.root)

    def test_http_allows_only_registered_reads_and_never_modifies_files(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.root))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def request(path, method="GET"):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
                connection.request(method, path)
                response = connection.getresponse()
                status, headers, body = response.status, dict(response.getheaders()), response.read()
                connection.close()
                return status, headers, body

            status, headers, body = request("/api/catalog")
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["items"][0]["available"])
            self.assertEqual(headers["Cache-Control"], "no-store")
            relative = "results/comparison/tables/table_model_comparison_example.md"
            status, _, body = request("/api/source?path=" + quote(relative))
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["text"], self.table)
            for relative in [".env", "../outside.md", "results/private/human_evaluation_blind_key_internal.csv"]:
                self.assertEqual(request("/download/" + quote(relative))[0], 403)
                self.assertEqual(request("/api/source?path=" + quote(relative))[0], 403)
            self.assertEqual(request("/download/results/comparison/manifest.json")[0], 200)
            csv_path = "results/comparison/tables/table_model_comparison_example.csv"
            status, headers, body = request("/download/" + csv_path)
            self.assertEqual(status, 200)
            self.assertEqual(body, before[csv_path])
            self.assertIn("attachment", headers["Content-Disposition"])
            self.assertEqual(request("/api/source", "POST")[0], 501)
            self.assertEqual(request("/", "DELETE")[0], 501)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
