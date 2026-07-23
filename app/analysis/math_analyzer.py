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
        self._goal_rules = rules.get("goals", {})
        self._tire_compounds = rules.get("tire_compounds", {})
        self._pi_classes = rules.get("pi_classes", {})

    async def analyze(
        self,
        session_metrics: dict[str, Any],
        setup: SetupSnapshot,
        tuning_goal: str = "street_road",
    ) -> TuningRecommendationResult:
        active_goal = tuning_goal or getattr(setup, "tuning_goal", "street_road")
        goal_profile = self._goal_rules.get(active_goal, self._goal_rules.get("street_road", {}))

        pressure_rules = {**self._pressure_rules, **goal_profile.get("tire_pressure", {})}
        camber_rules = {**self._camber_rules, **goal_profile.get("camber", {})}
        spring_rules = {**self._spring_rules, **goal_profile.get("spring_rate", {})}
        arb_rules = {**self._arb_rules, **goal_profile.get("anti_roll_bar", {})}

        adjustments: list[Adjustment] = []
        corners = session_metrics.get("corners", {})

        # --- Tyre pressure and camber (per corner) ---
        self._analyze_front_axle(corners, setup, adjustments, pressure_rules, camber_rules)
        self._analyze_rear_axle(corners, setup, adjustments, pressure_rules, camber_rules)

        # --- Spring rates (front / rear averaged) ---
        self._analyze_springs(corners, setup, adjustments, spring_rules)

        # --- Anti-roll bars ---
        self._analyze_arbs(session_metrics, setup, adjustments, arb_rules)

        # --- Tire Compound & Thermals ---
        self._analyze_tire_compound(corners, setup, adjustments)

        summary = self._build_summary(adjustments, active_goal)
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
        pressure_rules: dict,
        camber_rules: dict,
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
                pressure_rules,
            )
            if pressure_adj:
                adjustments.append(pressure_adj)

            camber_adj = self._camber_adjustment(
                avg_inner, avg_outer,
                setup.camber_front, "camber_front",
                camber_rules,
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
        pressure_rules: dict,
        camber_rules: dict,
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
                pressure_rules,
            )
            if pressure_adj:
                adjustments.append(pressure_adj)

            camber_adj = self._camber_adjustment(
                avg_inner, avg_outer,
                setup.camber_rear, "camber_rear",
                camber_rules,
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
        spring_rules: dict,
    ) -> None:
        rules = spring_rules

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

        if not setup.tuneable_springs:
            if front_adj or rear_adj:
                reason_text = (front_adj.reason if front_adj else "") + (" " + rear_adj.reason if rear_adj else "")
                adjustments.append(
                    Adjustment(
                        parameter="springs_upgrade",
                        current_value="Stock Springs",
                        recommended_value="Race Springs",
                        delta=0.0,
                        reason=f"Spring adjustments needed ({reason_text.strip()}), but springs are non-tuneable. Install Race Springs to adjust stiffness.",
                        is_upgrade_recommendation=True,
                    )
                )
        else:
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
        arb_rules: dict,
    ) -> None:
        rules = arb_rules
        front_travel = session_metrics.get("front_avg_suspension_travel", 0.0)
        rear_travel = session_metrics.get("rear_avg_suspension_travel", 0.0)

        if rear_travel < 1e-6:
            return

        roll_ratio = front_travel / rear_travel
        tolerance = rules["tolerance_ratio"]

        target_balance = rules["target_roll_balance_ratio"]
        if abs(roll_ratio - target_balance) <= tolerance:
            return   # balanced enough

        if roll_ratio > target_balance + tolerance:
            # Front rolling more → stiffen front ARB
            delta_pct = rules["step_percent"]
            reason = (
                f"Front suspension compresses {roll_ratio:.2f}x relative to rear. "
                "Stiffen front ARB."
            )
            param = "arb_front"
            current = setup.arb_front
        else:
            # Rear rolling more → stiffen rear ARB
            delta_pct = rules["step_percent"]
            reason = (
                f"Rear suspension compresses {1/roll_ratio:.2f}x relative to front. "
                "Stiffen rear ARB."
            )
            param = "arb_rear"
            current = setup.arb_rear

        if not setup.tuneable_arbs:
            adjustments.append(
                Adjustment(
                    parameter="arb_upgrade",
                    current_value="Stock ARBs",
                    recommended_value="Race ARBs",
                    delta=0.0,
                    reason=f"Roll balance adjustment required ({reason}), but Anti-Roll Bars are non-tuneable. Install Race Anti-Roll Bars.",
                    is_upgrade_recommendation=True,
                )
            )
            return

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
    # Tire Compound & Thermal Analysis
    # ------------------------------------------------------------------

    def _analyze_tire_compound(
        self,
        corners: dict,
        setup: SetupSnapshot,
        adjustments: list[Adjustment],
    ) -> None:
        if not corners or not self._tire_compounds:
            return

        compound_name = setup.tire_compound or "Sport"
        compound_info = self._tire_compounds.get(compound_name)
        if not compound_info:
            return

        all_temps = []
        for corner_name, data in corners.items():
            if isinstance(data, dict):
                inner = data.get("avg_inner_temp", 0)
                center = data.get("avg_center_temp", 0)
                outer = data.get("avg_outer_temp", 0)
                all_temps.extend([inner, center, outer])

        if not all_temps:
            return

        avg_tire_temp = sum(all_temps) / len(all_temps)
        min_ideal = compound_info.get("ideal_temp_min_c", 80)
        max_ideal = compound_info.get("ideal_temp_max_c", 100)
        current_tier = compound_info.get("grip_tier", 3)

        if avg_tire_temp > max_ideal:
            if setup.lock_tire_compound:
                adjustments.append(
                    Adjustment(
                        parameter="tire_compound_locked",
                        current_value=compound_name,
                        recommended_value=compound_name,
                        delta=0.0,
                        reason=f"Average tyre temperature ({avg_tire_temp:.1f}°C) exceeds optimal range ({min_ideal}–{max_ideal}°C) for {compound_name} compound. Tire compound upgrade is locked in setup.",
                        is_upgrade_recommendation=False,
                    )
                )
            else:
                next_compound = None
                for c_name, c_info in self._tire_compounds.items():
                    if c_info.get("grip_tier", 0) == current_tier + 1:
                        next_compound = c_name
                        break
                if not next_compound:
                    next_compound = "Race" if compound_name != "Race" else "Slick"

                pi_warning = None
                pi_rating = setup.pi_rating
                for c_label, bounds in self._pi_classes.items():
                    if bounds["min_pi"] <= pi_rating <= bounds["max_pi"]:
                        if bounds["max_pi"] - pi_rating < 25:
                            pi_warning = f"Upgrading to {next_compound} compound may push car ({pi_rating} PI) into next class (max {c_label} is {bounds['max_pi']} PI)."
                        break

                adjustments.append(
                    Adjustment(
                        parameter="tire_compound_upgrade",
                        current_value=compound_name,
                        recommended_value=next_compound,
                        delta=0.0,
                        reason=f"Average tyre temp ({avg_tire_temp:.1f}°C) is above {compound_name} optimal limit ({max_ideal}°C). Recommend upgrading to {next_compound} compound for better thermal capacity and grip.",
                        is_upgrade_recommendation=True,
                        pi_impact_warning=pi_warning,
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
        pressure_rules: dict,
    ) -> Adjustment | None:
        rules = pressure_rules
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
        camber_rules: dict,
    ) -> Adjustment | None:
        rules = camber_rules
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
                f"Inner {deviation:.1f}°C hotter than target delta ({target}°C) — too much camber. "
                f"Reduce {param_name} magnitude by {raw_change:.1f}°."
            )
        else:
            # Not enough camber: increase magnitude (subtract from negative camber)
            camber_change = -raw_change
            reason = (
                f"Inner {abs(deviation):.1f}°C cooler than target delta ({target}°C) — not enough camber. "
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

    def _build_summary(self, adjustments: list[Adjustment], active_goal: str = "street_road") -> str:
        goal_info = self._goal_rules.get(active_goal, {})
        goal_name = goal_info.get("name", active_goal.replace("_", " ").title())
        if not adjustments:
            return f"[{goal_name}] Setup looks well-balanced for this session. No changes recommended."
        parts = [f"• {adj.reason}" for adj in adjustments]
        return f"[{goal_name}] Math analysis recommends the following changes:\n" + "\n".join(parts)
