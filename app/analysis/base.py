"""
Strategy interface for the analysis engine.

Any new analysis backend (math, LLM, remote ML service…) implements
`AnalysisStrategy` and can be swapped in at runtime via the USE_LLM toggle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SetupSnapshot:
    """Current in-game vehicle setup passed to the analyser."""
    tire_pressure_front: float
    tire_pressure_rear: float
    camber_front: float
    camber_rear: float
    springs_front: float
    springs_rear: float
    arb_front: float
    arb_rear: float
    bump_front: float
    bump_rear: float
    rebound_front: float
    rebound_rear: float


@dataclass
class Adjustment:
    """A single recommended change to one tuning parameter."""
    parameter: str          # e.g. "tire_pressure_front"
    current_value: float
    recommended_value: float
    delta: float            # recommended_value - current_value
    reason: str             # human-readable explanation


@dataclass
class TuningRecommendationResult:
    """Output produced by any AnalysisStrategy."""
    analyzer_type: str                          # "math" | "ollama"
    adjustments: list[Adjustment] = field(default_factory=list)
    summary: str = ""                           # free-text overview
    raw_output: dict[str, Any] = field(default_factory=dict)   # pass-through for LLM


class AnalysisStrategy(ABC):
    """
    Strategy interface.  Implement this to add a new analysis backend.
    `analyze` must be async to allow non-blocking LLM / HTTP calls.
    """

    @abstractmethod
    async def analyze(
        self,
        session_metrics: dict[str, Any],
        setup: SetupSnapshot,
    ) -> TuningRecommendationResult:
        """
        Analyse `session_metrics` (produced by SessionAggregator.get_summary())
        against the current `setup` and return recommended adjustments.
        """
        ...
