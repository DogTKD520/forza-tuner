"""
FastAPI application entry point.

Startup sequence:
  1. Create DB tables (idempotent).
  2. Ensure the default user record exists.
  3. Start the UDP telemetry listener.
  4. Start the analysis GPU queue worker (even if USE_LLM=False — it just sits idle).

All shared state is stored on `app.state` so routes and WebSocket handlers
can access it without globals.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.analysis.gpu_queue import AnalysisQueue
from app.analysis.math_analyzer import MathBaselineAnalyzer
from app.analysis.ollama_analyzer import OllamaAnalyzer
from app.api.routes import router as rest_router
from app.api.websocket import router as ws_router
from app.config import get_settings
from app.db.database import create_db_and_tables
from app.db.models import User
from app.ingestion.udp_listener import ForzaTelemetryProcessor, start_udp_listener
from sqlmodel import Session, select

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — startup then shutdown."""
    # --- Startup ---
    create_db_and_tables()
    _ensure_default_user()

    # Shared telemetry processor (parser + aggregator)
    processor = ForzaTelemetryProcessor()
    app.state.processor = processor
    app.state.active_game = settings.default_game
    app.state.active_session_id = None

    # UDP listener — hands raw bytes to processor
    transport, worker_task = await start_udp_listener(
        host=settings.udp_host,
        port=settings.udp_port,
        processor=processor,
        game_type_getter=lambda: app.state.active_game,
    )
    app.state.udp_transport = transport
    app.state.udp_worker_task = worker_task

    # Analysis strategy & queue
    strategy = OllamaAnalyzer() if settings.use_llm else MathBaselineAnalyzer()
    queue = AnalysisQueue(strategy)
    await queue.start()
    app.state.analysis_queue = queue

    logger.info(
        "Forza Tuner started | game=%s | udp=%s:%d | llm=%s",
        settings.default_game,
        settings.udp_host,
        settings.udp_port,
        settings.use_llm,
    )

    yield   # hand control to FastAPI

    # --- Shutdown ---
    transport.close()
    worker_task.cancel()
    await queue.stop()
    logger.info("Forza Tuner shut down cleanly.")


def _ensure_default_user() -> None:
    """Create the local_admin user row if it does not already exist."""
    from app.db.database import engine
    with Session(engine) as db:
        existing = db.exec(
            select(User).where(User.username == settings.default_user_id)
        ).first()
        if not existing:
            db.add(User(username=settings.default_user_id))
            db.commit()
            logger.info("Created default user: %s", settings.default_user_id)


app = FastAPI(
    title="Forza Tuner",
    description="Telemetry-driven tuning analysis for Forza Motorsport & Forza Horizon",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount REST and WebSocket routers
app.include_router(rest_router)
app.include_router(ws_router)

# Serve the frontend dashboard from /static, with index.html at /
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)

