"""Hawk–dove scorers: heuristic lexicon baseline (RoBERTa lives in hawk_dove.roberta)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from fed_tracker.models import NormalizedDocument
from hawk_dove.models import HawkDoveEvidence, HawkDoveScoreResult, SectionScore


DEFAULT_PROMPT_VERSION = "hawk_dove_v1"
DEFAULT_MODEL_VERSION = "heuristic-hawkdove-v1"
EXTRACTION_VERSION = "v1"
LONG_DOC_CHAR_THRESHOLD = 24000
SECTION_CHAR_TARGET = 6000

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

POLICY_KEYWORDS = {
    "inflation", "prices", "price stability", "labor", "employment", "unemployment",
    "jobs", "growth", "gdp", "demand", "rate", "rates", "federal funds", "restrictive",
    "accommodative", "hike", "cut", "easing", "tightening", "fomc", "dual mandate",
    "policy", "monetary",
}

HAWKISH_TERMS = {
    "elevated": 0.35,
    "persistent": 0.4,
    "upside risk": 0.55,
    "unanchored": 0.7,
    "remain restrictive": 0.7,
    "further tightening": 0.75,
    "raise rates": 0.8,
    "hike": 0.75,
    "higher for longer": 0.7,
    "insufficiently restrictive": 0.75,
    "strong demand": 0.35,
    "tight labor": 0.4,
    "labor market remains strong": 0.45,
    "patient": 0.25,
    "not yet": 0.2,
    "premature": 0.35,
}

DOVISH_TERMS = {
    "progress": 0.25,
    "moderating": 0.35,
    "cooling": 0.35,
    "softening": 0.4,
    "downside risk": 0.55,
    "cut rates": 0.8,
    "reduce rates": 0.75,
    "easing": 0.55,
    "less restrictive": 0.65,
    "overtightening": 0.7,
    "weakening": 0.45,
    "rising unemployment": 0.55,
    "accommodation": 0.6,
    "supportive": 0.3,
    "balanced risks": 0.15,
}


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def _find_offsets(text: str, quote: str) -> Tuple[Optional[int], Optional[int]]:
    start = text.find(quote)
    if start < 0:
        return None, None
    return start, start + len(quote)


def has_monetary_policy_content(text: str, min_hits: int = 3) -> bool:
    lowered = text.lower()
    hits = sum(1 for keyword in POLICY_KEYWORDS if keyword in lowered)
    return hits >= min_hits


def split_policy_sections(text: str, target_chars: int = SECTION_CHAR_TARGET) -> List[Tuple[str, str]]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return [("section_0", text)]

    sections: List[Tuple[str, str]] = []
    current: List[str] = []
    current_len = 0
    index = 0
    for paragraph in paragraphs:
        if current and current_len + len(paragraph) > target_chars:
            body = "\n\n".join(current)
            if has_monetary_policy_content(body, min_hits=2):
                sections.append((f"section_{index}", body))
                index += 1
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len += len(paragraph)
    if current:
        body = "\n\n".join(current)
        if has_monetary_policy_content(body, min_hits=2) or not sections:
            sections.append((f"section_{index}", body))
    return sections or [("section_0", text)]


class BaseHawkDoveScorer:
    prompt_version = DEFAULT_PROMPT_VERSION
    model_version = "base"
    model_parameters: Dict[str, object] = {}

    def score(self, document: NormalizedDocument) -> HawkDoveScoreResult:
        raise NotImplementedError


class HeuristicHawkDoveScorer(BaseHawkDoveScorer):
    model_version = "heuristic-hawkdove-v1"
    model_parameters = {"method": "keyword_weighted_lexicon"}

    def score(self, document: NormalizedDocument) -> HawkDoveScoreResult:
        text = document.normalized_text
        if not has_monetary_policy_content(text):
            return HawkDoveScoreResult(
                overall_score=5.0,
                inflation_score=5.0,
                labor_score=5.0,
                growth_score=5.0,
                policy_action_score=5.0,
                confidence=0.15,
                rationale="Insufficient monetary-policy content for a reliable hawk–dove score.",
                evidence=[],
                insufficient_policy_content=True,
            )

        if len(text) > LONG_DOC_CHAR_THRESHOLD:
            section_results: List[SectionScore] = []
            for section_id, section_text in split_policy_sections(text):
                section_score = self._score_text(section_text)
                section_results.append(
                    SectionScore(
                        section_id=section_id,
                        label=section_id,
                        overall_score=section_score.overall_score,
                        inflation_score=section_score.inflation_score,
                        labor_score=section_score.labor_score,
                        growth_score=section_score.growth_score,
                        policy_action_score=section_score.policy_action_score,
                        confidence=section_score.confidence,
                        rationale=section_score.rationale,
                        evidence=section_score.evidence,
                    )
                )
            return self._synthesize_sections(section_results)

        return self._score_text(text)

    def _score_text(self, text: str) -> HawkDoveScoreResult:
        lowered = text.lower()
        sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]

        hawk_hits: List[Tuple[str, float]] = []
        dove_hits: List[Tuple[str, float]] = []
        for term, weight in HAWKISH_TERMS.items():
            if term in lowered:
                hawk_hits.append((term, weight))
        for term, weight in DOVISH_TERMS.items():
            if term in lowered:
                dove_hits.append((term, weight))

        hawk_strength = sum(weight for _, weight in hawk_hits)
        dove_strength = sum(weight for _, weight in dove_hits)
        net = hawk_strength - dove_strength
        overall = _clamp(5.0 + net * 1.4)

        inflation = self._component_score(
            sentences,
            positive_terms=("inflation", "price", "prices"),
            hawk_boost=("elevated", "persistent", "upside", "unanchored"),
            dove_boost=("progress", "moderating", "cooling", "declining"),
        )
        labor = self._component_score(
            sentences,
            positive_terms=("labor", "employment", "jobs", "unemployment", "payroll"),
            hawk_boost=("tight", "strong", "solid", "resilient"),
            dove_boost=("cooling", "softening", "weakening", "rising unemployment", "slowing"),
        )
        growth = self._component_score(
            sentences,
            positive_terms=("growth", "gdp", "demand", "activity", "outlook"),
            hawk_boost=("strong", "robust", "above trend", "firm"),
            dove_boost=("slowing", "soft", "downside", "weak", "recession"),
        )
        policy = self._component_score(
            sentences,
            positive_terms=("policy", "rate", "rates", "restrictive", "easing", "tightening", "cut", "hike"),
            hawk_boost=("restrictive", "tighten", "hike", "higher for longer", "patient", "premature"),
            dove_boost=("cut", "ease", "less restrictive", "accommodative", "overtightening"),
            prescription_boost=0.6,
        )

        # Blend lexical overall with policy-action emphasis.
        overall = _clamp(0.45 * overall + 0.35 * policy + 0.1 * inflation + 0.05 * labor + 0.05 * growth)

        evidence = self._build_evidence(text, sentences, hawk_hits, dove_hits)
        if (overall < 3.5 or overall > 6.5) and not evidence:
            # Force at least one evidence sentence when extremes lack term hits.
            for sentence in sentences:
                if any(k in sentence.lower() for k in POLICY_KEYWORDS):
                    start, end = _find_offsets(text, sentence[:240])
                    evidence.append(
                        HawkDoveEvidence(
                            quote=sentence[:240],
                            direction="hawkish" if overall > 5 else "dovish",
                            weight=0.5,
                            start_char=start,
                            end_char=end,
                        )
                    )
                    break

        confidence = _clamp(
            0.25 + 0.08 * (len(hawk_hits) + len(dove_hits)) + (0.15 if evidence else 0.0),
            0.0,
            0.95,
        )
        direction = "hawkish" if overall > 5.5 else "dovish" if overall < 4.5 else "balanced"
        rationale = (
            f"Heuristic lexicon score leans {direction} "
            f"(hawk_strength={hawk_strength:.2f}, dove_strength={dove_strength:.2f})."
        )
        return HawkDoveScoreResult(
            overall_score=round(overall, 2),
            inflation_score=round(inflation, 2),
            labor_score=round(labor, 2),
            growth_score=round(growth, 2),
            policy_action_score=round(policy, 2),
            confidence=round(confidence, 2),
            rationale=rationale,
            evidence=evidence[:5],
            insufficient_policy_content=False,
        )

    def _component_score(
        self,
        sentences: Sequence[str],
        positive_terms: Sequence[str],
        hawk_boost: Sequence[str],
        dove_boost: Sequence[str],
        prescription_boost: float = 0.0,
    ) -> float:
        relevant = [s for s in sentences if any(term in s.lower() for term in positive_terms)]
        if not relevant:
            return 5.0
        joined = " ".join(relevant).lower()
        hawk = sum(joined.count(term) * 0.35 for term in hawk_boost)
        dove = sum(joined.count(term) * 0.35 for term in dove_boost)
        if prescription_boost:
            if any(term in joined for term in ("should", "need to", "will", "intend", "prepared to")):
                if hawk > dove:
                    hawk += prescription_boost
                elif dove > hawk:
                    dove += prescription_boost
        return round(_clamp(5.0 + hawk - dove), 2)

    def _build_evidence(
        self,
        text: str,
        sentences: Sequence[str],
        hawk_hits: Sequence[Tuple[str, float]],
        dove_hits: Sequence[Tuple[str, float]],
    ) -> List[HawkDoveEvidence]:
        evidence: List[HawkDoveEvidence] = []
        for term, weight in sorted(hawk_hits, key=lambda item: item[1], reverse=True)[:3]:
            for sentence in sentences:
                if term in sentence.lower():
                    start, end = _find_offsets(text, sentence[:240])
                    evidence.append(
                        HawkDoveEvidence(
                            quote=sentence[:240],
                            direction="hawkish",
                            weight=min(1.0, weight),
                            start_char=start,
                            end_char=end,
                        )
                    )
                    break
        for term, weight in sorted(dove_hits, key=lambda item: item[1], reverse=True)[:3]:
            for sentence in sentences:
                if term in sentence.lower():
                    start, end = _find_offsets(text, sentence[:240])
                    evidence.append(
                        HawkDoveEvidence(
                            quote=sentence[:240],
                            direction="dovish",
                            weight=min(1.0, weight),
                            start_char=start,
                            end_char=end,
                        )
                    )
                    break
        return evidence

    def _synthesize_sections(self, sections: List[SectionScore]) -> HawkDoveScoreResult:
        if not sections:
            return HawkDoveScoreResult(
                overall_score=5.0,
                inflation_score=5.0,
                labor_score=5.0,
                growth_score=5.0,
                policy_action_score=5.0,
                confidence=0.1,
                rationale="No policy sections identified.",
                evidence=[],
                insufficient_policy_content=True,
            )
        weights = [max(0.1, s.confidence) for s in sections]
        weight_sum = sum(weights)

        def weighted(attr: str) -> float:
            return sum(getattr(s, attr) * w for s, w in zip(sections, weights)) / weight_sum

        evidence = []
        for section in sections:
            evidence.extend(section.evidence[:2])
        return HawkDoveScoreResult(
            overall_score=round(weighted("overall_score"), 2),
            inflation_score=round(weighted("inflation_score"), 2),
            labor_score=round(weighted("labor_score"), 2),
            growth_score=round(weighted("growth_score"), 2),
            policy_action_score=round(weighted("policy_action_score"), 2),
            confidence=round(sum(weights) / len(weights), 2),
            rationale=f"Synthesized from {len(sections)} monetary-policy sections.",
            evidence=evidence[:6],
            insufficient_policy_content=False,
            section_scores=sections,
        )


def default_scorer() -> BaseHawkDoveScorer:
    return HeuristicHawkDoveScorer()
