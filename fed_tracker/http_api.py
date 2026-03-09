from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from fed_tracker.agent_service import FedTextAgentService
from fed_tracker.contract import error_envelope, get_openapi_schema, success_envelope


def _json_response(status: int, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    return status, payload


def dispatch_request(
    service: FedTextAgentService,
    method: str,
    path: str,
    body: bytes | None = None,
) -> tuple[int, Dict[str, Any]]:
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    payload = json.loads(body.decode("utf-8")) if body else {}

    if method == "GET" and parsed.path == "/openapi.json":
        return 200, get_openapi_schema()

    if method == "GET" and parsed.path == "/health":
        return _json_response(200, success_envelope(data={"ok": True}, operation="health", transport="http", status_code=200))

    if method == "GET" and parsed.path == "/speaker/brief":
        speaker_name = query.get("speaker_name", [None])[0]
        if not speaker_name:
            return _json_response(400, error_envelope(message="speaker_name is required", operation="speaker_brief", transport="http", status_code=400))
        theme = query.get("theme", [None])[0]
        return _json_response(200, success_envelope(data=service.speaker_brief(speaker_name, theme=theme), operation="speaker_brief", transport="http", status_code=200))

    if method == "GET" and parsed.path == "/speaker/timeline":
        speaker_name = query.get("speaker_name", [None])[0]
        if not speaker_name:
            return _json_response(400, error_envelope(message="speaker_name is required", operation="speaker_timeline", transport="http", status_code=400))
        limit = int(query.get("limit", [10])[0])
        return _json_response(200, success_envelope(data=service.speaker_timeline(speaker_name, limit=limit), operation="speaker_timeline", transport="http", status_code=200))

    if method == "GET" and parsed.path == "/speaker/comparisons":
        speaker_name = query.get("speaker_name", [None])[0]
        if not speaker_name:
            return _json_response(400, error_envelope(message="speaker_name is required", operation="speaker_comparisons", transport="http", status_code=400))
        comparison_type = query.get("comparison_type", [None])[0]
        limit = int(query.get("limit", [10])[0])
        return _json_response(200, success_envelope(data=service.recent_comparisons(speaker_name, comparison_type=comparison_type, limit=limit), operation="speaker_comparisons", transport="http", status_code=200))

    if method == "GET" and parsed.path == "/speaker/orphaned":
        speaker_name = query.get("speaker_name", [None])[0]
        if not speaker_name:
            return _json_response(400, error_envelope(message="speaker_name is required", operation="speaker_orphaned", transport="http", status_code=400))
        window_days = int(query.get("window_days", [75])[0])
        min_emphasis = int(query.get("min_emphasis", [3])[0])
        return _json_response(200, success_envelope(data=service.query.orphaned_concepts(speaker_name, window_days=window_days, min_emphasis=min_emphasis), operation="speaker_orphaned", transport="http", status_code=200))

    if method == "GET" and parsed.path == "/speaker/drift":
        speaker_name = query.get("speaker_name", [None])[0]
        if not speaker_name:
            return _json_response(400, error_envelope(message="speaker_name is required", operation="speaker_drift", transport="http", status_code=400))
        theme = query.get("theme", [None])[0]
        window_days = int(query.get("window_days", [730])[0])
        limit = int(query.get("limit", [20])[0])
        return _json_response(200, success_envelope(data=service.query.theme_drift(speaker_name, theme=theme, window_days=window_days, limit=limit), operation="speaker_drift", transport="http", status_code=200))

    if method == "POST" and parsed.path == "/speaker/question":
        speaker_name = payload.get("speaker_name")
        question = payload.get("question")
        if not speaker_name or not question:
            return _json_response(400, error_envelope(message="speaker_name and question are required", operation="speaker_question", transport="http", status_code=400))
        return _json_response(200, success_envelope(data=service.answer_question(speaker_name, question), operation="speaker_question", transport="http", status_code=200))

    if method == "POST" and parsed.path == "/ingest/url":
        url = payload.get("url")
        if not url:
            return _json_response(400, error_envelope(message="url is required", operation="ingest_url", transport="http", status_code=400))
        skip_existing = payload.get("skip_existing", False)
        if skip_existing:
            data = service.ingest_url_if_new(url)
        else:
            data = service.ingest_url(url)
        return _json_response(200, success_envelope(data=data, operation="ingest_url", transport="http", status_code=200))

    if method == "POST" and parsed.path == "/ingest/urls":
        urls = payload.get("urls")
        if not urls:
            return _json_response(400, error_envelope(message="urls is required", operation="ingest_urls", transport="http", status_code=400))
        skip_existing = payload.get("skip_existing", True)
        return _json_response(200, success_envelope(data=service.ingest_urls(urls, skip_existing=skip_existing), operation="ingest_urls", transport="http", status_code=200))

    if method == "POST" and parsed.path == "/ingest/markdown":
        markdown_text = payload.get("markdown_text")
        metadata = payload.get("metadata") or {}
        if not markdown_text:
            return _json_response(400, error_envelope(message="markdown_text is required", operation="ingest_markdown", transport="http", status_code=400))
        return _json_response(200, success_envelope(data=service.ingest_markdown(markdown_text, metadata=metadata), operation="ingest_markdown", transport="http", status_code=200))

    return _json_response(404, error_envelope(message="not found", operation="unknown", transport="http", status_code=404))


def create_handler(service: FedTextAgentService):
    class AgentAPIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._handle()

        def do_POST(self) -> None:  # noqa: N802
            self._handle()

        def _handle(self) -> None:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b""
            try:
                status, payload = dispatch_request(service, self.command, self.path, body)
            except Exception as exc:  # pragma: no cover - defensive server boundary
                status, payload = 500, error_envelope(message=type(exc).__name__, detail=str(exc), operation="internal_error", transport="http", status_code=500)
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    return AgentAPIHandler


def run_server(host: str = "127.0.0.1", port: int = 8000, service: Optional[FedTextAgentService] = None) -> None:
    service = service or FedTextAgentService()
    server = ThreadingHTTPServer((host, port), create_handler(service))
    try:
        server.serve_forever()
    finally:  # pragma: no cover
        server.server_close()
