"""
Strategy interface for the analysis engine.

Any new analysis backend (math, LLM, remote ML service…) implements
`AnalysisStrategy` and can be swapped in at runtime via the USE_LLM toggle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class BoundValue:
    min: Optional[float]
    current: float
    max: Optional[float]


@dataclass
class SetupSnapshot:
    """Current in-game vehicle setup passed to the analyser."""
    tire_pressure_front: BoundValue
    tire_pressure_rear: BoundValue
    camber_front: BoundValue
    camber_rear: BoundValue
    springs_front: BoundValue
    springs_rear: BoundValue
    arb_front: BoundValue
    arb_rear: BoundValue
    bump_front: BoundValue
    bump_rear: BoundValue
    rebound_front: BoundValue
    rebound_rear: BoundValue

    # Vehicle specs & parameters
    pi_rating: int = 700
    hp: int = 400
    weight_lbs: float = 3000.0
    tire_compound: str = "Sport"
    lock_tire_compound: bool = False

    # Component tuneability flags (installed upgrades)
    tuneable_springs: bool = True
    tuneable_arbs: bool = True
    tuneable_dampers: bool = True
    tuneable_aero_front: bool = True
    tuneable_aero_rear: bool = True
    suspension_type: str = "Race"
    diff_upgrade_type: str = "Race"

    # Drivetrain
    drivetrain: str = "AWD"
    
    # Gearing
    final_drive: BoundValue = field(default_factory=lambda: BoundValue(None, 3.50, None))
    gear_1: BoundValue = field(default_factory=lambda: BoundValue(None, 2.89, None))
    gear_2: BoundValue = field(default_factory=lambda: BoundValue(None, 1.99, None))
    gear_3: BoundValue = field(default_factory=lambda: BoundValue(None, 1.49, None))
    gear_4: BoundValue = field(default_factory=lambda: BoundValue(None, 1.16, None))
    gear_5: BoundValue = field(default_factory=lambda: BoundValue(None, 0.94, None))
    gear_6: BoundValue = field(default_factory=lambda: BoundValue(None, 0.78, None))
    gear_7: BoundValue = field(default_factory=lambda: BoundValue(None, 0.65, None))
    gear_8: BoundValue = field(default_factory=lambda: BoundValue(None, 0.55, None))
    gear_9: BoundValue = field(default_factory=lambda: BoundValue(None, 0.48, None))
    gear_10: BoundValue = field(default_factory=lambda: BoundValue(None, 0.42, None))

    # Alignment Extensions
    toe_front: BoundValue = field(default_factory=lambda: BoundValue(None, 0.0, None))
    toe_rear: BoundValue = field(default_factory=lambda: BoundValue(None, 0.0, None))
    caster_front: BoundValue = field(default_factory=lambda: BoundValue(None, 5.0, None))

    # Ride Height
    ride_height_front: BoundValue = field(default_factory=lambda: BoundValue(None, 5.0, None))
    ride_height_rear: BoundValue = field(default_factory=lambda: BoundValue(None, 5.0, None))

    # Aero Extensions
    downforce_front: BoundValue = field(default_factory=lambda: BoundValue(None, 100.0, None))
    downforce_rear: BoundValue = field(default_factory=lambda: BoundValue(None, 150.0, None))

    # Brakes
    brake_balance: BoundValue = field(default_factory=lambda: BoundValue(None, 50.0, None))
    brake_pressure: BoundValue = field(default_factory=lambda: BoundValue(None, 100.0, None))

    # Differential Extensions
    diff_front_accel: BoundValue = field(default_factory=lambda: BoundValue(None, 25.0, None))
    diff_front_decel: BoundValue = field(default_factory=lambda: BoundValue(None, 0.0, None))
    diff_rear_accel: BoundValue = field(default_factory=lambda: BoundValue(None, 50.0, None))
    diff_rear_decel: BoundValue = field(default_factory=lambda: BoundValue(None, 15.0, None))
    diff_center_balance: BoundValue = field(default_factory=lambda: BoundValue(None, 65.0, None))
    front_weight_pct: BoundValue = field(default_factory=lambda: BoundValue(None, 52.0, None))

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
