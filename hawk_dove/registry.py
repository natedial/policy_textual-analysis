"""Scorer registry for swappable hawk–dove methodologies."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List

from hawk_dove.scoring import (
    AnthropicHawkDoveScorer,
    BaseHawkDoveScorer,
    HeuristicHawkDoveScorer,
    default_scorer,
)

METHOD_HEURISTIC = "heuristic"
METHOD_ANTHROPIC = "anthropic"
METHOD_ROBERTA = "roberta"

KNOWN_METHODS = (METHOD_HEURISTIC, METHOD_ANTHROPIC, METHOD_ROBERTA)


def _build_roberta() -> BaseHawkDoveScorer:
    from hawk_dove.roberta import RobertaHawkDoveScorer

    return RobertaHawkDoveScorer()


_FACTORIES: Dict[str, Callable[[], BaseHawkDoveScorer]] = {
    METHOD_HEURISTIC: HeuristicHawkDoveScorer,
    METHOD_ANTHROPIC: AnthropicHawkDoveScorer,
    METHOD_ROBERTA: _build_roberta,
}


def list_methods() -> List[str]:
    return list(KNOWN_METHODS)


def get_scorer(method: str | None = None) -> BaseHawkDoveScorer:
    if method is None or method == "default":
        return default_scorer()
    key = method.strip().lower()
    if key not in _FACTORIES:
        raise ValueError(f"Unknown scoring method '{method}'. Choose from: {', '.join(KNOWN_METHODS)}")
    return _FACTORIES[key]()


def get_scorers(methods: Iterable[str]) -> Dict[str, BaseHawkDoveScorer]:
    return {method.strip().lower(): get_scorer(method) for method in methods}
