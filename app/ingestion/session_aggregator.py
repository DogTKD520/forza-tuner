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
from app.config import get_settings


@dataclass
class _CornerStats:
    """Rolling accumulator for a single tyre corner."""
    sum_temps: float = 0.0
    sum_slip_ratios: float = 0.0
    sum_slip_angles: float = 0.0
    sum_combined_slips: float = 0.0
    sum_suspension_samples: float = 0.0
    max_slip_angle: float = 0.0
    peak_suspension_travel: float = 0.0
    bottom_out_count: int = 0      # frames where travel >= threshold
    total_frames: int = 0


class SessionAggregator:
    """
    Accumulates `TelemetryFrame` objects during a recording session and
    provides a summary dict suitable for passing to the analysis engine.

    Thread-safety: designed for single async task use — no locking needed.
    """

    CORNERS = ["fl", "fr", "rl", "rr"]

    def __init__(self) -> None:
        self._corners: dict[str, _CornerStats] = {
            c: _CornerStats() for c in self.CORNERS
        }
        self._sum_lateral_g: float = 0.0
        self._sum_speed: float = 0.0
        self._frame_count: int = 0
        self._latest_frame: TelemetryFrame | None = None
        
        settings = get_settings()
        self._bottom_out_threshold = settings.tuning_rules.get(
            "spring_rate", {}).get("bottom_out_threshold", 0.95)

    # ------------------------------------------------------------------
    # Accumulation
    # ------------------------------------------------------------------

    def ingest(self, frame: TelemetryFrame) -> None:
        """Feed one parsed frame into the running statistics."""
        self._frame_count += 1
        self._latest_frame = frame
        self._sum_speed += frame.speed_mps
        self._sum_lateral_g += abs(frame.accel_x)

        corner_data = [
            ("fl", frame.tire_temp_fl, frame.suspension_fl, frame.tire_slip_ratio_fl, frame.tire_slip_angle_fl, frame.tire_combined_slip_fl),
            ("fr", frame.tire_temp_fr, frame.suspension_fr, frame.tire_slip_ratio_fr, frame.tire_slip_angle_fr, frame.tire_combined_slip_fr),
            ("rl", frame.tire_temp_rl, frame.suspension_rl, frame.tire_slip_ratio_rl, frame.tire_slip_angle_rl, frame.tire_combined_slip_rl),
            ("rr", frame.tire_temp_rr, frame.suspension_rr, frame.tire_slip_ratio_rr, frame.tire_slip_angle_rr, frame.tire_combined_slip_rr),
        ]

        for corner_name, temp, suspension, ratio, angle, combined in corner_data:
            stats = self._corners[corner_name]
            stats.sum_temps += temp
            stats.sum_slip_ratios += abs(ratio)
            stats.sum_slip_angles += abs(angle)
            stats.sum_combined_slips += abs(combined)
            stats.sum_suspension_samples += suspension
            stats.max_slip_angle = max(stats.max_slip_angle, abs(angle))
            stats.peak_suspension_travel = max(stats.peak_suspension_travel, suspension)
            stats.total_frames += 1
            if suspension >= self._bottom_out_threshold:
                stats.bottom_out_count += 1

    # ------------------------------------------------------------------
    # Summary extraction
    # ------------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        """
        Return aggregated session metrics as a plain dict.

        Keys consumed by `MathBaselineAnalyzer`:
          - corners.<corner>.avg_temp
          - corners.<corner>.avg_slip_ratio
          - corners.<corner>.avg_slip_angle
          - corners.<corner>.max_slip_angle
          - corners.<corner>.avg_combined_slip
          - corners.<corner>.avg_suspension_travel
          - corners.<corner>.bottom_out_ratio   (0.0–1.0)
          - front_avg_suspension_travel
          - rear_avg_suspension_travel
          - total_frames
        """
        avg_speed = self._sum_speed / self._frame_count if self._frame_count > 0 else 0.0
        avg_lat_g = self._sum_lateral_g / self._frame_count if self._frame_count > 0 else 0.0
        
        summary: dict[str, Any] = {
            "total_frames": self._frame_count,
            "avg_speed_mps": avg_speed,
            "avg_lateral_g": avg_lat_g,
            "game_type": self._latest_frame.game_type if self._latest_frame else "FH",
            "corners": {},
        }

        for corner_name, stats in self._corners.items():
            if stats.total_frames == 0:
                continue
            summary["corners"][corner_name] = {
                "avg_temp": stats.sum_temps / stats.total_frames,
                "avg_slip_ratio": stats.sum_slip_ratios / stats.total_frames,
                "avg_slip_angle": stats.sum_slip_angles / stats.total_frames,
                "max_slip_angle": stats.max_slip_angle,
                "avg_combined_slip": stats.sum_combined_slips / stats.total_frames,
                "avg_suspension_travel": stats.sum_suspension_samples / stats.total_frames,
                "peak_suspension_travel": stats.peak_suspension_travel,
                "bottom_out_ratio": stats.bottom_out_count / stats.total_frames,
            }

        # Front vs rear average suspension travel (used for ARB balance calc)
        def _avg_travel(*corners: str) -> float:
            values = [
                summary["corners"][c]["avg_suspension_travel"]
                for c in corners
                if c in summary["corners"]
            ]
            return sum(values) / len(values) if values else 0.0

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
            "rpm": round(f.rpm, 0),
            "gear": f.gear,
            "boost": round(f.boost, 2),
            "throttle": round(f.throttle, 2),
            "brake": round(f.brake, 2),
            "steer": round(f.steer, 2),
            "lateral_g": round(f.accel_x / 9.81, 2),
            "longitudinal_g": round(f.accel_y / 9.81, 2),
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
            "tire_slip_ratio": {
                "fl": round(f.tire_slip_ratio_fl, 3),
                "fr": round(f.tire_slip_ratio_fr, 3),
                "rl": round(f.tire_slip_ratio_rl, 3),
                "rr": round(f.tire_slip_ratio_rr, 3),
            },
            "tire_slip_angle": {
                "fl": round(f.tire_slip_angle_fl, 3),
                "fr": round(f.tire_slip_angle_fr, 3),
                "rl": round(f.tire_slip_angle_rl, 3),
                "rr": round(f.tire_slip_angle_rr, 3),
            },
            "game_type": f.game_type,
        }

    def reset(self) -> None:
        """Clear all accumulated data to start a fresh session."""
        self.__init__()

    def set_latest_frame(self, frame: TelemetryFrame) -> None:
        """Set the most recently parsed frame for live broadcasting."""
        self._latest_frame = frame
