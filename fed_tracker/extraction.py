from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from fed_tracker.models import EvidenceQuote, NormalizedDocument, SemanticFingerprint, ThemeAssessment
from fed_tracker.ontology import (
    CORE_THEMES,
    DEFAULT_MODEL_VERSION,
    DEFAULT_PROMPT_VERSION,
    HEDGING_WORDS,
    THEME_KEYWORDS,
)
from fed_tracker.phrase_signals import build_phrase_signals

try:
    import anthropic
except ImportError:  # pragma: no cover - dependency is optional at runtime
    anthropic = None


STANCE_POSITIVE = {"progress", "moderating", "moderation", "improving", "improvement", "declined", "declining", "balanced"}
STANCE_NEGATIVE = {"elevated", "persistent", "concern", "concerning", "strong", "resilient", "upside", "inflationary", "tight", "restrictive"}
TRAJECTORY_POSITIVE = {"improving", "moderating", "slowing", "cooling", "declining", "easing"}
TRAJECTORY_NEGATIVE = {"worsening", "accelerating", "rising", "elevated", "persistent", "firming"}
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _find_offsets(text: str, quote: str) -> EvidenceQuote:
    start = text.find(quote)
    end = start + len(quote) if start >= 0 else None
    return EvidenceQuote(quote=quote, start_char=start if start >= 0 else None, end_char=end)


class BaseFingerprintExtractor:
    def extract(
        self,
        document: NormalizedDocument,
        historical_texts: Optional[Iterable[str]] = None,
    ) -> SemanticFingerprint:
        raise NotImplementedError


class HeuristicFingerprintExtractor(BaseFingerprintExtractor):
    model_version = "heuristic-v1"
    prompt_version = DEFAULT_PROMPT_VERSION

    def extract(
        self,
        document: NormalizedDocument,
        historical_texts: Optional[Iterable[str]] = None,
    ) -> SemanticFingerprint:
        text = document.normalized_text
        historical_texts = list(historical_texts or [])
        sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_RE.split(text) if sentence.strip()]
        lowered_text = text.lower()
        themes: Dict[str, ThemeAssessment] = {}

        for theme in CORE_THEMES:
            keywords = THEME_KEYWORDS.get(theme, [])
            matched_sentences = [
                sentence for sentence in sentences
                if any(keyword in sentence.lower() for keyword in keywords)
            ]
            keyword_hits = sum(lowered_text.count(keyword) for keyword in keywords)
            if keyword_hits < 2 and len(matched_sentences) < 2:
                continue

            stance = self._infer_stance(matched_sentences)
            trajectory = self._infer_trajectory(matched_sentences)
            hedges = self._extract_hedges(matched_sentences)
            emphasis = max(1, min(10, len(matched_sentences) + min(keyword_hits, 4)))
            evidence = [_find_offsets(text, sentence[:280]) for sentence in matched_sentences[:3]]

            themes[theme] = ThemeAssessment(
                stance=stance,
                trajectory=trajectory,
                emphasis_score=emphasis,
                hedging_level=self._hedging_level(hedges),
                key_hedges=hedges,
                confidence="low" if len(matched_sentences) < 3 else "moderate",
                uncertainty="high" if len(matched_sentences) < 3 else "medium",
                evidence=evidence,
            )

        phrase_signals = build_phrase_signals(text, historical_texts)
        uncertainty_notes = ["Heuristic extraction used; treat outputs as draft quality."]
        if not themes:
            uncertainty_notes.append("No themes met the heuristic inclusion threshold.")

        return SemanticFingerprint(
            document_id=document.document_id,
            speaker_name=document.speaker_name,
            speech_date=document.speech_date,
            document_type=document.document_type,
            themes=themes,
            emergent_themes=[],
            phrase_signals=phrase_signals,
            overall_tone=self._overall_tone(sentences),
            uncertainty_notes=uncertainty_notes,
            prompt_version=self.prompt_version,
            model_version=self.model_version,
            raw_llm_response=None,
        )

    def _infer_stance(self, sentences: List[str]) -> str:
        joined = " ".join(sentences).lower()
        positive = sum(joined.count(word) for word in STANCE_POSITIVE)
        negative = sum(joined.count(word) for word in STANCE_NEGATIVE)
        if negative - positive >= 3:
            return "very_concerned"
        if negative > positive:
            return "concerned"
        if positive - negative >= 3:
            return "very_optimistic"
        if positive > negative:
            return "optimistic"
        return "neutral"

    def _infer_trajectory(self, sentences: List[str]) -> str:
        joined = " ".join(sentences).lower()
        positive = sum(joined.count(word) for word in TRAJECTORY_POSITIVE)
        negative = sum(joined.count(word) for word in TRAJECTORY_NEGATIVE)
        if negative > positive:
            return "worsening"
        if positive >= negative + 2:
            return "improving"
        if negative == positive == 0:
            return "stable"
        return "stable_negative" if negative else "stable"

    def _extract_hedges(self, sentences: List[str]) -> List[str]:
        joined = " ".join(sentences).lower()
        found = [word for word in sorted(HEDGING_WORDS) if word in joined]
        return found[:6]

    def _hedging_level(self, hedges: List[str]) -> str:
        count = len(hedges)
        if count == 0:
            return "none"
        if count <= 2:
            return "light"
        if count <= 4:
            return "moderate"
        return "heavy"

    def _overall_tone(self, sentences: List[str]) -> str:
        joined = " ".join(sentences[:20]).lower()
        if any(token in joined for token in ["uncertain", "careful", "cautious"]):
            return "cautious"
        if any(token in joined for token in ["confident", "strong", "resilient"]):
            return "confident"
        return "measured"


class AnthropicFingerprintExtractor(BaseFingerprintExtractor):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_version: str = DEFAULT_MODEL_VERSION,
        prompt_path: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model_version = model_version
        self.prompt_version = DEFAULT_PROMPT_VERSION
        self.prompt_path = Path(prompt_path or Path(__file__).resolve().parent.parent / "prompts" / "fingerprint_prompt_v2.txt")

        if anthropic is None:
            raise RuntimeError("anthropic package is not installed")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set to use AnthropicFingerprintExtractor")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def extract(
        self,
        document: NormalizedDocument,
        historical_texts: Optional[Iterable[str]] = None,
    ) -> SemanticFingerprint:
        prompt = self._build_prompt(document)
        response = self.client.messages.create(
            model=self.model_version,
            max_tokens=4000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_response = response.content[0].text
        payload = self._parse_response(raw_response)
        phrase_signals = build_phrase_signals(document.normalized_text, list(historical_texts or []))

        themes: Dict[str, ThemeAssessment] = {}
        for theme_name, theme_data in payload.get("themes", {}).items():
            evidence = [_find_offsets(document.normalized_text, quote) for quote in theme_data.get("evidence", [])]
            themes[theme_name] = ThemeAssessment(
                stance=theme_data["stance"],
                trajectory=theme_data["trajectory"],
                emphasis_score=theme_data["emphasis_score"],
                hedging_level=theme_data["hedging_level"],
                key_hedges=theme_data.get("key_hedges", []),
                confidence=theme_data["confidence"],
                uncertainty=theme_data.get("uncertainty", "medium"),
                evidence=evidence,
            )

        return SemanticFingerprint(
            document_id=document.document_id,
            speaker_name=document.speaker_name,
            speech_date=document.speech_date,
            document_type=document.document_type,
            themes=themes,
            emergent_themes=payload.get("emergent_themes", []),
            phrase_signals=phrase_signals,
            overall_tone=payload.get("overall_tone", ""),
            uncertainty_notes=payload.get("uncertainty_notes", []),
            prompt_version=self.prompt_version,
            model_version=self.model_version,
            raw_llm_response=raw_response,
        )

    def _build_prompt(self, document: NormalizedDocument) -> str:
        template = self.prompt_path.read_text()
        return template.format(
            title=document.title or "",
            speaker_name=document.speaker_name or "",
            speech_date=document.speech_date.isoformat() if document.speech_date else "",
            document_type=document.document_type.value,
            speech_text=document.normalized_text,
        )

    def _parse_response(self, raw_response: str) -> Dict[str, object]:
        json_str = raw_response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```", 1)[1].split("```", 1)[0].strip()
        return json.loads(json_str)
