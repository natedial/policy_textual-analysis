from __future__ import annotations

import os
from typing import Iterable, List, Optional, Sequence

import pandas as pd

from db import Database
from fed_tracker.pipeline import AnalysisBundle, AnalysisPipeline


def build_pipeline() -> AnalysisPipeline:
    database = None
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
        try:
            database = Database()
        except Exception:
            database = None
    return AnalysisPipeline(database=database)


def analyze_url(url: str, historical_bundles: Optional[Sequence[AnalysisBundle]] = None) -> AnalysisBundle:
    pipeline = build_pipeline()
    historical_documents = [bundle.document for bundle in historical_bundles or []]
    return pipeline.analyze_url(url, historical_documents=historical_documents)


def compare_urls(
    base_url: str,
    target_url: str,
    historical_urls: Optional[Iterable[str]] = None,
):
    pipeline = build_pipeline()
    historical_bundles: List[AnalysisBundle] = []
    for url in historical_urls or []:
        if url.strip():
            historical_bundles.append(pipeline.analyze_url(url.strip()))

    base_bundle = pipeline.analyze_url(base_url, historical_documents=[bundle.document for bundle in historical_bundles])
    target_bundle = pipeline.analyze_url(
        target_url,
        historical_documents=[base_bundle.document, *[bundle.document for bundle in historical_bundles]],
    )
    comparison = pipeline.compare_bundles(
        base_bundle=base_bundle,
        target_bundle=target_bundle,
        context_bundles=[base_bundle, *historical_bundles],
    )
    return base_bundle, target_bundle, comparison


def extractor_label() -> str:
    return "Anthropic" if os.getenv("ANTHROPIC_API_KEY") else "Heuristic"


def persistence_enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))


def fingerprint_to_dataframe(bundle: AnalysisBundle) -> pd.DataFrame:
    rows = []
    for theme, assessment in bundle.fingerprint.themes.items():
        rows.append(
            {
                "Theme": theme,
                "Stance": assessment.stance,
                "Trajectory": assessment.trajectory,
                "Emphasis": assessment.emphasis_score,
                "Hedging": assessment.hedging_level,
                "Confidence": assessment.confidence,
                "Uncertainty": assessment.uncertainty,
                "Evidence": " | ".join(item.quote for item in assessment.evidence[:2]),
            }
        )
    return pd.DataFrame(rows)


def theme_changes_to_dataframe(comparison) -> pd.DataFrame:
    rows = []
    for change in comparison.theme_changes:
        rows.append(
            {
                "Theme": change.theme,
                "Change Type": change.change_type,
                "Strength": change.strength,
                "Uncertainty": change.uncertainty,
                "Summary": change.summary,
            }
        )
    return pd.DataFrame(rows)


def phrase_signals_to_dataframe(bundle: AnalysisBundle) -> pd.DataFrame:
    rows = []
    for signal in bundle.fingerprint.phrase_signals:
        rows.append(
            {
                "Phrase": signal.phrase_text,
                "Normalized": signal.normalized_phrase,
                "Rarity": signal.rarity_score,
                "Current Count": signal.current_count,
                "Historical Count": signal.historical_count,
                "Semantic Key": signal.semantic_key,
            }
        )
    return pd.DataFrame(rows)
