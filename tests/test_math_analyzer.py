"""
Tests for MathBaselineAnalyzer.

Each test exercises one recommendation rule in isolation using hand-crafted
session_metrics dicts, verifying the direction and presence of adjustments.
"""

import pytest
import pytest_asyncio

from app.analysis.math_analyzer import MathBaselineAnalyzer
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
    )
    defaults.update(overrides)
    return SetupSnapshot(**defaults)


def _make_corner(
    temp=90.0,
    combined_slip=0.10,
    max_slip_angle=0.08,
    peak_travel=0.8,
    bottom_out_ratio=0.0,
    avg_travel=0.75
):
    return {
        "avg_temp": temp,
        "avg_combined_slip": combined_slip,
        "avg_slip_ratio": 0.05,
        "avg_slip_angle": 0.05,
        "max_slip_angle": max_slip_angle,
        "avg_suspension_travel": avg_travel,
        "peak_suspension_travel": peak_travel,
        "bottom_out_ratio": bottom_out_ratio,
    }


def _balanced_metrics(**corner_overrides):
    """Return a well-balanced session metrics dict."""
    balanced_corner = _make_corner(temp=90.0, combined_slip=0.10, max_slip_angle=0.08)
    corners = {
        "fl": balanced_corner.copy(),
        "fr": balanced_corner.copy(),
        "rl": balanced_corner.copy(),
        "rr": balanced_corner.copy(),
    }
    corners.update(corner_overrides)
    return {
        "total_frames": 3600,
        "avg_speed_mps": 40.0,
        "corners": corners,
        "front_avg_suspension_travel": 0.75,
        "rear_avg_suspension_travel": 0.75,
    }


class TestMathBaselineAnalyzer:
    def setup_method(self):
        self.analyzer = MathBaselineAnalyzer()

    @pytest.mark.asyncio
    async def test_no_recommendations_for_balanced_setup(self):
        metrics = _balanced_metrics()
        result = await self.analyzer.analyze(metrics, _default_setup())
        assert result.adjustments == []
        assert "well-balanced" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_hot_and_sliding_increases_pressure(self):
        """Hot (105C) and sliding (>0.12 slip) -> increase PSI."""
        hot_corner = _make_corner(temp=105.0, combined_slip=0.15)
        metrics = _balanced_metrics(fl=hot_corner, fr=hot_corner)
        result = await self.analyzer.analyze(metrics, _default_setup())
        pressure_adj = next(
            (a for a in result.adjustments if a.parameter == "tire_pressure_front"), None
        )
        assert pressure_adj is not None, "Expected a pressure adjustment for front"
        assert pressure_adj.delta > 0, "Overheating & sliding -> increase PSI"

    @pytest.mark.asyncio
    async def test_cold_and_sliding_reduces_pressure(self):
        """Cold (75C) and sliding (>0.12 slip) -> reduce PSI."""
        cold_corner = _make_corner(temp=75.0, combined_slip=0.15)
        metrics = _balanced_metrics(fl=cold_corner, fr=cold_corner)
        result = await self.analyzer.analyze(metrics, _default_setup())
        pressure_adj = next(
            (a for a in result.adjustments if a.parameter == "tire_pressure_front"), None
        )
        assert pressure_adj is not None
        assert pressure_adj.delta < 0, "Cold & sliding -> reduce PSI"

    @pytest.mark.asyncio
    async def test_too_much_slip_angle_increases_negative_camber(self):
        """Max slip angle > 0.10 -> roll-over -> increase negative camber."""
        excess_slip_corner = _make_corner(max_slip_angle=0.15)
        metrics = _balanced_metrics(fl=excess_slip_corner, fr=excess_slip_corner)
        result = await self.analyzer.analyze(metrics, _default_setup())
        camber_adj = next(
            (a for a in result.adjustments if a.parameter == "camber_front"), None
        )
        assert camber_adj is not None
        # Increasing negative camber means moving away from 0 -> delta should be negative
        assert camber_adj.delta < 0, "Too much slip angle -> increase negative camber (delta negative)"

    @pytest.mark.asyncio
    async def test_very_low_slip_angle_reduces_negative_camber(self):
        """Max slip angle < 0.05 -> reduce negative camber magnitude."""
        low_slip_corner = _make_corner(max_slip_angle=0.03)
        metrics = _balanced_metrics(fl=low_slip_corner, fr=low_slip_corner)
        result = await self.analyzer.analyze(metrics, _default_setup())
        camber_adj = next(
            (a for a in result.adjustments if a.parameter == "camber_front"), None
        )
        assert camber_adj is not None
        # Reducing magnitude of negative camber -> delta positive
        assert camber_adj.delta > 0, "Very low slip angle -> reduce negative camber magnitude (delta positive)"

    @pytest.mark.asyncio
    async def test_bottoming_out_stiffens_springs(self):
        """High bottom-out ratio → springs too soft → stiffen."""
        soft_corner = _make_corner(80.0, 80.0, 80.0, peak_travel=0.98, bottom_out_ratio=0.15)
        metrics = _balanced_metrics(fl=soft_corner, fr=soft_corner)
        result = await self.analyzer.analyze(metrics, _default_setup())
        spring_adj = next(
            (a for a in result.adjustments if a.parameter == "springs_front"), None
        )
        assert spring_adj is not None
        assert spring_adj.delta > 0, "Bottoming out → stiffen springs"

    @pytest.mark.asyncio
    async def test_undertravel_softens_springs(self):
        """Peak travel below 70% → springs too stiff → soften."""
        stiff_corner = _make_corner(80.0, 80.0, 80.0, peak_travel=0.55, avg_travel=0.50)
        metrics = _balanced_metrics(fl=stiff_corner, fr=stiff_corner)
        result = await self.analyzer.analyze(metrics, _default_setup())
        spring_adj = next(
            (a for a in result.adjustments if a.parameter == "springs_front"), None
        )
        assert spring_adj is not None
        assert spring_adj.delta < 0, "Under-travel → soften springs"

    @pytest.mark.asyncio
    async def test_front_roll_imbalance_stiffens_front_arb(self):
        """Front compresses much more than rear → stiffen front ARB."""
        metrics = _balanced_metrics()
        metrics["front_avg_suspension_travel"] = 0.85
        metrics["rear_avg_suspension_travel"] = 0.50
        result = await self.analyzer.analyze(metrics, _default_setup())
        arb_adj = next(
            (a for a in result.adjustments if a.parameter == "arb_front"), None
        )
        assert arb_adj is not None
        assert arb_adj.delta > 0, "Front roll > rear → stiffen front ARB"

    @pytest.mark.asyncio
    async def test_rear_roll_imbalance_stiffens_rear_arb(self):
        """Rear compresses much more than front → stiffen rear ARB."""
        metrics = _balanced_metrics()
        metrics["front_avg_suspension_travel"] = 0.50
        metrics["rear_avg_suspension_travel"] = 0.85
        result = await self.analyzer.analyze(metrics, _default_setup())
        arb_adj = next(
            (a for a in result.adjustments if a.parameter == "arb_rear"), None
        )
        assert arb_adj is not None
        assert arb_adj.delta > 0, "Rear roll > front → stiffen rear ARB"

    @pytest.mark.asyncio
    async def test_analyzer_type_is_math(self):
        metrics = _balanced_metrics()
        result = await self.analyzer.analyze(metrics, _default_setup())
        assert result.analyzer_type == "math"

    @pytest.mark.asyncio
    async def test_nontuneable_arbs_suggests_upgrade(self):
        """When ARBs are non-tuneable and unbalanced, suggest installing Race ARBs."""
        metrics = _balanced_metrics()
        metrics["front_avg_suspension_travel"] = 0.85
        metrics["rear_avg_suspension_travel"] = 0.50
        setup = _default_setup(tuneable_arbs=False)
        result = await self.analyzer.analyze(metrics, setup)
        upgrade_adj = next(
            (a for a in result.adjustments if a.parameter == "arb_upgrade"), None
        )
        assert upgrade_adj is not None
        assert upgrade_adj.is_upgrade_recommendation is True
        assert "Install Race Anti-Roll Bars" in upgrade_adj.reason

    @pytest.mark.asyncio
    async def test_nontuneable_springs_suggests_upgrade(self):
        """When springs are non-tuneable and bottoming out, suggest installing Race Springs."""
        soft_corner = _make_corner(80.0, 80.0, 80.0, peak_travel=0.98, bottom_out_ratio=0.15)
        metrics = _balanced_metrics(fl=soft_corner, fr=soft_corner)
        setup = _default_setup(tuneable_springs=False)
        result = await self.analyzer.analyze(metrics, setup)
        upgrade_adj = next(
            (a for a in result.adjustments if a.parameter == "springs_upgrade"), None
        )
        assert upgrade_adj is not None
        assert upgrade_adj.is_upgrade_recommendation is True
        assert "Install Race Springs" in upgrade_adj.reason

    @pytest.mark.asyncio
    async def test_overheating_tires_unlocked_recommends_compound_and_pi_warning(self):
        """Hot tires with unlocked compound recommend compound upgrade + PI warning if near boundary."""
        hot_corner = _make_corner(105.0, 105.0, 105.0)
        metrics = _balanced_metrics(
            fl=hot_corner, fr=hot_corner, rl=hot_corner, rr=hot_corner
        )
        setup = _default_setup(tire_compound="Sport", lock_tire_compound=False, pi_rating=790)
        result = await self.analyzer.analyze(metrics, setup)
        compound_adj = next(
            (a for a in result.adjustments if a.parameter == "tire_compound_upgrade"), None
        )
        assert compound_adj is not None
        assert compound_adj.is_upgrade_recommendation is True
        assert compound_adj.recommended_value == "Race"
        assert compound_adj.pi_impact_warning is not None
        assert "may push car (790 PI) into next class" in compound_adj.pi_impact_warning

    @pytest.mark.asyncio
    async def test_overheating_tires_locked_does_not_recommend_upgrade(self):
        """Hot tires with locked compound do not recommend upgrading tire compound."""
        hot_corner = _make_corner(105.0, 105.0, 105.0)
        metrics = _balanced_metrics(
            fl=hot_corner, fr=hot_corner, rl=hot_corner, rr=hot_corner
        )
        setup = _default_setup(tire_compound="Sport", lock_tire_compound=True)
        result = await self.analyzer.analyze(metrics, setup)
        upgrade_adj = next(
            (a for a in result.adjustments if a.parameter == "tire_compound_upgrade"), None
        )
        assert upgrade_adj is None, "Should not recommend compound upgrade when tire is locked"
        locked_adj = next(
            (a for a in result.adjustments if a.parameter == "tire_compound_locked"), None
        )
        assert locked_adj is not None
        assert "locked in setup" in locked_adj.reason

