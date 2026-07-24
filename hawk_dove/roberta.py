"""Optional RoBERTa baseline scorer (gtfintechlab/fomc-hawkish-dovish).

Component (inflation/labor/growth/policy) scores are derived by keyword-routing
RoBERTa-labeled sentences — they are not native model heads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

from fed_tracker.models import NormalizedDocument
from fed_tracker.ontology import THEME_KEYWORDS
from hawk_dove.models import HawkDoveEvidence, HawkDoveScoreResult
from hawk_dove.scoring import (
    SENTENCE_SPLIT_RE,
    BaseHawkDoveScorer,
    _find_offsets,
    has_monetary_policy_content,
)

ROBERTA_MODEL_ID = "gtfintechlab/fomc-hawkish-dovish"
ROBERTA_PROMPT_VERSION = "roberta_baseline_v1"

LABEL_SCORE = {
    "hawkish": 10.0,
    "dovish": 0.0,
    "neutral": 5.0,
}

COMPONENT_KEYWORDS = {
    "inflation": THEME_KEYWORDS.get("INFLATION", []),
    "labor": THEME_KEYWORDS.get("LABOR_MARKETS", []),
    "growth": THEME_KEYWORDS.get("GROWTH_OUTLOOK", []),
    "policy_action": THEME_KEYWORDS.get("POLICY_STANCE", []),
}


class SentenceClassifier(Protocol):
    def classify(self, texts: Sequence[str]) -> List["SentencePrediction"]:
        ...


@dataclass
class SentencePrediction:
    label: str
    scores: Dict[str, float]
    confidence: float


class StubSentenceClassifier:
    """Deterministic fallback used in tests / when transformers is unavailable."""

    HAWKISH = ("elevated", "restrictive", "tighten", "hike", "persistent", "upside")
    DOVISH = ("cut", "easing", "moderating", "cooling", "overtightening", "downside")

    def classify(self, texts: Sequence[str]) -> List[SentencePrediction]:
        predictions: List[SentencePrediction] = []
        for text in texts:
            lowered = text.lower()
            hawk = sum(1 for token in self.HAWKISH if token in lowered)
            dove = sum(1 for token in self.DOVISH if token in lowered)
            if hawk > dove:
                label = "hawkish"
                scores = {"hawkish": 0.7, "neutral": 0.2, "dovish": 0.1}
            elif dove > hawk:
                label = "dovish"
                scores = {"hawkish": 0.1, "neutral": 0.2, "dovish": 0.7}
            else:
                label = "neutral"
                scores = {"hawkish": 0.2, "neutral": 0.6, "dovish": 0.2}
            predictions.append(
                SentencePrediction(label=label, scores=scores, confidence=scores[label])
            )
        return predictions


class TransformersSentenceClassifier:
    def __init__(self, model_id: str = ROBERTA_MODEL_ID, device: Optional[int] = None):
        try:
            from transformers import pipeline
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "transformers is required for RobertaHawkDoveScorer. "
                "Install optional deps: pip install transformers torch"
            ) from exc

        kwargs = {"model": model_id, "tokenizer": model_id, "top_k": None}
        if device is not None:
            kwargs["device"] = device
        self._pipe = pipeline("text-classification", **kwargs)
        self.model_id = model_id

    def classify(self, texts: Sequence[str]) -> List[SentencePrediction]:
        if not texts:
            return []
        raw = self._pipe(list(texts), truncation=True, max_length=256)
        predictions: List[SentencePrediction] = []
        for item in raw:
            # pipeline may return list-of-dicts (all labels) or a single dict
            rows = item if isinstance(item, list) else [item]
            scores: Dict[str, float] = {}
            for row in rows:
                label = _normalize_label(str(row.get("label", "neutral")))
                scores[label] = float(row.get("score", 0.0))
            if not scores:
                scores = {"neutral": 1.0}
            label = max(scores.items(), key=lambda pair: pair[1])[0]
            predictions.append(
                SentencePrediction(label=label, scores=scores, confidence=scores.get(label, 0.0))
            )
        return predictions


def _normalize_label(label: str) -> str:
    cleaned = label.strip().lower().replace("label_", "")
    if "hawk" in cleaned:
        return "hawkish"
    if "dove" in cleaned:
        return "dovish"
    if "neutral" in cleaned or cleaned in {"2", "label_2"}:
        return "neutral"
    # common integer encodings from the TDW model card variants
    if cleaned in {"1", "label_1"}:
        return "hawkish"
    if cleaned in {"0", "label_0"}:
        return "dovish"
    return "neutral"


def sentence_score(prediction: SentencePrediction) -> float:
    scores = prediction.scores
    if scores:
        total = (
            LABEL_SCORE["dovish"] * scores.get("dovish", 0.0)
            + LABEL_SCORE["neutral"] * scores.get("neutral", 0.0)
            + LABEL_SCORE["hawkish"] * scores.get("hawkish", 0.0)
        )
        mass = sum(scores.get(key, 0.0) for key in LABEL_SCORE)
        if mass > 0:
            return total / mass
    return LABEL_SCORE.get(prediction.label, 5.0)


def _route_component(sentence: str, component: str) -> bool:
    lowered = sentence.lower()
    return any(keyword in lowered for keyword in COMPONENT_KEYWORDS.get(component, []))


class RobertaHawkDoveScorer(BaseHawkDoveScorer):
    prompt_version = ROBERTA_PROMPT_VERSION
    model_version = ROBERTA_MODEL_ID

    def __init__(
        self,
        classifier: Optional[SentenceClassifier] = None,
        model_id: str = ROBERTA_MODEL_ID,
        use_transformers: bool = True,
    ):
        self.model_version = model_id
        self.model_parameters = {
            "method": "roberta_sentence_baseline",
            "model_id": model_id,
            "component_scores": "keyword_routed_over_roberta_labels",
            "component_scores_native": False,
        }
        if classifier is not None:
            self.classifier = classifier
        elif use_transformers:
            try:
                self.classifier = TransformersSentenceClassifier(model_id=model_id)
            except Exception:
                self.classifier = StubSentenceClassifier()
                self.model_parameters["classifier_fallback"] = "stub"
        else:
            self.classifier = StubSentenceClassifier()
            self.model_parameters["classifier_fallback"] = "stub"

    def score(self, document: NormalizedDocument) -> HawkDoveScoreResult:
        text = document.normalized_text
        if not has_monetary_policy_content(text):
            return HawkDoveScoreResult(
                overall_score=5.0,
                inflation_score=5.0,
                labor_score=5.0,
                growth_score=5.0,
                policy_action_score=5.0,
                confidence=0.2,
                rationale="Insufficient monetary-policy content for a reliable hawk–dove score.",
                evidence=[],
                insufficient_policy_content=True,
            )

        sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
        policy_sentences = [
            s for s in sentences if has_monetary_policy_content(s, min_hits=1) or len(s.split()) >= 8
        ]
        if not policy_sentences:
            policy_sentences = sentences[:12]

        predictions = self.classifier.classify(policy_sentences)
        scored_rows = [
            (sentence, prediction, sentence_score(prediction))
            for sentence, prediction in zip(policy_sentences, predictions)
        ]
        if not scored_rows:
            return HawkDoveScoreResult(
                overall_score=5.0,
                inflation_score=5.0,
                labor_score=5.0,
                growth_score=5.0,
                policy_action_score=5.0,
                confidence=0.2,
                rationale="No sentences available for RoBERTa scoring.",
                evidence=[],
                insufficient_policy_content=True,
            )

        overall = sum(value for _, _, value in scored_rows) / len(scored_rows)
        confidence = sum(pred.confidence for _, pred, _ in scored_rows) / len(scored_rows)

        components = {
            name: self._component_from_rows(scored_rows, name, default=overall)
            for name in ("inflation", "labor", "growth", "policy_action")
        }

        evidence = self._build_evidence(text, scored_rows)
        label_counts = {"hawkish": 0, "dovish": 0, "neutral": 0}
        for _, pred, _ in scored_rows:
            label_counts[pred.label] = label_counts.get(pred.label, 0) + 1

        rationale = (
            f"RoBERTa baseline averaged {len(scored_rows)} sentences "
            f"(hawkish={label_counts.get('hawkish', 0)}, "
            f"neutral={label_counts.get('neutral', 0)}, "
            f"dovish={label_counts.get('dovish', 0)}). "
            "Component scores are keyword-routed over labeled sentences, not native model outputs."
        )
        return HawkDoveScoreResult(
            overall_score=round(overall, 2),
            inflation_score=round(components["inflation"], 2),
            labor_score=round(components["labor"], 2),
            growth_score=round(components["growth"], 2),
            policy_action_score=round(components["policy_action"], 2),
            confidence=round(min(0.95, max(0.05, confidence)), 2),
            rationale=rationale,
            evidence=evidence,
            insufficient_policy_content=False,
        )

    def _component_from_rows(
        self,
        rows: Sequence[Tuple[str, SentencePrediction, float]],
        component: str,
        default: float,
    ) -> float:
        matched = [value for sentence, _, value in rows if _route_component(sentence, component)]
        if not matched:
            return default
        return sum(matched) / len(matched)

    def _build_evidence(
        self,
        text: str,
        rows: Sequence[Tuple[str, SentencePrediction, float]],
    ) -> List[HawkDoveEvidence]:
        ranked = sorted(rows, key=lambda item: abs(item[2] - 5.0) * item[1].confidence, reverse=True)
        evidence: List[HawkDoveEvidence] = []
        for sentence, prediction, value in ranked[:5]:
            start, end = _find_offsets(text, sentence[:240])
            direction = prediction.label if prediction.label in {"hawkish", "dovish", "neutral"} else "neutral"
            if direction == "neutral" and value > 6.0:
                direction = "hawkish"
            elif direction == "neutral" and value < 4.0:
                direction = "dovish"
            evidence.append(
                HawkDoveEvidence(
                    quote=sentence[:240],
                    direction=direction,  # type: ignore[arg-type]
                    weight=round(min(1.0, prediction.confidence), 3),
                    start_char=start,
                    end_char=end,
                )
            )
        return evidence
