"""
Shift detection and comparison engine.
Compares semantic fingerprints to identify meaningful changes.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from extract import SemanticFingerprint, ThemeFingerprint


class Evidence(BaseModel):
    """Evidence supporting a detected shift."""
    speech_a_quotes: List[str]
    speech_b_quotes: List[str]
    verified: bool = False


class Shift(BaseModel):
    """A detected shift between two speeches."""
    theme: str
    shift_type: str
    significance: str  # HIGH, MEDIUM, LOW
    from_state: Optional[Dict[str, Any]]
    to_state: Optional[Dict[str, Any]]
    interpretation: str
    evidence: Evidence
    market_implication: Optional[str] = None


# Shift categorization logic
STANCE_ORDER = ["very_optimistic", "optimistic", "neutral", "concerned", "very_concerned"]
TRAJECTORY_ORDER = ["improving_rapidly", "improving", "stable", "stable_negative", "worsening"]


def get_stance_shift_magnitude(from_stance: str, to_stance: str) -> int:
    """Calculate magnitude of stance shift (positive = more hawkish/concerned)."""
    try:
        from_idx = STANCE_ORDER.index(from_stance)
        to_idx = STANCE_ORDER.index(to_stance)
        return to_idx - from_idx
    except ValueError:
        return 0


def get_trajectory_shift_magnitude(from_traj: str, to_traj: str) -> int:
    """Calculate magnitude of trajectory shift (positive = worsening)."""
    try:
        from_idx = TRAJECTORY_ORDER.index(from_traj)
        to_idx = TRAJECTORY_ORDER.index(to_traj)
        return to_idx - from_idx
    except ValueError:
        return 0


def categorize_shift_type(
    theme: str,
    stance_shift: int,
    trajectory_shift: int,
    emphasis_delta: float,
    hedging_change: int
) -> str:
    """
    Categorize the type of shift based on multiple signals.

    Returns:
        Shift type: HAWKISH_DRIFT, DOVISH_PIVOT, NEW_EMPHASIS, etc.
    """
    # Hawkish indicators: more concerned, worsening trajectory, less hedging
    hawkish_score = stance_shift + trajectory_shift - hedging_change

    if abs(emphasis_delta) >= 3:
        if emphasis_delta > 0:
            return "NEW_EMPHASIS"
        else:
            return "REDUCED_EMPHASIS"

    if hawkish_score >= 2:
        return "HAWKISH_DRIFT"
    elif hawkish_score <= -2:
        return "DOVISH_PIVOT"
    elif abs(hedging_change) >= 2:
        return "CONVICTION_CHANGE"
    elif stance_shift != 0 or trajectory_shift != 0:
        return "SUBTLE_SHIFT"
    else:
        return "MINOR_CHANGE"


def assess_significance(
    shift_type: str,
    theme: str,
    stance_shift: int,
    trajectory_shift: int,
    emphasis_delta: float
) -> str:
    """
    Assess the significance of a detected shift.

    Returns:
        Significance level: HIGH, MEDIUM, LOW
    """
    # High-impact themes
    high_impact_themes = ["INFLATION", "POLICY_STANCE", "LABOR_MARKETS"]

    # Calculate overall magnitude
    magnitude = abs(stance_shift) + abs(trajectory_shift) + abs(emphasis_delta) / 3

    if shift_type in ["HAWKISH_DRIFT", "DOVISH_PIVOT", "ORPHANED_CONCEPT"]:
        if theme in high_impact_themes or magnitude >= 3:
            return "HIGH"
        else:
            return "MEDIUM"
    elif shift_type in ["NEW_EMPHASIS", "CONVICTION_CHANGE"]:
        if magnitude >= 4:
            return "HIGH"
        else:
            return "MEDIUM"
    else:
        if magnitude >= 2:
            return "MEDIUM"
        else:
            return "LOW"


def get_hedging_level_score(hedging_level: str) -> int:
    """Convert hedging level to numeric score."""
    hedging_map = {"none": 0, "light": 1, "moderate": 2, "heavy": 3}
    return hedging_map.get(hedging_level, 0)


def detect_theme_shift(
    theme: str,
    theme_a: ThemeFingerprint,
    theme_b: ThemeFingerprint
) -> Optional[Shift]:
    """
    Detect shifts for a single theme between two speeches.

    Args:
        theme: Theme name
        theme_a: Theme fingerprint from speech A
        theme_b: Theme fingerprint from speech B

    Returns:
        Shift object if significant change detected, None otherwise
    """
    # Calculate shifts
    stance_shift = get_stance_shift_magnitude(theme_a.stance, theme_b.stance)
    trajectory_shift = get_trajectory_shift_magnitude(theme_a.trajectory, theme_b.trajectory)
    emphasis_delta = theme_b.emphasis_score - theme_a.emphasis_score
    hedging_a = get_hedging_level_score(theme_a.hedging_level)
    hedging_b = get_hedging_level_score(theme_b.hedging_level)
    hedging_change = hedging_b - hedging_a

    # Determine if change is significant enough to report
    if (abs(stance_shift) == 0 and abs(trajectory_shift) == 0 and
        abs(emphasis_delta) < 2 and abs(hedging_change) == 0):
        return None  # No significant change

    # Categorize shift
    shift_type = categorize_shift_type(
        theme, stance_shift, trajectory_shift, emphasis_delta, hedging_change
    )

    # Assess significance
    significance = assess_significance(
        shift_type, theme, stance_shift, trajectory_shift, emphasis_delta
    )

    # Build interpretation
    interpretation_parts = []

    if stance_shift != 0:
        direction = "more concerned" if stance_shift > 0 else "more optimistic"
        interpretation_parts.append(f"Stance shifted {direction} (from '{theme_a.stance}' to '{theme_b.stance}')")

    if trajectory_shift != 0:
        direction = "worsening" if trajectory_shift > 0 else "improving"
        interpretation_parts.append(f"Trajectory viewed as {direction} (from '{theme_a.trajectory}' to '{theme_b.trajectory}')")

    if abs(emphasis_delta) >= 2:
        direction = "increased" if emphasis_delta > 0 else "decreased"
        interpretation_parts.append(f"Emphasis {direction} from {theme_a.emphasis_score}/10 to {theme_b.emphasis_score}/10")

    if hedging_change != 0:
        direction = "increased" if hedging_change > 0 else "decreased"
        interpretation_parts.append(f"Hedging {direction} (from '{theme_a.hedging_level}' to '{theme_b.hedging_level}')")

    interpretation = ". ".join(interpretation_parts)

    # Create evidence
    evidence = Evidence(
        speech_a_quotes=theme_a.key_passages[:2],  # Limit to first 2
        speech_b_quotes=theme_b.key_passages[:2],
        verified=False  # Will be verified later
    )

    # Create shift object
    shift = Shift(
        theme=theme,
        shift_type=shift_type,
        significance=significance,
        from_state={
            "stance": theme_a.stance,
            "trajectory": theme_a.trajectory,
            "emphasis": theme_a.emphasis_score,
            "hedging": theme_a.hedging_level,
            "hedges": theme_a.key_hedges
        },
        to_state={
            "stance": theme_b.stance,
            "trajectory": theme_b.trajectory,
            "emphasis": theme_b.emphasis_score,
            "hedging": theme_b.hedging_level,
            "hedges": theme_b.key_hedges
        },
        interpretation=interpretation,
        evidence=evidence
    )

    return shift


def detect_orphaned_themes(
    fp_a: SemanticFingerprint,
    fp_b: SemanticFingerprint
) -> List[Shift]:
    """
    Detect themes that were discussed in speech A but not in speech B.

    Args:
        fp_a: Fingerprint from earlier speech
        fp_b: Fingerprint from later speech

    Returns:
        List of orphaned concept shifts
    """
    orphaned_shifts = []

    themes_a = set(fp_a.themes.keys())
    themes_b = set(fp_b.themes.keys())
    orphaned_themes = themes_a - themes_b

    for theme in orphaned_themes:
        theme_a = fp_a.themes[theme]

        # Only report if it had significant emphasis
        if theme_a.emphasis_score >= 3:
            interpretation = (
                f"Theme '{theme}' was discussed in the earlier speech "
                f"(emphasis: {theme_a.emphasis_score}/10, stance: {theme_a.stance}) "
                f"but is not mentioned in the later speech."
            )

            evidence = Evidence(
                speech_a_quotes=theme_a.key_passages[:2],
                speech_b_quotes=[],
                verified=False
            )

            shift = Shift(
                theme=theme,
                shift_type="ORPHANED_CONCEPT",
                significance="HIGH" if theme_a.emphasis_score >= 6 else "MEDIUM",
                from_state={
                    "stance": theme_a.stance,
                    "trajectory": theme_a.trajectory,
                    "emphasis": theme_a.emphasis_score
                },
                to_state=None,
                interpretation=interpretation,
                evidence=evidence,
                market_implication="Narrative shift - this topic may no longer be a policy concern"
            )

            orphaned_shifts.append(shift)

    return orphaned_shifts


def detect_new_themes(
    fp_a: SemanticFingerprint,
    fp_b: SemanticFingerprint
) -> List[Shift]:
    """
    Detect themes that appear in speech B but not in speech A.

    Args:
        fp_a: Fingerprint from earlier speech
        fp_b: Fingerprint from later speech

    Returns:
        List of new theme shifts
    """
    new_shifts = []

    themes_a = set(fp_a.themes.keys())
    themes_b = set(fp_b.themes.keys())
    new_themes = themes_b - themes_a

    for theme in new_themes:
        theme_b = fp_b.themes[theme]

        # Only report if it has significant emphasis
        if theme_b.emphasis_score >= 3:
            interpretation = (
                f"Theme '{theme}' is newly discussed in this speech "
                f"(emphasis: {theme_b.emphasis_score}/10, stance: {theme_b.stance})."
            )

            evidence = Evidence(
                speech_a_quotes=[],
                speech_b_quotes=theme_b.key_passages[:2],
                verified=False
            )

            shift = Shift(
                theme=theme,
                shift_type="NEW_THEME",
                significance="HIGH" if theme_b.emphasis_score >= 6 else "MEDIUM",
                from_state=None,
                to_state={
                    "stance": theme_b.stance,
                    "trajectory": theme_b.trajectory,
                    "emphasis": theme_b.emphasis_score
                },
                interpretation=interpretation,
                evidence=evidence,
                market_implication="Emerging policy consideration"
            )

            new_shifts.append(shift)

    return new_shifts


def detect_shifts(
    fp_a: SemanticFingerprint,
    fp_b: SemanticFingerprint
) -> List[Shift]:
    """
    Detect all shifts between two semantic fingerprints.

    Args:
        fp_a: Fingerprint from earlier speech
        fp_b: Fingerprint from later speech

    Returns:
        List of detected shifts
    """
    all_shifts = []

    # Detect shifts in common themes
    common_themes = set(fp_a.themes.keys()) & set(fp_b.themes.keys())
    for theme in common_themes:
        shift = detect_theme_shift(theme, fp_a.themes[theme], fp_b.themes[theme])
        if shift:
            all_shifts.append(shift)

    # Detect orphaned themes
    orphaned = detect_orphaned_themes(fp_a, fp_b)
    all_shifts.extend(orphaned)

    # Detect new themes
    new_themes = detect_new_themes(fp_a, fp_b)
    all_shifts.extend(new_themes)

    # Sort by significance (HIGH > MEDIUM > LOW)
    significance_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    all_shifts.sort(key=lambda s: significance_order.get(s.significance, 3))

    return all_shifts
