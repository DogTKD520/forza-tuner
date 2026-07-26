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
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlmodel import Session

from app.analysis.base import SetupSnapshot, BoundValue as BaseBoundValue
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



class BoundValue(BaseModel):
    min: Optional[float] = None
    current: float
    max: Optional[float] = None

class SetupCreateRequest(BaseModel):
    vehicle_id: Optional[int] = None
    name: str
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
    front_weight_pct: BoundValue
    aero_front: BoundValue
    aero_rear: BoundValue
    tire_compound: str = "Sport"
    lock_tire_compound: bool = False

    # Component tuneability flags
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
    final_drive: BoundValue
    gear_1: BoundValue
    gear_2: BoundValue
    gear_3: BoundValue
    gear_4: BoundValue
    gear_5: BoundValue
    gear_6: BoundValue
    gear_7: BoundValue
    gear_8: BoundValue
    gear_9: BoundValue
    gear_10: BoundValue

    # Alignment Extensions
    toe_front: BoundValue
    toe_rear: BoundValue
    caster_front: BoundValue

    # Ride Height
    ride_height_front: BoundValue
    ride_height_rear: BoundValue

    # Aero Extensions
    downforce_front: BoundValue
    downforce_rear: BoundValue

    # Brakes
    brake_balance: BoundValue
    brake_pressure: BoundValue

    # Differential Extensions
    diff_front_accel: BoundValue
    diff_front_decel: BoundValue
    diff_rear_accel: BoundValue
    diff_rear_decel: BoundValue
    diff_center_balance: BoundValue

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
    return {
        "game": request.app.state.active_game,
        "ollama_model": settings.ollama_model,
    }


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
        user_id="",
        name=body.name,
        pi_rating=body.pi_rating,
        hp=body.hp,
        weight_lbs=body.weight_lbs,
        tire_compound=body.tire_compound,
        lock_tire_compound=body.lock_tire_compound,
        tuneable_springs=body.tuneable_springs,
        tuneable_arbs=body.tuneable_arbs,
        tuneable_dampers=body.tuneable_dampers,
        tuneable_aero_front=body.tuneable_aero_front,
        tuneable_aero_rear=body.tuneable_aero_rear,
        suspension_type=body.suspension_type,
        diff_upgrade_type=body.diff_upgrade_type,
        drivetrain=body.drivetrain,
        tuning_goal=body.tuning_goal or "street_road",
    )
    setup.tunables = {
        "tire_pressure_front": body.tire_pressure_front.model_dump(),
        "tire_pressure_rear": body.tire_pressure_rear.model_dump(),
        "camber_front": body.camber_front.model_dump(),
        "camber_rear": body.camber_rear.model_dump(),
        "springs_front": body.springs_front.model_dump(),
        "springs_rear": body.springs_rear.model_dump(),
        "arb_front": body.arb_front.model_dump(),
        "arb_rear": body.arb_rear.model_dump(),
        "bump_front": body.bump_front.model_dump(),
        "bump_rear": body.bump_rear.model_dump(),
        "rebound_front": body.rebound_front.model_dump(),
        "rebound_rear": body.rebound_rear.model_dump(),
        "front_weight_pct": body.front_weight_pct.model_dump(),
        "aero_front": body.aero_front.model_dump(),
        "aero_rear": body.aero_rear.model_dump(),
        "final_drive": body.final_drive.model_dump(),
        "gear_1": body.gear_1.model_dump(),
        "gear_2": body.gear_2.model_dump(),
        "gear_3": body.gear_3.model_dump(),
        "gear_4": body.gear_4.model_dump(),
        "gear_5": body.gear_5.model_dump(),
        "gear_6": body.gear_6.model_dump(),
        "gear_7": body.gear_7.model_dump(),
        "gear_8": body.gear_8.model_dump(),
        "gear_9": body.gear_9.model_dump(),
        "gear_10": body.gear_10.model_dump(),
        "toe_front": body.toe_front.model_dump(),
        "toe_rear": body.toe_rear.model_dump(),
        "caster_front": body.caster_front.model_dump(),
        "ride_height_front": body.ride_height_front.model_dump(),
        "ride_height_rear": body.ride_height_rear.model_dump(),
        "downforce_front": body.downforce_front.model_dump(),
        "downforce_rear": body.downforce_rear.model_dump(),
        "brake_balance": body.brake_balance.model_dump(),
        "brake_pressure": body.brake_pressure.model_dump(),
        "diff_front_accel": body.diff_front_accel.model_dump(),
        "diff_front_decel": body.diff_front_decel.model_dump(),
        "diff_rear_accel": body.diff_rear_accel.model_dump(),
        "diff_rear_decel": body.diff_rear_decel.model_dump(),
        "diff_center_balance": body.diff_center_balance.model_dump(),
    }
    return repo.create_setup(setup)


@router.delete("/setups/{setup_id}", status_code=204)
async def delete_setup(setup_id: int, db: Annotated[Session, Depends(get_session)]):
    repo = VehicleSetupRepository(db)
    success = repo.delete_setup(setup_id)
    if not success:
        raise HTTPException(status_code=404, detail="Setup not found")
    return None


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
    if processor.is_recording or getattr(request.app.state, "active_session_id", None) is not None:
        raise HTTPException(status_code=409, detail="A recording session is already active")

    processor.start_recording()

    request.app.state.active_session_id = "pending"
    request.app.state.pending_session_setup_id = setup_id
    request.app.state.pending_session_started_at = datetime.now(timezone.utc)
    
    return {"session_id": "pending", "status": "recording"}


@router.post("/sessions/{session_id}/stop")
async def stop_session(
    session_id: str,
    request: Request,
):
    processor = request.app.state.processor
    active_session_id = getattr(request.app.state, "active_session_id", None)

    if not processor.is_recording:
        raise HTTPException(status_code=400, detail="No active recording session")
    
    if active_session_id != session_id:
        raise HTTPException(status_code=409, detail=f"Requested session_id {session_id} does not match active session {active_session_id}")

    summary = processor.stop_recording()
    request.app.state.active_session_id = None
    
    if summary.get("total_frames", 0) == 0:
        return {"status": "discarded", "message": "No data recorded"}

    started_at = getattr(request.app.state, "pending_session_started_at", datetime.now(timezone.utc))
    ended_at = datetime.now(timezone.utc)
    duration_seconds = (ended_at - started_at).total_seconds()
    
    telemetry_session = TelemetrySession(
        user_id="",
        vehicle_setup_id=getattr(request.app.state, "pending_session_setup_id", None),
        game_type=request.app.state.active_game,
        status="completed",
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration_seconds,
    )
    telemetry_session.summary_metrics = summary
    
    request.app.state.pending_session = telemetry_session

    return {"session_id": "pending", "status": "completed", "summary": summary}


@router.post("/sessions/current/save", status_code=201)
async def save_current_session(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
):
    pending_session = getattr(request.app.state, "pending_session", None)
    if not pending_session:
        raise HTTPException(status_code=400, detail="No pending session to save")
        
    session_repo = TelemetrySessionRepository(db)
    created = session_repo.create_session(pending_session)
    request.app.state.pending_session = None
    return {"session_id": created.id, "status": "saved"}


@router.post("/sessions/current/clear")
async def clear_current_session(
    request: Request,
):
    request.app.state.pending_session = None
    return {"status": "cleared"}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: int, db: Annotated[Session, Depends(get_session)]):
    repo = TelemetrySessionRepository(db)
    success = repo.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return None


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

    tunables = db_setup.tunables

    def _to_bound(data: dict) -> "BaseBoundValue":
        """Convert a tunables dict entry to a dataclass BoundValue."""
        return BaseBoundValue(
            min=data.get("min"),
            current=data.get("current", 0.0),
            max=data.get("max"),
        )

    setup_snapshot = SetupSnapshot(
        pi_rating=getattr(db_setup, "pi_rating", 700),
        hp=getattr(db_setup, "hp", 400),
        weight_lbs=getattr(db_setup, "weight_lbs", 3000.0),
        tire_compound=getattr(db_setup, "tire_compound", "Sport"),
        lock_tire_compound=getattr(db_setup, "lock_tire_compound", False),
        tuneable_springs=getattr(db_setup, "tuneable_springs", True),
        tuneable_arbs=getattr(db_setup, "tuneable_arbs", True),
        tuneable_dampers=getattr(db_setup, "tuneable_dampers", True),
        tuneable_aero_front=getattr(db_setup, "tuneable_aero_front", True),
        tuneable_aero_rear=getattr(db_setup, "tuneable_aero_rear", True),
        suspension_type=getattr(db_setup, "suspension_type", "Race"),
        diff_upgrade_type=getattr(db_setup, "diff_upgrade_type", "Race"),
        drivetrain=getattr(db_setup, "drivetrain", "AWD"),
        tuning_goal=active_goal,
        tire_pressure_front=_to_bound(tunables.get("tire_pressure_front", {"current": 0.0})),
        tire_pressure_rear=_to_bound(tunables.get("tire_pressure_rear", {"current": 0.0})),
        camber_front=_to_bound(tunables.get("camber_front", {"current": 0.0})),
        camber_rear=_to_bound(tunables.get("camber_rear", {"current": 0.0})),
        springs_front=_to_bound(tunables.get("springs_front", {"current": 0.0})),
        springs_rear=_to_bound(tunables.get("springs_rear", {"current": 0.0})),
        arb_front=_to_bound(tunables.get("arb_front", {"current": 0.0})),
        arb_rear=_to_bound(tunables.get("arb_rear", {"current": 0.0})),
        bump_front=_to_bound(tunables.get("bump_front", {"current": 0.0})),
        bump_rear=_to_bound(tunables.get("bump_rear", {"current": 0.0})),
        rebound_front=_to_bound(tunables.get("rebound_front", {"current": 0.0})),
        rebound_rear=_to_bound(tunables.get("rebound_rear", {"current": 0.0})),
        front_weight_pct=_to_bound(tunables.get("front_weight_pct", {"current": 52.0})),
        downforce_front=_to_bound(tunables.get("aero_front", tunables.get("downforce_front", {"current": 100.0}))),
        downforce_rear=_to_bound(tunables.get("aero_rear", tunables.get("downforce_rear", {"current": 150.0}))),
        final_drive=_to_bound(tunables.get("final_drive", {"current": 3.50})),
        gear_1=_to_bound(tunables.get("gear_1", {"current": 2.89})),
        gear_2=_to_bound(tunables.get("gear_2", {"current": 1.99})),
        gear_3=_to_bound(tunables.get("gear_3", {"current": 1.49})),
        gear_4=_to_bound(tunables.get("gear_4", {"current": 1.16})),
        gear_5=_to_bound(tunables.get("gear_5", {"current": 0.94})),
        gear_6=_to_bound(tunables.get("gear_6", {"current": 0.78})),
        gear_7=_to_bound(tunables.get("gear_7", {"current": 0.55})),
        gear_8=_to_bound(tunables.get("gear_8", {"current": 0.55})),
        gear_9=_to_bound(tunables.get("gear_9", {"current": 0.48})),
        gear_10=_to_bound(tunables.get("gear_10", {"current": 0.42})),
        toe_front=_to_bound(tunables.get("toe_front", {"current": 0.0})),
        toe_rear=_to_bound(tunables.get("toe_rear", {"current": 0.0})),
        caster_front=_to_bound(tunables.get("caster_front", {"current": 5.0})),
        ride_height_front=_to_bound(tunables.get("ride_height_front", {"current": 5.0})),
        ride_height_rear=_to_bound(tunables.get("ride_height_rear", {"current": 5.0})),
        brake_balance=_to_bound(tunables.get("brake_balance", {"current": 50.0})),
        brake_pressure=_to_bound(tunables.get("brake_pressure", {"current": 100.0})),
        diff_front_accel=_to_bound(tunables.get("diff_front_accel", {"current": 25.0})),
        diff_front_decel=_to_bound(tunables.get("diff_front_decel", {"current": 0.0})),
        diff_rear_accel=_to_bound(tunables.get("diff_rear_accel", {"current": 50.0})),
        diff_rear_decel=_to_bound(tunables.get("diff_rear_decel", {"current": 15.0})),
        diff_center_balance=_to_bound(tunables.get("diff_center_balance", {"current": 65.0})),
    )
    use_llm = body.use_llm

    if use_llm:
        # Enqueue for sequential GPU processing
        queue = request.app.state.analysis_queue
        task_id = await queue.enqueue(session_metrics, setup_snapshot, use_llm=True)
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
        recommendation.input_setup_json = json.dumps(jsonable_encoder(setup_snapshot))
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
        known_ids = list(queue._tasks.keys())
        logger.warning(
            "Task %s not found. Known task IDs: %s", task_id, known_ids
        )
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
