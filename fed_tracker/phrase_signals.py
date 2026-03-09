from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Iterable, List

from fed_tracker.models import PhraseSignal
from fed_tracker.ontology import LOW_SIGNAL_PHRASES

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "that", "the", "their", "this", "to",
    "was", "we", "will", "with", "would", "our", "they", "i", "you", "he", "she", "them",
}

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-']+")


def _normalize_phrase(phrase: str) -> str:
    return re.sub(r"\s+", " ", phrase.lower()).strip(" .,;:\"'()[]{}")


def _semantic_key(normalized_phrase: str) -> str:
    return hashlib.sha1(normalized_phrase.encode("utf-8")).hexdigest()[:12]


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _extract_candidate_ngrams(text: str, min_words: int = 2, max_words: int = 5) -> Counter:
    tokens = _tokenize(text)
    counts: Counter = Counter()
    for size in range(min_words, max_words + 1):
        for index in range(0, len(tokens) - size + 1):
            window = tokens[index:index + size]
            if sum(1 for token in window if token not in STOPWORDS) < 2:
                continue
            phrase = " ".join(window)
            if phrase in LOW_SIGNAL_PHRASES:
                continue
            counts[phrase] += 1
    return counts


def build_phrase_signals(
    current_text: str,
    historical_texts: Iterable[str],
    top_n: int = 20,
) -> List[PhraseSignal]:
    historical_counts: Counter = Counter()
    for historical_text in historical_texts:
        historical_counts.update(_extract_candidate_ngrams(historical_text))

    current_counts = _extract_candidate_ngrams(current_text)
    ranked = []
    for phrase, current_count in current_counts.items():
        historical_count = historical_counts.get(phrase, 0)
        rarity = current_count / (historical_count + 1)
        rarity *= math.log(current_count + 1.5)
        if phrase in LOW_SIGNAL_PHRASES:
            continue
        ranked.append((rarity, phrase, current_count, historical_count))

    ranked.sort(key=lambda item: item[0], reverse=True)

    signals: List[PhraseSignal] = []
    for rarity, phrase, current_count, historical_count in ranked[:top_n]:
        normalized = _normalize_phrase(phrase)
        signals.append(
            PhraseSignal(
                phrase_text=phrase,
                normalized_phrase=normalized,
                semantic_key=_semantic_key(normalized),
                current_count=current_count,
                historical_count=historical_count,
                rarity_score=round(rarity, 4),
                examples=[phrase],
            )
        )
    return signals
