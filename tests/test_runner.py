import json
import tempfile
import unittest
from pathlib import Path

from fed_tracker.runner import load_manifest, load_urls_file, run_manifest, run_url_batch


class FakeService:
    def ingest_urls(self, urls, skip_existing=True):
        return {
            "count": len(list(urls)),
            "ingested": 1,
            "skipped": 1 if skip_existing else 0,
            "results": [{"url": "https://example.com", "skipped": False}],
        }

    def ingest_markdown_file(self, path, metadata=None):
        return {
            "path": path,
            "metadata": metadata or {},
            "persisted": None,
        }


class RunnerTests(unittest.TestCase):
    def test_load_urls_file_ignores_comments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "urls.txt"
            path.write_text("# comment\nhttps://a.example\n\nhttps://b.example\n")
            urls = load_urls_file(str(path))
        self.assertEqual(urls, ["https://a.example", "https://b.example"])

    def test_run_manifest_handles_urls_and_markdown(self):
        service = FakeService()
        with tempfile.TemporaryDirectory() as tmpdir:
            markdown_path = Path(tmpdir) / "speech.md"
            markdown_path.write_text("hello")
            manifest = {
                "urls": ["https://a.example"],
                "markdown_files": [
                    {"path": str(markdown_path), "metadata": {"speaker_name": "Test Speaker"}}
                ],
            }
            payload = run_manifest(service, manifest)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["results"][0]["type"], "urls")
        self.assertEqual(payload["results"][1]["type"], "markdown_file")

    def test_load_manifest_reads_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps({"urls": ["https://a.example"]}))
            manifest = load_manifest(str(path))
        self.assertEqual(manifest["urls"], ["https://a.example"])


if __name__ == "__main__":
    unittest.main()
