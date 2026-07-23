"""
WebSocket endpoint for live telemetry streaming.

Connected browser clients receive throttled telemetry frame JSON at
WEBSOCKET_FPS (default 15 Hz) regardless of the 60 Hz UDP ingestion rate.
Multiple concurrent clients are supported via a shared broadcast set.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Shared set of connected WebSocket clients
_connected_clients: set[WebSocket] = set()


@router.websocket("/ws/telemetry")
async def telemetry_websocket(websocket: WebSocket):
    await websocket.accept()
    _connected_clients.add(websocket)
    logger.info(
        "WebSocket client connected. Total clients: %d", len(_connected_clients)
    )

    frame_interval = 1.0 / settings.websocket_fps

    try:
        while True:
            # Read latest frame from the processor shared on app state
            processor = websocket.app.state.processor
            frame = await processor.get_latest_frame()

            if frame:
                await websocket.send_text(json.dumps(frame))

            # Respect the throttle interval
            await asyncio.sleep(frame_interval)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        _connected_clients.discard(websocket)
