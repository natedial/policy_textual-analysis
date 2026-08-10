"""Fed textual change tracker package.

All public exports are lazy so ``db`` can import ``fed_tracker.models``
without pulling agent/query modules that import ``db``.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AnalysisPipeline",
    "AnthropicFingerprintExtractor",
    "HeuristicFingerprintExtractor",
    "AnalysisBundle",
    "StoredAnalysisResult",
    "QueryService",
    "FedTextAgentService",
    "API_VERSION",
    "cli_envelope",
    "success_envelope",
    "error_envelope",
    "get_openapi_schema",
    "dispatch_request",
    "run_server",
    "NormalizedDocument",
    "SemanticFingerprint",
    "ComparisonResult",
    "normalize_url",
    "normalize_markdown",
    "compare_fingerprints",
    "summarize_window",
]

_LAZY_ATTRS = {
    "AnalysisPipeline": ("fed_tracker.pipeline", "AnalysisPipeline"),
    "AnalysisBundle": ("fed_tracker.pipeline", "AnalysisBundle"),
    "StoredAnalysisResult": ("fed_tracker.pipeline", "StoredAnalysisResult"),
    "AnthropicFingerprintExtractor": ("fed_tracker.extraction", "AnthropicFingerprintExtractor"),
    "HeuristicFingerprintExtractor": ("fed_tracker.extraction", "HeuristicFingerprintExtractor"),
    "QueryService": ("fed_tracker.query", "QueryService"),
    "FedTextAgentService": ("fed_tracker.agent_service", "FedTextAgentService"),
    "API_VERSION": ("fed_tracker.contract", "API_VERSION"),
    "cli_envelope": ("fed_tracker.contract", "cli_envelope"),
    "success_envelope": ("fed_tracker.contract", "success_envelope"),
    "error_envelope": ("fed_tracker.contract", "error_envelope"),
    "get_openapi_schema": ("fed_tracker.contract", "get_openapi_schema"),
    "dispatch_request": ("fed_tracker.http_api", "dispatch_request"),
    "run_server": ("fed_tracker.http_api", "run_server"),
    "NormalizedDocument": ("fed_tracker.models", "NormalizedDocument"),
    "SemanticFingerprint": ("fed_tracker.models", "SemanticFingerprint"),
    "ComparisonResult": ("fed_tracker.models", "ComparisonResult"),
    "normalize_url": ("fed_tracker.normalization", "normalize_url"),
    "normalize_markdown": ("fed_tracker.normalization", "normalize_markdown"),
    "compare_fingerprints": ("fed_tracker.comparison", "compare_fingerprints"),
    "summarize_window": ("fed_tracker.comparison", "summarize_window"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    from importlib import import_module

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
