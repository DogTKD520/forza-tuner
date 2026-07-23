"""
MathBaselineAnalyzer — deterministic, instant tuning recommendations.

All thresholds and step sizes are loaded from config/tuning_rules.json so they
can be tuned without touching source code.

Rules implemented
─────────────────
Tyre Pressure
  • Average center temperature should equal the average of inner + outer temps
    (i.e. the tyre is working uniformly across its contact patch).
  • If center is hotter than the average edge temps → over-inflated → reduce PSI.
  • If center is cooler → under-inflated → increase PSI.

Camber
  • Under lateral load the inner edge should run 5–10 °C hotter than the outer.
  • Inner cooler than outer → not enough negative camber → increase (more negative).
  • Inner much hotter → too much camber → reduce.

Spring Rate
  • Ideal: peak suspension travel 70–90% of full compression range.
  • Bottom-out ratio (travel ≥ 95%) > 5% of frames → springs too soft → stiffen.
  • Peak travel < 70% → springs too stiff for the circuit → soften.

Anti-Roll Bars
  • Balance: compare average front vs rear suspension travel.
  • If front compresses significantly more than rear → front ARB too soft → stiffen.
  • If rear compresses more → rear ARB too soft → stiffen.
"""

from __future__ import annotations

import logging
from typing import Any

from app.analysis.base import (
    Adjustment,
    AnalysisStrategy,
    SetupSnapshot,
    TuningRecommendationResult,
)
from app.config import get_settings

logger = logging.getLogger(__name__)


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


class MathBaselineAnalyzer(AnalysisStrategy):
    """
    Threshold-based analysis engine.  Executes synchronously in microseconds —
    no external I/O, no GPU, no network calls.
    """

    def __init__(self) -> None:
        rules = get_settings().tuning_rules
        self._pressure_rules = rules["tire_pressure"]
        self._camber_rules = rules["camber"]
        self._spring_rules = rules["spring_rate"]
        self._arb_rules = rules["anti_roll_bar"]

    async def analyze(
        self,
        session_metrics: dict[str, Any],
        setup: SetupSnapshot,
    ) -> TuningRecommendationResult:
        adjustments: list[Adjustment] = []
        corners = session_metrics.get("corners", {})

        # --- Tyre pressure and camber (per corner) ---
        self._analyze_front_axle(corners, setup, adjustments)
        self._analyze_rear_axle(corners, setup, adjustments)

        # --- Spring rates (front / rear averaged) ---
        self._analyze_springs(corners, setup, adjustments)

        # --- Anti-roll bars ---
        self._analyze_arbs(session_metrics, setup, adjustments)

        summary = self._build_summary(adjustments)
        return TuningRecommendationResult(
            analyzer_type="math",
            adjustments=adjustments,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Pressure & Camber — Front axle
    # ------------------------------------------------------------------

    def _analyze_front_axle(
        self,
        corners: dict,
        setup: SetupSnapshot,
        adjustments: list[Adjustment],
    ) -> None:
        fl = corners.get("fl")
        fr = corners.get("fr")
        if fl and fr:
            avg_inner = (fl["avg_inner_temp"] + fr["avg_inner_temp"]) / 2
            avg_center = (fl["avg_center_temp"] + fr["avg_center_temp"]) / 2
            avg_outer = (fl["avg_outer_temp"] + fr["avg_outer_temp"]) / 2

            pressure_adj = self._pressure_adjustment(
                avg_inner, avg_center, avg_outer,
                setup.tire_pressure_front, "tire_pressure_front",
            )
            if pressure_adj:
                adjustments.append(pressure_adj)

            camber_adj = self._camber_adjustment(
                avg_inner, avg_outer,
                setup.camber_front, "camber_front",
            )
            if camber_adj:
                adjustments.append(camber_adj)

    # ------------------------------------------------------------------
    # Pressure & Camber — Rear axle
    # ------------------------------------------------------------------

    def _analyze_rear_axle(
        self,
        corners: dict,
        setup: SetupSnapshot,
        adjustments: list[Adjustment],
    ) -> None:
        rl = corners.get("rl")
        rr = corners.get("rr")
        if rl and rr:
            avg_inner = (rl["avg_inner_temp"] + rr["avg_inner_temp"]) / 2
            avg_center = (rl["avg_center_temp"] + rr["avg_center_temp"]) / 2
            avg_outer = (rl["avg_outer_temp"] + rr["avg_outer_temp"]) / 2

            pressure_adj = self._pressure_adjustment(
                avg_inner, avg_center, avg_outer,
                setup.tire_pressure_rear, "tire_pressure_rear",
            )
            if pressure_adj:
                adjustments.append(pressure_adj)

            camber_adj = self._camber_adjustment(
                avg_inner, avg_outer,
                setup.camber_rear, "camber_rear",
            )
            if camber_adj:
                adjustments.append(camber_adj)

    # ------------------------------------------------------------------
    # Spring rates
    # ------------------------------------------------------------------

    def _analyze_springs(
        self,
        corners: dict,
        setup: SetupSnapshot,
        adjustments: list[Adjustment],
    ) -> None:
        rules = self._spring_rules

        def _axle_spring_adj(
            corner_names: list[str],
            current_spring: float,
            param_name: str,
        ) -> Adjustment | None:
            axle_data = [corners[c] for c in corner_names if c in corners]
            if not axle_data:
                return None

            peak_travel = max(d["peak_suspension_travel"] for d in axle_data)
            bottom_out_ratio = max(d["bottom_out_ratio"] for d in axle_data)

            if bottom_out_ratio >= 0.05:
                # Bottoming out — stiffen springs
                delta_pct = rules["bottom_out_step_percent"]
                reason = (
                    f"Bottoming out {bottom_out_ratio:.1%} of the time. "
                    f"Stiffen springs by {abs(delta_pct)}%."
                )
            elif peak_travel < rules["target_travel_utilisation_min"]:
                # Barely using travel — soften
                delta_pct = rules["undertravel_step_percent"]
                reason = (
                    f"Peak travel only {peak_travel:.1%} — springs too stiff. "
                    f"Soften by {abs(delta_pct)}%."
                )
            elif peak_travel <= rules["target_travel_utilisation_max"]:
                return None   # within target range — no change
            else:
                return None

            delta = current_spring * (delta_pct / 100.0)
            recommended = _clamp(
                current_spring + delta,
                current_spring * (1 - rules["max_adjustment_percent"] / 100),
                current_spring * (1 + rules["max_adjustment_percent"] / 100),
            )
            return Adjustment(
                parameter=param_name,
                current_value=current_spring,
                recommended_value=round(recommended, 1),
                delta=round(recommended - current_spring, 1),
                reason=reason,
            )

        front_adj = _axle_spring_adj(["fl", "fr"], setup.springs_front, "springs_front")
        rear_adj = _axle_spring_adj(["rl", "rr"], setup.springs_rear, "springs_rear")
        if front_adj:
            adjustments.append(front_adj)
        if rear_adj:
            adjustments.append(rear_adj)

    # ------------------------------------------------------------------
    # Anti-roll bars
    # ------------------------------------------------------------------

    def _analyze_arbs(
        self,
        session_metrics: dict,
        setup: SetupSnapshot,
        adjustments: list[Adjustment],
    ) -> None:
        rules = self._arb_rules
        front_travel = session_metrics.get("front_avg_suspension_travel", 0.0)
        rear_travel = session_metrics.get("rear_avg_suspension_travel", 0.0)

        if rear_travel < 1e-6:
            return

        roll_ratio = front_travel / rear_travel
        tolerance = rules["tolerance_ratio"]

        if abs(roll_ratio - rules["target_roll_balance_ratio"]) <= tolerance:
            return   # balanced enough

        if roll_ratio > 1 + tolerance:
            # Front rolling more → stiffen front ARB
            delta_pct = rules["step_percent"]
            reason = (
                f"Front suspension compresses {roll_ratio:.2f}x more than rear. "
                "Stiffen front ARB."
            )
            param = "arb_front"
            current = setup.arb_front
        else:
            # Rear rolling more → stiffen rear ARB
            delta_pct = rules["step_percent"]
            reason = (
                f"Rear suspension compresses {1/roll_ratio:.2f}x more than front. "
                "Stiffen rear ARB."
            )
            param = "arb_rear"
            current = setup.arb_rear

        delta = current * (delta_pct / 100.0)
        recommended = _clamp(
            current + delta,
            current * (1 - rules["max_adjustment_percent"] / 100),
            current * (1 + rules["max_adjustment_percent"] / 100),
        )
        adjustments.append(
            Adjustment(
                parameter=param,
                current_value=current,
                recommended_value=round(recommended, 1),
                delta=round(recommended - current, 1),
                reason=reason,
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pressure_adjustment(
        self,
        avg_inner: float,
        avg_center: float,
        avg_outer: float,
        current_psi: float,
        param_name: str,
    ) -> Adjustment | None:
        rules = self._pressure_rules
        edge_avg = (avg_inner + avg_outer) / 2.0
        delta_to_edge = avg_center - edge_avg   # positive → over-inflated

        if abs(delta_to_edge) <= rules["tolerance_celsius"]:
            return None

        steps = delta_to_edge / rules["tolerance_celsius"]
        psi_change = -steps * rules["step_psi"]   # negative because hotter center → reduce PSI
        psi_change = _clamp(psi_change, -rules["max_adjustment_psi"], rules["max_adjustment_psi"])
        recommended = round(current_psi + psi_change, 1)

        if delta_to_edge > 0:
            reason = (
                f"Centre tyre {delta_to_edge:.1f}°C hotter than edges — over-inflated. "
                f"Reduce {param_name} by {abs(psi_change):.1f} PSI."
            )
        else:
            reason = (
                f"Centre tyre {abs(delta_to_edge):.1f}°C cooler than edges — under-inflated. "
                f"Increase {param_name} by {abs(psi_change):.1f} PSI."
            )

        return Adjustment(
            parameter=param_name,
            current_value=current_psi,
            recommended_value=recommended,
            delta=round(psi_change, 1),
            reason=reason,
        )

    def _camber_adjustment(
        self,
        avg_inner: float,
        avg_outer: float,
        current_camber: float,
        param_name: str,
    ) -> Adjustment | None:
        rules = self._camber_rules
        inner_outer_delta = avg_inner - avg_outer   # positive = inner hotter than outer

        target = rules["target_inner_outer_delta_celsius"]
        tolerance = rules["tolerance_celsius"]
        deviation = inner_outer_delta - target

        if abs(deviation) <= tolerance:
            return None

        # deviation > 0 → inner too hot → too much camber → reduce magnitude
        #   Camber is negative (e.g. -2.5°); reducing magnitude means moving toward 0
        #   → add a positive step_degrees value.
        # deviation < 0 → inner too cool → not enough camber → increase magnitude
        #   Moving away from 0 (more negative) → subtract step_degrees.
        steps = abs(deviation) / tolerance
        raw_change = steps * rules["step_degrees"]
        raw_change = min(raw_change, rules["max_adjustment_degrees"])

        if deviation > 0:
            # Too much camber: reduce magnitude (add positive value to negative camber)
            camber_change = +raw_change
            reason = (
                f"Inner {deviation:.1f}°C hotter than target delta — too much camber. "
                f"Reduce {param_name} magnitude by {raw_change:.1f}°."
            )
        else:
            # Not enough camber: increase magnitude (subtract from negative camber)
            camber_change = -raw_change
            reason = (
                f"Inner {abs(deviation):.1f}°C cooler than target delta — not enough camber. "
                f"Increase {param_name} magnitude by {raw_change:.1f}°."
            )

        recommended = round(current_camber + camber_change, 1)

        return Adjustment(
            parameter=param_name,
            current_value=current_camber,
            recommended_value=recommended,
            delta=round(camber_change, 1),
            reason=reason,
        )

    def _build_summary(self, adjustments: list[Adjustment]) -> str:
        if not adjustments:
            return "Setup looks well-balanced for this session. No changes recommended."
        parts = [f"• {adj.reason}" for adj in adjustments]
        return "Math analysis recommends the following changes:\n" + "\n".join(parts)
