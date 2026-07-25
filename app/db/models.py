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

    # Vehicle specs & parameters
    pi_rating: int = Field(default=700)
    hp: int = Field(default=400)
    weight_lbs: float = Field(default=3000.0)

    # Component tuneability flags (installed upgrades)
    tuneable_springs: bool = Field(default=True)
    tuneable_arbs: bool = Field(default=True)
    tuneable_dampers: bool = Field(default=True)
    tuneable_aero_front: bool = Field(default=True)
    tuneable_aero_rear: bool = Field(default=True)
    suspension_type: str = Field(default="Race")
    diff_upgrade_type: str = Field(default="Race")
    tire_compound: str = Field(default="Sport")
    lock_tire_compound: bool = Field(default=False)
    drivetrain: str = Field(default="AWD")

    # Discipline / Goal
    tuning_goal: str = Field(default="street_road")

    # JSON blob of all tunable sliders and bounded values
    tunables_json: str = Field(default="{}")

    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def tunables(self) -> dict:
        return json.loads(self.tunables_json)

    @tunables.setter
    def tunables(self, value: dict) -> None:
        self.tunables_json = json.dumps(value)


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
