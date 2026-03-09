# API Contract

## Version

The local orchestrator-facing contract is versioned as `v1`.

All CLI outputs are emitted as a versioned envelope:

```json
{
  "api_version": "v1",
  "ok": true,
  "transport": "cli",
  "operation": "ingest",
  "status_code": 200,
  "data": {"...": "..."}
}
```

All HTTP responses except `/openapi.json` are emitted as the same versioned envelope with `transport: "http"`.

Error responses use:

```json
{
  "api_version": "v1",
  "ok": false,
  "transport": "http",
  "operation": "speaker_brief",
  "status_code": 400,
  "error": {
    "message": "speaker_name is required"
  }
}
```

## HTTP Schema

Machine-readable schema:
- [openapi.json](/Users/ndial/dev/textual_change_tracker/docs/openapi.json)
- runtime endpoint: `GET /openapi.json`

## Supported HTTP Operations

- `GET /health`
- `GET /openapi.json`
- `GET /speaker/brief`
- `GET /speaker/timeline`
- `GET /speaker/comparisons`
- `GET /speaker/orphaned`
- `GET /speaker/drift`
- `POST /speaker/question`
- `POST /ingest/url`
- `POST /ingest/urls`
- `POST /ingest/markdown`

## CLI Commands

- [ingest.py](/Users/ndial/dev/textual_change_tracker/ingest.py)
- [schedule_ingest.py](/Users/ndial/dev/textual_change_tracker/schedule_ingest.py)
- [query_artifacts.py](/Users/ndial/dev/textual_change_tracker/query_artifacts.py)

## Integration Guidance

Preferred order for orchestrator agents:

1. HTTP API over `127.0.0.1`
2. Direct Python import via `FedTextAgentService`
3. CLI as a fallback for cron/manual workflows

`/openapi.json` is the canonical machine-readable entrypoint for the HTTP contract.
