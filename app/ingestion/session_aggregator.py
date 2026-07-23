"""
Session aggregator — accumulates per-frame telemetry into rolling statistics
that the analysis engine can reason about.

Keeps everything in memory during a session.  At session-end, `get_summary()`
returns a plain dict that is persisted to SQLite as a JSON blob.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.ingestion.parser import TelemetryFrame


@dataclass
class _CornerStats:
    """Rolling accumulator for a single tyre corner."""
    inner_temps: list[float] = field(default_factory=list)
    center_temps: list[float] = field(default_factory=list)
    outer_temps: list[float] = field(default_factory=list)
    suspension_samples: list[float] = field(default_factory=list)
    bottom_out_count: int = 0      # frames where travel >= 0.95
    total_frames: int = 0


class SessionAggregator:
    """
    Accumulates `TelemetryFrame` objects during a recording session and
    provides a summary dict suitable for passing to the analysis engine.

    Thread-safety: designed for single async task use — no locking needed.
    """

    BOTTOM_OUT_THRESHOLD = 0.95
    CORNERS = ["fl", "fr", "rl", "rr"]

    def __init__(self) -> None:
        self._corners: dict[str, _CornerStats] = {
            c: _CornerStats() for c in self.CORNERS
        }
        self._lateral_g_samples: list[float] = []
        self._speed_samples: list[float] = []
        self._frame_count: int = 0
        self._latest_frame: TelemetryFrame | None = None

    # ------------------------------------------------------------------
    # Accumulation
    # ------------------------------------------------------------------

    def ingest(self, frame: TelemetryFrame) -> None:
        """Feed one parsed frame into the running statistics."""
        self._frame_count += 1
        self._latest_frame = frame
        self._speed_samples.append(frame.speed_mps)
        self._lateral_g_samples.append(abs(frame.accel_x))

        corner_data = [
            ("fl", frame.tire_temp_fl, frame.suspension_fl),
            ("fr", frame.tire_temp_fr, frame.suspension_fr),
            ("rl", frame.tire_temp_rl, frame.suspension_rl),
            ("rr", frame.tire_temp_rr, frame.suspension_rr),
        ]

        for corner_name, temps, suspension_travel in corner_data:
            stats = self._corners[corner_name]
            stats.inner_temps.append(temps[0])
            stats.center_temps.append(temps[1])
            stats.outer_temps.append(temps[2])
            stats.suspension_samples.append(suspension_travel)
            stats.total_frames += 1
            if suspension_travel >= self.BOTTOM_OUT_THRESHOLD:
                stats.bottom_out_count += 1

    # ------------------------------------------------------------------
    # Summary extraction
    # ------------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        """
        Return aggregated session metrics as a plain dict.

        Keys consumed by `MathBaselineAnalyzer`:
          - corners.<corner>.avg_inner_temp
          - corners.<corner>.avg_center_temp
          - corners.<corner>.avg_outer_temp
          - corners.<corner>.avg_suspension_travel
          - corners.<corner>.bottom_out_ratio   (0.0–1.0)
          - front_avg_suspension_travel
          - rear_avg_suspension_travel
          - total_frames
        """
        summary: dict[str, Any] = {
            "total_frames": self._frame_count,
            "avg_speed_mps": _safe_mean(self._speed_samples),
            "avg_lateral_g": _safe_mean(self._lateral_g_samples),
            "corners": {},
        }

        for corner_name, stats in self._corners.items():
            if stats.total_frames == 0:
                continue
            summary["corners"][corner_name] = {
                "avg_inner_temp": _safe_mean(stats.inner_temps),
                "avg_center_temp": _safe_mean(stats.center_temps),
                "avg_outer_temp": _safe_mean(stats.outer_temps),
                "avg_suspension_travel": _safe_mean(stats.suspension_samples),
                "peak_suspension_travel": max(stats.suspension_samples, default=0.0),
                "bottom_out_ratio": (
                    stats.bottom_out_count / stats.total_frames
                    if stats.total_frames > 0
                    else 0.0
                ),
            }

        # Front vs rear average suspension travel (used for ARB balance calc)
        def _avg_travel(*corners: str) -> float:
            values = [
                summary["corners"][c]["avg_suspension_travel"]
                for c in corners
                if c in summary["corners"]
            ]
            return _safe_mean(values)

        summary["front_avg_suspension_travel"] = _avg_travel("fl", "fr")
        summary["rear_avg_suspension_travel"] = _avg_travel("rl", "rr")

        return summary

    def get_latest_frame_dict(self) -> dict[str, Any] | None:
        """Return the most recently ingested frame as a JSON-serialisable dict."""
        if self._latest_frame is None:
            return None
        f = self._latest_frame
        return {
            "speed_kph": round(f.speed_mps * 3.6, 1),
            "boost": round(f.boost, 2),
            "throttle": round(f.throttle, 2),
            "brake": round(f.brake, 2),
            "steer": round(f.steer, 2),
            "tire_temp": {
                "fl": f.tire_temp_fl,
                "fr": f.tire_temp_fr,
                "rl": f.tire_temp_rl,
                "rr": f.tire_temp_rr,
            },
            "suspension": {
                "fl": round(f.suspension_fl, 3),
                "fr": round(f.suspension_fr, 3),
                "rl": round(f.suspension_rl, 3),
                "rr": round(f.suspension_rr, 3),
            },
            "game_type": f.game_type,
        }

    def reset(self) -> None:
        """Clear all accumulated data to start a fresh session."""
        self.__init__()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
