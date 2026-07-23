"""
SQLModel table definitions.

Every entity that belongs to a user carries a `user_id` column.  In the MVP
this defaults to "local_admin" via the repository layer.  When Cloudflare
Access (or any other SSO) is added later, the identity header value is dropped
in here without touching any other part of the code.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Vehicle
# ---------------------------------------------------------------------------

class Vehicle(SQLModel, table=True):
    __tablename__ = "vehicles"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    make: str
    model: str
    year: int
    car_class: str        # e.g. "S1", "A", "X"
    performance_index: int = Field(alias="pi")
    created_at: datetime = Field(default_factory=_utcnow)

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# VehicleSetup
# ---------------------------------------------------------------------------

class VehicleSetup(SQLModel, table=True):
    __tablename__ = "vehicle_setups"

    id: Optional[int] = Field(default=None, primary_key=True)
    vehicle_id: Optional[int] = Field(default=None, foreign_key="vehicles.id")
    user_id: str = Field(index=True)
    name: str

    # Tyres
    tire_pressure_front: float     # PSI
    tire_pressure_rear: float

    # Alignment
    camber_front: float            # degrees (negative = more camber)
    camber_rear: float

    # Springs (N/mm or game unit — we store whatever the game shows)
    springs_front: float
    springs_rear: float

    # Anti-roll bars (1–65 game scale)
    arb_front: float
    arb_rear: float

    # Dampers
    bump_front: float
    bump_rear: float
    rebound_front: float
    rebound_rear: float

    # Vehicle specs & parameters
    pi_rating: int = Field(default=700)
    hp: int = Field(default=400)
    weight_lbs: float = Field(default=3000.0)
    front_weight_pct: float = Field(default=52.0)
    aero_front: float = Field(default=100.0)
    aero_rear: float = Field(default=150.0)
    tire_compound: str = Field(default="Sport")
    lock_tire_compound: bool = Field(default=False)

    # Component tuneability flags (installed upgrades)
    tuneable_springs: bool = Field(default=True)
    tuneable_arbs: bool = Field(default=True)
    tuneable_dampers: bool = Field(default=True)
    tuneable_aero_front: bool = Field(default=True)
    tuneable_aero_rear: bool = Field(default=True)
    diff_upgrade_type: str = Field(default="Race")

    # Drivetrain
    drivetrain: str = Field(default="AWD")
    
    # Gearing
    final_drive: float = Field(default=3.50)
    gear_1: float = Field(default=2.89)
    gear_2: float = Field(default=1.99)
    gear_3: float = Field(default=1.49)
    gear_4: float = Field(default=1.16)
    gear_5: float = Field(default=0.94)
    gear_6: float = Field(default=0.78)
    gear_7: float = Field(default=0.65)
    gear_8: float = Field(default=0.55)
    gear_9: float = Field(default=0.48)
    gear_10: float = Field(default=0.42)

    # Alignment Extensions
    toe_front: float = Field(default=0.0)
    toe_rear: float = Field(default=0.0)
    caster_front: float = Field(default=5.0)

    # Ride Height
    ride_height_front: float = Field(default=5.0)
    ride_height_rear: float = Field(default=5.0)

    # Aero Extensions
    downforce_front: float = Field(default=100.0)
    downforce_rear: float = Field(default=150.0)

    # Brakes
    brake_balance: float = Field(default=50.0)
    brake_pressure: float = Field(default=100.0)

    # Differential Extensions
    diff_front_accel: float = Field(default=25.0)
    diff_front_decel: float = Field(default=0.0)
    diff_rear_accel: float = Field(default=50.0)
    diff_rear_decel: float = Field(default=15.0)
    diff_center_balance: float = Field(default=65.0)

    # Discipline / Goal
    tuning_goal: str = Field(default="street_road")

    created_at: datetime = Field(default_factory=_utcnow)



# ---------------------------------------------------------------------------
# TelemetrySession
# ---------------------------------------------------------------------------

class TelemetrySession(SQLModel, table=True):
    __tablename__ = "telemetry_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    vehicle_setup_id: Optional[int] = Field(default=None, foreign_key="vehicle_setups.id")
    game_type: str                # "FM" | "FH"
    status: str = "recording"    # "recording" | "completed" | "cancelled"
    tuning_goal: str = Field(default="street_road")
    duration_seconds: Optional[float] = None

    # JSON blob of aggregated metrics produced by SessionAggregator
    summary_metrics_json: Optional[str] = None

    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: Optional[datetime] = None

    @property
    def summary_metrics(self) -> Optional[dict]:
        if self.summary_metrics_json is None:
            return None
        return json.loads(self.summary_metrics_json)

    @summary_metrics.setter
    def summary_metrics(self, value: dict) -> None:
        self.summary_metrics_json = json.dumps(value)


# ---------------------------------------------------------------------------
# TuningRecommendation
# ---------------------------------------------------------------------------

class TuningRecommendation(SQLModel, table=True):
    __tablename__ = "tuning_recommendations"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="telemetry_sessions.id")
    user_id: str = Field(index=True)
    analyzer_type: str            # "math" | "ollama"

    # Snapshot of the setup that was analysed (JSON)
    input_setup_json: Optional[str] = None

    # Recommendation output (JSON dict of deltas and explanations)
    recommendations_json: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def recommendations(self) -> Optional[dict]:
        if self.recommendations_json is None:
            return None
        return json.loads(self.recommendations_json)

    @recommendations.setter
    def recommendations(self, value: dict) -> None:
        self.recommendations_json = json.dumps(value)
