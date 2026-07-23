"""
Tests for Tuning Goal / Discipline customization across analyzers.
"""

import pytest
from app.analysis.math_analyzer import MathBaselineAnalyzer
from app.analysis.ollama_analyzer import OllamaAnalyzer
from app.analysis.base import SetupSnapshot


def _default_setup(**overrides) -> SetupSnapshot:
    defaults = dict(
        tire_pressure_front=30.0,
        tire_pressure_rear=30.0,
        camber_front=-2.5,
        camber_rear=-1.5,
        springs_front=500.0,
        springs_rear=450.0,
        arb_front=25.0,
        arb_rear=20.0,
        bump_front=5.0,
        bump_rear=5.0,
        rebound_front=5.0,
        rebound_rear=5.0,
        tuning_goal="street_road",
    )
    defaults.update(overrides)
    return SetupSnapshot(**defaults)


def _make_corner(inner, center, outer, peak_travel=0.8, bottom_out_ratio=0.0):
    return {
        "avg_inner_temp": inner,
        "avg_center_temp": center,
        "avg_outer_temp": outer,
        "avg_suspension_travel": 0.75,
        "peak_suspension_travel": peak_travel,
        "bottom_out_ratio": bottom_out_ratio,
    }


def _sample_metrics(inner_delta=7.5, peak_travel=0.75):
    corner = _make_corner(inner=80.0 + inner_delta / 2, center=80.0, outer=80.0 - inner_delta / 2, peak_travel=peak_travel)
    return {
        "total_frames": 3600,
        "avg_speed_mps": 40.0,
        "corners": {
            "fl": corner.copy(),
            "fr": corner.copy(),
            "rl": corner.copy(),
            "rr": corner.copy(),
        },
        "front_avg_suspension_travel": 0.75,
        "rear_avg_suspension_travel": 0.75,
    }


class TestTuningGoals:
    def setup_method(self):
        self.math_analyzer = MathBaselineAnalyzer()
        self.ollama_analyzer = OllamaAnalyzer()

    @pytest.mark.asyncio
    async def test_camber_recommendation_differs_by_goal(self):
        # With inner-outer delta of 7.5°C:
        # street_road target delta is 7.5°C -> no camber change
        # drift target delta is 12.0°C -> inner edge is cooler than drift target -> needs more negative camber
        metrics = _sample_metrics(inner_delta=7.5)
        setup = _default_setup()

        res_street = await self.math_analyzer.analyze(metrics, setup, tuning_goal="street_road")
        camber_street = [a for a in res_street.adjustments if "camber" in a.parameter]
        assert len(camber_street) == 0

        res_drift = await self.math_analyzer.analyze(metrics, setup, tuning_goal="drift")
        camber_drift = [a for a in res_drift.adjustments if "camber" in a.parameter]
        assert len(camber_drift) > 0
        assert camber_drift[0].delta < 0  # more negative camber needed

    @pytest.mark.asyncio
    async def test_summary_includes_goal_name(self):
        metrics = _sample_metrics()
        setup = _default_setup()

        res_dirt = await self.math_analyzer.analyze(metrics, setup, tuning_goal="dirt_rally")
        assert "Dirt / Rally" in res_dirt.summary

        res_drag = await self.math_analyzer.analyze(metrics, setup, tuning_goal="drag")
        assert "Drag" in res_drag.summary

    def test_ollama_user_message_includes_goal_guidance(self):
        metrics = _sample_metrics()
        setup = _default_setup()

        msg_drift = self.ollama_analyzer._build_user_message(metrics, setup, tuning_goal="drift")
        assert "TUNING GOAL: DRIFT" in msg_drift
        assert "controlled oversteer bias" in msg_drift.lower()

        msg_offroad = self.ollama_analyzer._build_user_message(metrics, setup, tuning_goal="off_road")
        assert "TUNING GOAL: OFF_ROAD" in msg_offroad
        assert "bump absorption" in msg_offroad.lower()
