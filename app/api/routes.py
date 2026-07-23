"""
REST API routes.

All endpoints that mutate state accept an optional `user_id` query parameter.
In MVP mode this defaults to settings.default_user_id ("local_admin").
Adding SSO later is a matter of reading the identity header here and passing
it down to the repository layer.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from app.analysis.base import SetupSnapshot
from app.analysis.gpu_queue import TaskStatus
from app.analysis.math_analyzer import MathBaselineAnalyzer
from app.config import get_settings
from app.db.database import get_session
from app.db.models import TelemetrySession, TuningRecommendation, Vehicle, VehicleSetup
from app.db.repositories import (
    TuningRecommendationRepository,
    TelemetrySessionRepository,
    VehicleRepository,
    VehicleSetupRepository,
)

router = APIRouter(prefix="/api")
settings = get_settings()


# ---------------------------------------------------------------------------
# Request / Response schemas (Pydantic)
# ---------------------------------------------------------------------------

class GameProfileRequest(BaseModel):
    game: str   # "FM" | "FH"


class VehicleCreateRequest(BaseModel):
    make: str
    model: str
    year: int
    car_class: str
    pi: int


class SetupCreateRequest(BaseModel):
    vehicle_id: Optional[int] = None
    name: str
    tire_pressure_front: float
    tire_pressure_rear: float
    camber_front: float
    camber_rear: float
    springs_front: float
    springs_rear: float
    arb_front: float
    arb_rear: float
    bump_front: float = 5.0
    bump_rear: float = 5.0
    rebound_front: float = 5.0
    rebound_rear: float = 5.0

    # Vehicle specs & parameters
    pi_rating: int = 700
    hp: int = 400
    weight_lbs: float = 3000.0
    front_weight_pct: float = 52.0
    aero_front: float = 100.0
    aero_rear: float = 150.0
    tire_compound: str = "Sport"
    lock_tire_compound: bool = False

    # Component tuneability flags
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

    # Discipline / Goal
    tuning_goal: str = "street_road"



class AnalyzeRequest(BaseModel):
    session_id: int
    setup_id: int
    use_llm: bool = False
    tuning_goal: Optional[str] = None


# ---------------------------------------------------------------------------
# Game profile
# ---------------------------------------------------------------------------

@router.get("/game-profile")
async def get_game_profile(request: Request):
    return {"game": request.app.state.active_game}


@router.post("/game-profile")
async def set_game_profile(body: GameProfileRequest, request: Request):
    if body.game not in ("FM", "FH"):
        raise HTTPException(status_code=400, detail="game must be 'FM' or 'FH'")
    request.app.state.active_game = body.game
    return {"game": request.app.state.active_game}


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

@router.get("/vehicles")
async def list_vehicles(db: Annotated[Session, Depends(get_session)]):
    repo = VehicleRepository(db)
    return repo.list_vehicles()


@router.post("/vehicles", status_code=201)
async def create_vehicle(
    body: VehicleCreateRequest,
    db: Annotated[Session, Depends(get_session)],
):
    repo = VehicleRepository(db)
    vehicle = Vehicle(
        make=body.make,
        model=body.model,
        year=body.year,
        car_class=body.car_class,
        performance_index=body.pi,
        user_id="",   # set by repository
    )
    return repo.create_vehicle(vehicle)


# ---------------------------------------------------------------------------
# Vehicle Setups
# ---------------------------------------------------------------------------

@router.get("/setups")
async def list_setups(db: Annotated[Session, Depends(get_session)]):
    repo = VehicleSetupRepository(db)
    return repo.list_setups()


@router.get("/setups/{setup_id}")
async def get_setup(setup_id: int, db: Annotated[Session, Depends(get_session)]):
    repo = VehicleSetupRepository(db)
    setup = repo.get_setup(setup_id)
    if not setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    return setup


@router.post("/setups", status_code=201)
async def create_setup(
    body: SetupCreateRequest,
    db: Annotated[Session, Depends(get_session)],
):
    repo = VehicleSetupRepository(db)
    setup = VehicleSetup(
        vehicle_id=body.vehicle_id,
        user_id="",   # set by repository
        name=body.name,
        tire_pressure_front=body.tire_pressure_front,
        tire_pressure_rear=body.tire_pressure_rear,
        camber_front=body.camber_front,
        camber_rear=body.camber_rear,
        springs_front=body.springs_front,
        springs_rear=body.springs_rear,
        arb_front=body.arb_front,
        arb_rear=body.arb_rear,
        bump_front=body.bump_front,
        bump_rear=body.bump_rear,
        rebound_front=body.rebound_front,
        rebound_rear=body.rebound_rear,
        pi_rating=body.pi_rating,
        hp=body.hp,
        weight_lbs=body.weight_lbs,
        front_weight_pct=body.front_weight_pct,
        aero_front=body.aero_front,
        aero_rear=body.aero_rear,
        tire_compound=body.tire_compound,
        lock_tire_compound=body.lock_tire_compound,
        tuneable_springs=body.tuneable_springs,
        tuneable_arbs=body.tuneable_arbs,
        tuneable_dampers=body.tuneable_dampers,
        tuneable_aero_front=body.tuneable_aero_front,
        tuneable_aero_rear=body.tuneable_aero_rear,
        diff_upgrade_type=body.diff_upgrade_type,
        drivetrain=body.drivetrain,
        final_drive=body.final_drive,
        gear_1=body.gear_1,
        gear_2=body.gear_2,
        gear_3=body.gear_3,
        gear_4=body.gear_4,
        gear_5=body.gear_5,
        gear_6=body.gear_6,
        gear_7=body.gear_7,
        gear_8=body.gear_8,
        gear_9=body.gear_9,
        gear_10=body.gear_10,
        toe_front=body.toe_front,
        toe_rear=body.toe_rear,
        caster_front=body.caster_front,
        ride_height_front=body.ride_height_front,
        ride_height_rear=body.ride_height_rear,
        downforce_front=body.downforce_front,
        downforce_rear=body.downforce_rear,
        brake_balance=body.brake_balance,
        brake_pressure=body.brake_pressure,
        diff_front_accel=body.diff_front_accel,
        diff_front_decel=body.diff_front_decel,
        diff_rear_accel=body.diff_rear_accel,
        diff_rear_decel=body.diff_rear_decel,
        diff_center_balance=body.diff_center_balance,
        tuning_goal=body.tuning_goal or "street_road",
    )
    return repo.create_setup(setup)


# ---------------------------------------------------------------------------
# Telemetry Sessions
# ---------------------------------------------------------------------------

@router.get("/sessions")
async def list_sessions(db: Annotated[Session, Depends(get_session)]):
    repo = TelemetrySessionRepository(db)
    return repo.list_sessions()


@router.post("/sessions/start", status_code=201)
async def start_session(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    setup_id: Optional[int] = None,
):
    processor = request.app.state.processor
    processor.start_recording()

    session_repo = TelemetrySessionRepository(db)
    telemetry_session = TelemetrySession(
        user_id="",
        vehicle_setup_id=setup_id,
        game_type=request.app.state.active_game,
        status="recording",
    )
    created = session_repo.create_session(telemetry_session)
    request.app.state.active_session_id = created.id
    return {"session_id": created.id, "status": "recording"}


@router.post("/sessions/stop")
async def stop_session(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
):
    processor = request.app.state.processor
    if not processor.is_recording:
        raise HTTPException(status_code=400, detail="No active recording session")

    summary = processor.stop_recording()

    session_repo = TelemetrySessionRepository(db)
    session_id = request.app.state.active_session_id
    telemetry_session = session_repo.get_session(session_id)
    if telemetry_session:
        telemetry_session.status = "completed"
        telemetry_session.ended_at = datetime.now(timezone.utc)
        if telemetry_session.started_at:
            telemetry_session.duration_seconds = (telemetry_session.ended_at - telemetry_session.started_at).total_seconds()
        else:
            telemetry_session.duration_seconds = 0.0
        telemetry_session.summary_metrics = summary
        session_repo.update_session(telemetry_session)

    return {"session_id": session_id, "status": "completed", "summary": summary}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@router.post("/analyze")
async def analyze_session(
    body: AnalyzeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
):
    # Fetch session and validate it belongs to this user
    session_repo = TelemetrySessionRepository(db)
    telemetry_session = session_repo.get_session(body.session_id)
    if not telemetry_session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_metrics = telemetry_session.summary_metrics
    if not session_metrics:
        raise HTTPException(
            status_code=422,
            detail="Session has no recorded metrics. Record a session first.",
        )

    # Fetch setup
    setup_repo = VehicleSetupRepository(db)
    db_setup = setup_repo.get_setup(body.setup_id)
    if not db_setup:
        raise HTTPException(status_code=404, detail="Setup not found")

    active_goal = body.tuning_goal or getattr(db_setup, "tuning_goal", "street_road")
    telemetry_session.tuning_goal = active_goal
    session_repo.update_session(telemetry_session)

    setup_snapshot = SetupSnapshot(
        tire_pressure_front=db_setup.tire_pressure_front,
        tire_pressure_rear=db_setup.tire_pressure_rear,
        camber_front=db_setup.camber_front,
        camber_rear=db_setup.camber_rear,
        springs_front=db_setup.springs_front,
        springs_rear=db_setup.springs_rear,
        arb_front=db_setup.arb_front,
        arb_rear=db_setup.arb_rear,
        bump_front=db_setup.bump_front,
        bump_rear=db_setup.bump_rear,
        rebound_front=db_setup.rebound_front,
        rebound_rear=db_setup.rebound_rear,
        pi_rating=getattr(db_setup, "pi_rating", 700),
        hp=getattr(db_setup, "hp", 400),
        weight_lbs=getattr(db_setup, "weight_lbs", 3000.0),
        front_weight_pct=getattr(db_setup, "front_weight_pct", 52.0),
        aero_front=getattr(db_setup, "aero_front", 100.0),
        aero_rear=getattr(db_setup, "aero_rear", 150.0),
        tire_compound=getattr(db_setup, "tire_compound", "Sport"),
        lock_tire_compound=getattr(db_setup, "lock_tire_compound", False),
        tuneable_springs=getattr(db_setup, "tuneable_springs", True),
        tuneable_arbs=getattr(db_setup, "tuneable_arbs", True),
        tuneable_dampers=getattr(db_setup, "tuneable_dampers", True),
        tuneable_aero_front=getattr(db_setup, "tuneable_aero_front", True),
        tuneable_aero_rear=getattr(db_setup, "tuneable_aero_rear", True),
        diff_upgrade_type=getattr(db_setup, "diff_upgrade_type", "Race"),
        drivetrain=getattr(db_setup, "drivetrain", "AWD"),
        final_drive=getattr(db_setup, "final_drive", 3.50),
        gear_1=getattr(db_setup, "gear_1", 2.89),
        gear_2=getattr(db_setup, "gear_2", 1.99),
        gear_3=getattr(db_setup, "gear_3", 1.49),
        gear_4=getattr(db_setup, "gear_4", 1.16),
        gear_5=getattr(db_setup, "gear_5", 0.94),
        gear_6=getattr(db_setup, "gear_6", 0.78),
        gear_7=getattr(db_setup, "gear_7", 0.65),
        gear_8=getattr(db_setup, "gear_8", 0.55),
        gear_9=getattr(db_setup, "gear_9", 0.48),
        gear_10=getattr(db_setup, "gear_10", 0.42),
        toe_front=getattr(db_setup, "toe_front", 0.0),
        toe_rear=getattr(db_setup, "toe_rear", 0.0),
        caster_front=getattr(db_setup, "caster_front", 5.0),
        ride_height_front=getattr(db_setup, "ride_height_front", 5.0),
        ride_height_rear=getattr(db_setup, "ride_height_rear", 5.0),
        downforce_front=getattr(db_setup, "downforce_front", 100.0),
        downforce_rear=getattr(db_setup, "downforce_rear", 150.0),
        brake_balance=getattr(db_setup, "brake_balance", 50.0),
        brake_pressure=getattr(db_setup, "brake_pressure", 100.0),
        diff_front_accel=getattr(db_setup, "diff_front_accel", 25.0),
        diff_front_decel=getattr(db_setup, "diff_front_decel", 0.0),
        diff_rear_accel=getattr(db_setup, "diff_rear_accel", 50.0),
        diff_rear_decel=getattr(db_setup, "diff_rear_decel", 15.0),
        diff_center_balance=getattr(db_setup, "diff_center_balance", 65.0),
        tuning_goal=active_goal,
    )

    use_llm = body.use_llm and settings.use_llm

    if use_llm:
        # Enqueue for sequential GPU processing
        queue = request.app.state.analysis_queue
        task_id = await queue.enqueue(session_metrics, setup_snapshot)
        return {"mode": "llm", "task_id": task_id, "status": TaskStatus.QUEUED, "tuning_goal": active_goal}
    else:
        # Math analyzer — instant synchronous response
        analyzer = MathBaselineAnalyzer()
        result = await analyzer.analyze(session_metrics, setup_snapshot, tuning_goal=active_goal)

        # Persist recommendation
        rec_repo = TuningRecommendationRepository(db)
        recommendation = TuningRecommendation(
            session_id=body.session_id,
            user_id="",
            analyzer_type=result.analyzer_type,
        )
        recommendation.recommendations = {
            "summary": result.summary,
            "adjustments": [adj.__dict__ for adj in result.adjustments],
        }
        recommendation.input_setup_json = json.dumps(setup_snapshot.__dict__)
        rec_repo.create_recommendation(recommendation)

        return {
            "mode": "math",
            "analyzer_type": result.analyzer_type,
            "tuning_goal": active_goal,
            "summary": result.summary,
            "adjustments": [adj.__dict__ for adj in result.adjustments],
        }


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, request: Request):
    queue = request.app.state.analysis_queue
    task = queue.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    response = {"task_id": task_id, "status": task.status}
    if task.result:
        response["result"] = {
            "summary": task.result.summary,
            "adjustments": [adj.__dict__ for adj in task.result.adjustments],
        }
    if task.error:
        response["error"] = task.error
    return response
