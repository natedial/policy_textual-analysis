from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Iterable, List, Optional
from uuid import uuid4

from fed_tracker.models import ComparisonResult, ComparisonType, SemanticFingerprint, ThemeAssessment, ThemeChange

STANCE_ORDER = ["very_optimistic", "optimistic", "neutral", "concerned", "very_concerned"]
TRAJECTORY_ORDER = ["improving_rapidly", "improving", "stable", "stable_negative", "worsening"]
SIGNIFICANCE_LABELS = {3: "high", 2: "moderate", 1: "low"}
UNCERTAINTY_ORDER = {"low": 0, "medium": 1, "high": 2}


def _ordered_delta(order: List[str], before: str, after: str) -> int:
    try:
        return order.index(after) - order.index(before)
    except ValueError:
        return 0


def _strength(score: int) -> str:
    if score >= 3:
        return "high"
    if score == 2:
        return "moderate"
    return "low"


def _max_uncertainty(*values: str) -> str:
    cleaned = [value for value in values if value]
    if not cleaned:
        return "medium"
    return max(cleaned, key=lambda value: UNCERTAINTY_ORDER.get(value, 1))


def compare_fingerprints(
    base: Optional[SemanticFingerprint],
    target: SemanticFingerprint,
    context_fingerprints: Optional[Iterable[SemanticFingerprint]] = None,
    comparison_type: ComparisonType = ComparisonType.T_MINUS_1,
    window_days: Optional[int] = None,
) -> ComparisonResult:
    theme_changes: List[ThemeChange] = []
    base_themes = base.themes if base else {}
    target_themes = target.themes

    for theme in sorted(set(base_themes) & set(target_themes)):
        before = base_themes[theme]
        after = target_themes[theme]
        change = _compare_theme(theme, before, after)
        if change:
            theme_changes.append(change)

    new_themes = sorted(set(target_themes) - set(base_themes))
    orphaned_concepts = []
    context_fingerprints = list(context_fingerprints or [])
    if context_fingerprints:
        orphaned_concepts = detect_orphaned_concepts(target, context_fingerprints, window_days=window_days)

    phrase_anomalies = sorted(target.phrase_signals, key=lambda item: item.rarity_score, reverse=True)[:10]

    summary_bits = []
    if theme_changes:
        summary_bits.append(f"{len(theme_changes)} theme changes vs baseline")
    if new_themes:
        summary_bits.append(f"{len(new_themes)} new themes")
    if orphaned_concepts:
        summary_bits.append(f"{len(orphaned_concepts)} orphaned concepts")
    if phrase_anomalies:
        summary_bits.append(f"{len(phrase_anomalies)} phrase anomalies")
    summary = "; ".join(summary_bits) if summary_bits else "No material changes detected"

    uncertainty_notes = list(target.uncertainty_notes)
    if base:
        uncertainty_notes.extend(note for note in base.uncertainty_notes if note not in uncertainty_notes)

    return ComparisonResult(
        comparison_id=f"cmp_{uuid4().hex[:12]}",
        speaker_name=target.speaker_name,
        target_document_id=target.document_id,
        base_document_id=base.document_id if base else None,
        comparison_type=comparison_type,
        window_days=window_days,
        theme_changes=theme_changes,
        orphaned_concepts=orphaned_concepts,
        new_themes=new_themes,
        phrase_anomalies=phrase_anomalies,
        summary=summary,
        uncertainty_notes=uncertainty_notes,
    )


def _compare_theme(theme: str, before: ThemeAssessment, after: ThemeAssessment) -> Optional[ThemeChange]:
    stance_delta = _ordered_delta(STANCE_ORDER, before.stance, after.stance)
    trajectory_delta = _ordered_delta(TRAJECTORY_ORDER, before.trajectory, after.trajectory)
    emphasis_delta = after.emphasis_score - before.emphasis_score
    hedge_delta = _hedging_score(after.hedging_level) - _hedging_score(before.hedging_level)

    severity = 0
    if stance_delta:
        severity += 1 + min(abs(stance_delta), 2)
    if trajectory_delta:
        severity += 1 + min(abs(trajectory_delta), 2)
    if abs(emphasis_delta) >= 2:
        severity += 1
    if abs(hedge_delta) >= 1:
        severity += 1
    if severity == 0:
        return None

    summaries = []
    change_type = "mixed_shift"
    if stance_delta > 0:
        change_type = "more_concerned"
        summaries.append(f"stance moved from {before.stance} to {after.stance}")
    elif stance_delta < 0:
        change_type = "more_optimistic"
        summaries.append(f"stance moved from {before.stance} to {after.stance}")

    if trajectory_delta > 0:
        change_type = "worse_trajectory" if change_type == "mixed_shift" else change_type
        summaries.append(f"trajectory moved from {before.trajectory} to {after.trajectory}")
    elif trajectory_delta < 0:
        change_type = "better_trajectory" if change_type == "mixed_shift" else change_type
        summaries.append(f"trajectory moved from {before.trajectory} to {after.trajectory}")

    if abs(emphasis_delta) >= 2:
        direction = "increased" if emphasis_delta > 0 else "decreased"
        change_type = "emphasis_shift" if change_type == "mixed_shift" else change_type
        summaries.append(f"emphasis {direction} from {before.emphasis_score} to {after.emphasis_score}")

    if abs(hedge_delta) >= 1:
        direction = "more hedged" if hedge_delta > 0 else "less hedged"
        summaries.append(f"language became {direction}")

    return ThemeChange(
        theme=theme,
        change_type=change_type,
        strength=_strength(min(severity, 3)),
        uncertainty=_max_uncertainty(before.uncertainty, after.uncertainty),
        before=before,
        after=after,
        evidence_before=before.evidence[:2],
        evidence_after=after.evidence[:2],
        summary="; ".join(summaries),
    )


def _hedging_score(level: str) -> int:
    return {"none": 0, "light": 1, "moderate": 2, "heavy": 3}.get(level, 0)


def detect_orphaned_concepts(
    target: SemanticFingerprint,
    context_fingerprints: Iterable[SemanticFingerprint],
    window_days: Optional[int] = None,
) -> List[str]:
    context_fingerprints = list(context_fingerprints)
    if window_days is not None and target.speech_date:
        floor = target.speech_date - timedelta(days=window_days)
        filtered = [
            fp for fp in context_fingerprints
            if fp.speech_date and fp.speech_date >= floor and fp.document_id != target.document_id
        ]
    else:
        filtered = [fp for fp in context_fingerprints if fp.document_id != target.document_id]

    historical_themes = Counter()
    for fingerprint in filtered:
        for theme, assessment in fingerprint.themes.items():
            if assessment.emphasis_score >= 3:
                historical_themes[theme] += 1

    orphaned = [theme for theme, count in historical_themes.items() if count > 0 and theme not in target.themes]
    return sorted(orphaned)


def summarize_window(fingerprints: Iterable[SemanticFingerprint], window_label: str) -> str:
    fingerprints = list(fingerprints)
    if not fingerprints:
        return f"No documents available for {window_label}."

    theme_counts = Counter()
    tone_counts = Counter()
    for fingerprint in fingerprints:
        theme_counts.update(fingerprint.themes.keys())
        if fingerprint.overall_tone:
            tone_counts[fingerprint.overall_tone] += 1

    most_common_themes = ", ".join(theme for theme, _ in theme_counts.most_common(3)) or "none"
    dominant_tone = tone_counts.most_common(1)[0][0] if tone_counts else "unknown"
    return f"{window_label}: dominant themes {most_common_themes}; dominant tone {dominant_tone}."
