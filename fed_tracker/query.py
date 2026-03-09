from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from db import Database
from fed_tracker.storage import comparison_from_record, document_from_record, fingerprint_from_record

THEME_HINTS = {
    "INFLATION": ["inflation", "price", "prices", "disinflation", "pce", "cpi"],
    "LABOR_MARKETS": ["labor", "labour", "jobs", "employment", "wages", "unemployment"],
    "GROWTH_OUTLOOK": ["growth", "gdp", "recession", "activity", "demand"],
    "POLICY_STANCE": ["policy", "rates", "restrictive", "tightening", "easing", "cuts", "hikes"],
    "FINANCIAL_CONDITIONS": ["financial conditions", "credit", "lending", "yields"],
    "HOUSING": ["housing", "shelter", "rent", "real estate"],
}


class QueryService:
    def __init__(self, database: Optional[Database] = None):
        self.database = database or Database()

    def _speaker_documents_with_fingerprints(
        self,
        speaker_name: str,
        limit: int = 100,
        within_days: int | None = None,
    ) -> List[Tuple[Any, Any]]:
        documents = self.database.get_documents_for_speaker(
            speaker_name=speaker_name,
            limit=limit,
            within_days=within_days,
        )
        bundles: List[Tuple[Any, Any]] = []
        for row in documents:
            fingerprint_row = self.database.get_fingerprint_for_document(row["id"])
            if not fingerprint_row:
                continue
            document = document_from_record(row, segments=self.database.get_document_segments(row["id"]))
            fingerprint = fingerprint_from_record(fingerprint_row, document)
            bundles.append((document, fingerprint))
        bundles.sort(
            key=lambda item: (
                item[0].speech_date.isoformat() if item[0].speech_date else "",
                item[0].document_id,
            ),
            reverse=True,
        )
        return bundles

    def speaker_timeline(self, speaker_name: str, limit: int = 10) -> Dict[str, Any]:
        timeline: List[Dict[str, Any]] = []
        for document, fingerprint in self._speaker_documents_with_fingerprints(speaker_name=speaker_name, limit=limit):
            timeline.append(
                {
                    "document": document.model_dump(mode="json"),
                    "fingerprint_summary": {
                        "overall_tone": fingerprint.overall_tone,
                        "themes": sorted(fingerprint.themes.keys()),
                        "emergent_themes": fingerprint.emergent_themes,
                    },
                }
            )
        return {
            "speaker_name": speaker_name,
            "count": len(timeline),
            "timeline": timeline,
        }

    def recent_comparisons(
        self,
        speaker_name: str,
        comparison_type: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        rows = self.database.get_recent_comparisons(
            speaker_name=speaker_name,
            comparison_type=comparison_type,
            limit=limit,
        )
        comparisons = [comparison_from_record(row).model_dump(mode="json") for row in rows]
        return {
            "speaker_name": speaker_name,
            "count": len(comparisons),
            "comparisons": comparisons,
        }

    def phrase_anomalies(
        self,
        speaker_name: str,
        limit: int = 20,
        min_rarity: float | None = None,
    ) -> Dict[str, Any]:
        rows = self.database.get_phrase_observations(
            speaker_name=speaker_name,
            limit=limit,
            min_rarity=min_rarity,
        )
        anomalies = []
        for row in rows:
            document_meta = row.get("documents") or {}
            anomalies.append(
                {
                    "phrase_text": row.get("phrase_text"),
                    "normalized_phrase": row.get("normalized_phrase"),
                    "semantic_key": row.get("semantic_key"),
                    "rarity_score": row.get("rarity_score"),
                    "current_count": row.get("current_count"),
                    "historical_count": row.get("historical_count"),
                    "document": {
                        "speaker_name": document_meta.get("speaker_name"),
                        "speech_date": document_meta.get("speech_date"),
                        "title": document_meta.get("title"),
                    },
                }
            )
        return {
            "speaker_name": speaker_name,
            "count": len(anomalies),
            "phrase_anomalies": anomalies,
        }

    def latest_document_snapshot(self, speaker_name: str) -> Dict[str, Any]:
        row = self.database.get_recent_document_for_speaker(speaker_name)
        if not row:
            return {"speaker_name": speaker_name, "document": None}
        fingerprint_row = self.database.get_fingerprint_for_document(row["id"])
        document = document_from_record(row, segments=self.database.get_document_segments(row["id"]))
        fingerprint = fingerprint_from_record(fingerprint_row, document) if fingerprint_row else None
        return {
            "speaker_name": speaker_name,
            "document": document.model_dump(mode="json"),
            "fingerprint": fingerprint.model_dump(mode="json") if fingerprint else None,
        }

    def orphaned_concepts(
        self,
        speaker_name: str,
        window_days: int = 75,
        min_emphasis: int = 3,
    ) -> Dict[str, Any]:
        bundles = self._speaker_documents_with_fingerprints(
            speaker_name=speaker_name,
            limit=100,
            within_days=window_days,
        )
        if len(bundles) < 2:
            return {
                "speaker_name": speaker_name,
                "window_days": window_days,
                "latest_document": bundles[0][0].model_dump(mode="json") if bundles else None,
                "orphaned_concepts": [],
            }

        latest_document, latest_fingerprint = bundles[0]
        prior_bundles = bundles[1:]
        historical_counts = Counter()
        supporting_documents: Dict[str, List[Dict[str, Any]]] = {}

        for document, fingerprint in prior_bundles:
            for theme, assessment in fingerprint.themes.items():
                if assessment.emphasis_score < min_emphasis:
                    continue
                historical_counts[theme] += 1
                supporting_documents.setdefault(theme, []).append(
                    {
                        "document_id": document.document_id,
                        "speech_date": document.speech_date.isoformat() if document.speech_date else None,
                        "title": document.title,
                        "emphasis_score": assessment.emphasis_score,
                    }
                )

        orphaned = []
        for theme, count in historical_counts.items():
            if theme in latest_fingerprint.themes:
                continue
            orphaned.append(
                {
                    "theme": theme,
                    "historical_mentions": count,
                    "supporting_documents": supporting_documents.get(theme, [])[:5],
                }
            )

        orphaned.sort(key=lambda item: item["historical_mentions"], reverse=True)
        return {
            "speaker_name": speaker_name,
            "window_days": window_days,
            "latest_document": latest_document.model_dump(mode="json"),
            "orphaned_concepts": orphaned,
        }

    def theme_drift(
        self,
        speaker_name: str,
        theme: Optional[str] = None,
        window_days: int = 730,
        limit: int = 20,
    ) -> Dict[str, Any]:
        bundles = self._speaker_documents_with_fingerprints(
            speaker_name=speaker_name,
            limit=limit,
            within_days=window_days,
        )
        observations: Dict[str, List[Dict[str, Any]]] = {}

        for document, fingerprint in sorted(
            bundles,
            key=lambda item: (item[0].speech_date.isoformat() if item[0].speech_date else "", item[0].document_id),
        ):
            for theme_name, assessment in fingerprint.themes.items():
                if theme and theme_name != theme:
                    continue
                observations.setdefault(theme_name, []).append(
                    {
                        "speech_date": document.speech_date.isoformat() if document.speech_date else None,
                        "document_id": document.document_id,
                        "title": document.title,
                        "document_type": document.document_type.value,
                        "stance": assessment.stance,
                        "trajectory": assessment.trajectory,
                        "emphasis_score": assessment.emphasis_score,
                        "hedging_level": assessment.hedging_level,
                        "overall_tone": fingerprint.overall_tone,
                    }
                )

        drift = []
        for theme_name, rows in observations.items():
            if not rows:
                continue
            first = rows[0]
            last = rows[-1]
            drift.append(
                {
                    "theme": theme_name,
                    "count": len(rows),
                    "first_observation": first,
                    "latest_observation": last,
                    "net_emphasis_change": last["emphasis_score"] - first["emphasis_score"],
                    "stance_path": [row["stance"] for row in rows],
                    "trajectory_path": [row["trajectory"] for row in rows],
                }
            )

        drift.sort(key=lambda item: (abs(item["net_emphasis_change"]), item["count"]), reverse=True)
        return {
            "speaker_name": speaker_name,
            "window_days": window_days,
            "theme": theme,
            "theme_drift": drift,
        }

    def speaker_brief(
        self,
        speaker_name: str,
        theme: Optional[str] = None,
        orphan_window_days: int = 75,
        drift_window_days: int = 730,
    ) -> Dict[str, Any]:
        latest = self.latest_document_snapshot(speaker_name)
        comparisons = self.recent_comparisons(speaker_name, comparison_type="t_minus_1", limit=1)
        orphaned = self.orphaned_concepts(speaker_name, window_days=orphan_window_days)
        drift = self.theme_drift(speaker_name, theme=theme, window_days=drift_window_days)
        phrases = self.phrase_anomalies(speaker_name, limit=10)

        return {
            "speaker_name": speaker_name,
            "theme_focus": theme,
            "latest_snapshot": latest,
            "latest_t_minus_1": comparisons["comparisons"][0] if comparisons["comparisons"] else None,
            "orphaned_concepts_75d": orphaned["orphaned_concepts"],
            "theme_drift_24m": drift["theme_drift"],
            "phrase_anomalies": phrases["phrase_anomalies"],
        }

    def answer_speaker_question(
        self,
        speaker_name: str,
        question: str,
    ) -> Dict[str, Any]:
        theme = self._infer_theme_from_question(question)
        brief = self.speaker_brief(speaker_name, theme=theme)
        highlights: List[str] = []

        latest_comparison = brief.get("latest_t_minus_1") or {}
        if latest_comparison.get("summary"):
            highlights.append(latest_comparison["summary"])

        orphaned = brief.get("orphaned_concepts_75d") or []
        if orphaned:
            highlights.append(
                "Orphaned concepts in 75d window: " +
                ", ".join(item["theme"] for item in orphaned[:3])
            )

        drift = brief.get("theme_drift_24m") or []
        if drift:
            top = drift[0]
            highlights.append(
                f"Theme drift focus: {top['theme']} with net emphasis change {top['net_emphasis_change']}"
            )

        phrases = brief.get("phrase_anomalies") or []
        if phrases:
            highlights.append(
                "Top phrase anomaly: " + phrases[0]["phrase_text"]
            )

        return {
            "speaker_name": speaker_name,
            "question": question,
            "theme_focus": theme,
            "highlights": highlights,
            "brief": brief,
        }

    def _infer_theme_from_question(self, question: str) -> Optional[str]:
        lowered = question.lower()
        for theme, hints in THEME_HINTS.items():
            if any(hint in lowered for hint in hints):
                return theme
        return None
