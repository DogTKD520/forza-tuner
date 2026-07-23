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

    # Vehicle specs & parameters
    pi_rating: int = 700
    hp: int = 400
    weight_lbs: float = 3000.0
    front_weight_pct: float = 52.0
    aero_front: float = 100.0
    aero_rear: float = 150.0
    tire_compound: str = "Sport"
    lock_tire_compound: bool = False

    # Component tuneability flags (installed upgrades)
    tuneable_springs: bool = True
    tuneable_arbs: bool = True
    tuneable_dampers: bool = True
    tuneable_aero: bool = True
    tuneable_diff: bool = True

    # Goal / Discipline
    tuning_goal: str = "street_road"


@dataclass
class Adjustment:
    """A single recommended change to one tuning parameter or part upgrade."""
    parameter: str          # e.g. "tire_pressure_front" or "arb_upgrade"
    current_value: float | str
    recommended_value: float | str
    delta: float            # recommended_value - current_value (0.0 for qualitative upgrade suggestions)
    reason: str             # human-readable explanation
    is_upgrade_recommendation: bool = False
    pi_impact_warning: str | None = None



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
        tuning_goal: str = "street_road",
    ) -> TuningRecommendationResult:
        """
        Analyse `session_metrics` (produced by SessionAggregator.get_summary())
        against the current `setup` and return recommended adjustments.
        """
        ...
