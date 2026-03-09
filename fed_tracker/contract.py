from __future__ import annotations

from typing import Any, Dict, Optional

API_VERSION = "v1"


def success_envelope(
    *,
    data: Any,
    operation: str,
    transport: str,
    status_code: int = 200,
) -> Dict[str, Any]:
    return {
        "api_version": API_VERSION,
        "ok": True,
        "transport": transport,
        "operation": operation,
        "status_code": status_code,
        "data": data,
    }


def error_envelope(
    *,
    message: str,
    operation: str,
    transport: str,
    status_code: int,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "api_version": API_VERSION,
        "ok": False,
        "transport": transport,
        "operation": operation,
        "status_code": status_code,
        "error": {
            "message": message,
        },
    }
    if detail:
        payload["error"]["detail"] = detail
    return payload


def cli_envelope(*, command: str, data: Any) -> Dict[str, Any]:
    return success_envelope(data=data, operation=command, transport="cli")


def get_openapi_schema() -> Dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Fed Textual Change Tracker Local API",
            "version": API_VERSION,
            "description": "Local-only HTTP API for ingesting and querying Fed textual analysis artifacts.",
        },
        "servers": [
            {"url": "http://127.0.0.1:8000", "description": "Localhost"},
        ],
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health check",
                    "operationId": "health",
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "Machine-readable API schema",
                    "operationId": "openapiJson",
                }
            },
            "/speaker/brief": {
                "get": {
                    "summary": "Get a composed speaker brief",
                    "operationId": "speakerBrief",
                    "parameters": [
                        {"name": "speaker_name", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "theme", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                }
            },
            "/speaker/timeline": {
                "get": {
                    "summary": "Get a speaker timeline",
                    "operationId": "speakerTimeline",
                    "parameters": [
                        {"name": "speaker_name", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 10}},
                    ],
                }
            },
            "/speaker/comparisons": {
                "get": {
                    "summary": "Get recent comparison artifacts",
                    "operationId": "speakerComparisons",
                    "parameters": [
                        {"name": "speaker_name", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "comparison_type", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 10}},
                    ],
                }
            },
            "/speaker/orphaned": {
                "get": {
                    "summary": "Get orphaned concepts in a trailing window",
                    "operationId": "speakerOrphaned",
                    "parameters": [
                        {"name": "speaker_name", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "window_days", "in": "query", "required": False, "schema": {"type": "integer", "default": 75}},
                        {"name": "min_emphasis", "in": "query", "required": False, "schema": {"type": "integer", "default": 3}},
                    ],
                }
            },
            "/speaker/drift": {
                "get": {
                    "summary": "Get theme drift over time",
                    "operationId": "speakerDrift",
                    "parameters": [
                        {"name": "speaker_name", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "theme", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "window_days", "in": "query", "required": False, "schema": {"type": "integer", "default": 730}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 20}},
                    ],
                }
            },
            "/speaker/question": {
                "post": {
                    "summary": "Answer a speaker-focused question using stored artifacts",
                    "operationId": "speakerQuestion",
                }
            },
            "/ingest/url": {
                "post": {
                    "summary": "Ingest a single URL",
                    "operationId": "ingestUrl",
                }
            },
            "/ingest/urls": {
                "post": {
                    "summary": "Ingest multiple URLs",
                    "operationId": "ingestUrls",
                }
            },
            "/ingest/markdown": {
                "post": {
                    "summary": "Ingest markdown input",
                    "operationId": "ingestMarkdown",
                }
            },
        },
    }
