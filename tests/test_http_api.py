import json
import unittest

from fed_tracker.http_api import dispatch_request


class FakeService:
    def __init__(self):
        self.query = self

    def speaker_brief(self, speaker_name, theme=None):
        return {"speaker_name": speaker_name, "theme": theme}

    def speaker_timeline(self, speaker_name, limit=10):
        return {"speaker_name": speaker_name, "limit": limit}

    def recent_comparisons(self, speaker_name, comparison_type=None, limit=10):
        return {"speaker_name": speaker_name, "comparison_type": comparison_type, "limit": limit}

    def orphaned_concepts(self, speaker_name, window_days=75, min_emphasis=3):
        return {"speaker_name": speaker_name, "window_days": window_days, "min_emphasis": min_emphasis}

    def theme_drift(self, speaker_name, theme=None, window_days=730, limit=20):
        return {"speaker_name": speaker_name, "theme": theme, "window_days": window_days, "limit": limit}

    def answer_question(self, speaker_name, question):
        return {"speaker_name": speaker_name, "question": question}

    def ingest_url(self, url):
        return {"url": url, "skipped": False}

    def ingest_url_if_new(self, url):
        return {"url": url, "skipped": True}

    def ingest_urls(self, urls, skip_existing=True):
        return {"count": len(urls), "skip_existing": skip_existing}

    def ingest_markdown(self, markdown_text, metadata=None):
        return {"markdown_text": markdown_text, "metadata": metadata or {}}


class HttpApiTests(unittest.TestCase):
    def test_health_endpoint(self):
        status, payload = dispatch_request(FakeService(), "GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["transport"], "http")
        self.assertEqual(payload["operation"], "health")
        self.assertTrue(payload["data"]["ok"])

    def test_openapi_endpoint(self):
        status, payload = dispatch_request(FakeService(), "GET", "/openapi.json")
        self.assertEqual(status, 200)
        self.assertEqual(payload["openapi"], "3.1.0")
        self.assertIn("/speaker/brief", payload["paths"])

    def test_brief_endpoint(self):
        status, payload = dispatch_request(FakeService(), "GET", "/speaker/brief?speaker_name=Jerome%20Powell&theme=INFLATION")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "speaker_brief")
        self.assertEqual(payload["data"]["theme"], "INFLATION")

    def test_question_endpoint(self):
        body = json.dumps({"speaker_name": "Jerome Powell", "question": "What changed?"}).encode("utf-8")
        status, payload = dispatch_request(FakeService(), "POST", "/speaker/question", body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["question"], "What changed?")

    def test_ingest_urls_endpoint(self):
        body = json.dumps({"urls": ["https://a.example", "https://b.example"], "skip_existing": False}).encode("utf-8")
        status, payload = dispatch_request(FakeService(), "POST", "/ingest/urls", body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["count"], 2)
        self.assertFalse(payload["data"]["skip_existing"])

    def test_error_envelope(self):
        status, payload = dispatch_request(FakeService(), "GET", "/speaker/brief")
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["message"], "speaker_name is required")


if __name__ == "__main__":
    unittest.main()
