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
    tuneable_aero_front: bool = True
    tuneable_aero_rear: bool = True
    diff_upgrade_type: str = "Race"

    # Drivetrain
    drivetrain: str = "AWD"
    
    # Gearing
    final_drive: float = 3.50
    gear_1: float = 2.89
    gear_2: float = 1.99
    gear_3: float = 1.49
    gear_4: float = 1.16
    gear_5: float = 0.94
    gear_6: float = 0.78
    gear_7: float = 0.65
    gear_8: float = 0.55
    gear_9: float = 0.48
    gear_10: float = 0.42

    # Alignment Extensions
    toe_front: float = 0.0
    toe_rear: float = 0.0
    caster_front: float = 5.0

    # Ride Height
    ride_height_front: float = 5.0
    ride_height_rear: float = 5.0

    # Aero Extensions
    downforce_front: float = 100.0
    downforce_rear: float = 150.0

    # Brakes
    brake_balance: float = 50.0
    brake_pressure: float = 100.0

    # Differential Extensions
    diff_front_accel: float = 25.0
    diff_front_decel: float = 0.0
    diff_rear_accel: float = 50.0
    diff_rear_decel: float = 15.0
    diff_center_balance: float = 65.0

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
