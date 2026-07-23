"""
Data-access repository layer.

Every public method scopes queries and inserts to `user_id`.  In the MVP that
value always comes from settings.default_user_id ("local_admin").  To add
multi-tenancy later, pass the identity-header value instead — no SQL changes
are needed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.config import get_settings
from app.db.models import (
    TelemetrySession,
    TuningRecommendation,
    Vehicle,
    VehicleSetup,
)

settings = get_settings()


def _default_user_id() -> str:
    """Return the active user identity (MVP: always local_admin)."""
    return settings.default_user_id


# ---------------------------------------------------------------------------
# Vehicle repository
# ---------------------------------------------------------------------------

class VehicleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_vehicles(self, user_id: Optional[str] = None) -> list[Vehicle]:
        uid = user_id or _default_user_id()
        return list(
            self._session.exec(select(Vehicle).where(Vehicle.user_id == uid)).all()
        )

    def get_vehicle(self, vehicle_id: int, user_id: Optional[str] = None) -> Optional[Vehicle]:
        uid = user_id or _default_user_id()
        return self._session.exec(
            select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.user_id == uid)
        ).first()

    def create_vehicle(self, vehicle: Vehicle, user_id: Optional[str] = None) -> Vehicle:
        vehicle.user_id = user_id or _default_user_id()
        self._session.add(vehicle)
        self._session.commit()
        self._session.refresh(vehicle)
        return vehicle


# ---------------------------------------------------------------------------
# VehicleSetup repository
# ---------------------------------------------------------------------------

class VehicleSetupRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_setups(self, user_id: Optional[str] = None) -> list[VehicleSetup]:
        uid = user_id or _default_user_id()
        return list(
            self._session.exec(
                select(VehicleSetup).where(VehicleSetup.user_id == uid)
            ).all()
        )

    def get_setup(self, setup_id: int, user_id: Optional[str] = None) -> Optional[VehicleSetup]:
        uid = user_id or _default_user_id()
        return self._session.exec(
            select(VehicleSetup).where(
                VehicleSetup.id == setup_id, VehicleSetup.user_id == uid
            )
        ).first()

    def create_setup(self, setup: VehicleSetup, user_id: Optional[str] = None) -> VehicleSetup:
        setup.user_id = user_id or _default_user_id()
        self._session.add(setup)
        self._session.commit()
        self._session.refresh(setup)
        return setup

    def update_setup(self, setup: VehicleSetup) -> VehicleSetup:
        self._session.add(setup)
        self._session.commit()
        self._session.refresh(setup)
        return setup


# ---------------------------------------------------------------------------
# TelemetrySession repository
# ---------------------------------------------------------------------------

class TelemetrySessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_sessions(self, user_id: Optional[str] = None) -> list[TelemetrySession]:
        uid = user_id or _default_user_id()
        return list(
            self._session.exec(
                select(TelemetrySession).where(TelemetrySession.user_id == uid)
            ).all()
        )

    def get_session(
        self, session_id: int, user_id: Optional[str] = None
    ) -> Optional[TelemetrySession]:
        uid = user_id or _default_user_id()
        return self._session.exec(
            select(TelemetrySession).where(
                TelemetrySession.id == session_id, TelemetrySession.user_id == uid
            )
        ).first()

    def create_session(
        self, telemetry_session: TelemetrySession, user_id: Optional[str] = None
    ) -> TelemetrySession:
        telemetry_session.user_id = user_id or _default_user_id()
        self._session.add(telemetry_session)
        self._session.commit()
        self._session.refresh(telemetry_session)
        return telemetry_session

    def update_session(self, telemetry_session: TelemetrySession) -> TelemetrySession:
        self._session.add(telemetry_session)
        self._session.commit()
        self._session.refresh(telemetry_session)
        return telemetry_session


# ---------------------------------------------------------------------------
# TuningRecommendation repository
# ---------------------------------------------------------------------------

class TuningRecommendationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_recommendations(
        self, session_id: int, user_id: Optional[str] = None
    ) -> list[TuningRecommendation]:
        uid = user_id or _default_user_id()
        return list(
            self._session.exec(
                select(TuningRecommendation).where(
                    TuningRecommendation.session_id == session_id,
                    TuningRecommendation.user_id == uid,
                )
            ).all()
        )

    def create_recommendation(
        self, recommendation: TuningRecommendation, user_id: Optional[str] = None
    ) -> TuningRecommendation:
        recommendation.user_id = user_id or _default_user_id()
        self._session.add(recommendation)
        self._session.commit()
        self._session.refresh(recommendation)
        return recommendation
