"""
OllamaAnalyzer — LLM-backed analysis strategy.

Formats the session metrics and current setup into a structured prompt and
sends it to a local Ollama instance.  The response is parsed into the same
`TuningRecommendationResult` type as the math analyser so callers are
completely agnostic to which strategy is active.

This strategy is ONLY active when USE_LLM=True in .env.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.analysis.base import (
    Adjustment,
    AnalysisStrategy,
    SetupSnapshot,
    TuningRecommendationResult,
)
from app.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert Forza racing car tuning engineer.
Analyse the telemetry session metrics and current vehicle setup provided by the user.
The vehicle setup parameters contain `min`, `current`, and `max` bounds.
Ensure your recommended values STRICTLY fall within the provided min and max bounds for each parameter.

Respond ONLY with a valid JSON object matching this exact schema:
{
  "summary": "<one paragraph overview>",
  "adjustments": [
    {
      "parameter": "<parameter_name>",
      "current_value": <float>,
      "recommended_value": <float>,
      "delta": <float>,
      "reason": "<explanation>"
    }
  ]
}
Parameter names must be one of:
  tire_pressure_front, tire_pressure_rear,
  camber_front, camber_rear,
  springs_front, springs_rear,
  arb_front, arb_rear,
  bump_front, bump_rear,
  rebound_front, rebound_rear.
Do not include any text outside the JSON object.
"""


_GOAL_GUIDANCE = {
    "street_road": "Target balanced high-grip track performance, uniform tire heat, roll stability, and 70-90% suspension travel utilization.",
    "dirt_rally": "Prioritize suspension travel compliance (80-95%), softer ARBs for uneven terrain traction, and fast damper responsiveness over jumps.",
    "off_road": "Prioritize maximum bump absorption (85-98% travel), low roll resistance on uneven terrain, and soft high-travel dampening.",
    "drift": "Prioritize controlled oversteer bias: stiffer rear ARBs/springs, aggressive front negative camber for turn-in angle, and higher rear tire pressure for slide control.",
    "drag": "Prioritize straight-line launch traction: stiff rear springs/dampers to prevent squat, neutral camber for maximum contact patch, and minimal front roll stiffness.",
}


class OllamaAnalyzer(AnalysisStrategy):
    """
    Sends session data to a locally running Ollama model for AI-assisted
    tuning recommendations.

    Failures fall back gracefully — the caller receives an error summary
    rather than an unhandled exception.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.ollama_host.rstrip("/")
        self._model = settings.ollama_model
        self._timeout = settings.ollama_timeout_seconds
        
        # Load forza.guide knowledge base
        import os
        from pathlib import Path
        knowledge_dir = Path("config/knowledge")
        self._knowledge_context = ""
        if knowledge_dir.exists():
            kb_parts = []
            for filepath in sorted(knowledge_dir.glob("*.md")):
                with open(filepath, "r", encoding="utf-8") as kb_file:
                    kb_parts.append(kb_file.read())
            self._knowledge_context = "\n\n".join(kb_parts)

    async def analyze(
        self,
        session_metrics: dict[str, Any],
        setup: SetupSnapshot,
        tuning_goal: str = "street_road",
    ) -> TuningRecommendationResult:
        user_content = self._build_user_message(session_metrics, setup, tuning_goal)

        try:
            raw_response = await self._call_ollama(user_content)
            parsed = json.loads(raw_response)
            adjustments = [
                Adjustment(
                    parameter=adj.get("parameter", ""),
                    current_value=adj.get("current_value", 0),
                    recommended_value=adj.get("recommended_value", 0),
                    delta=adj.get("delta", 0.0),
                    reason=adj.get("reason", ""),
                    is_upgrade_recommendation=adj.get("is_upgrade_recommendation", False),
                    pi_impact_warning=adj.get("pi_impact_warning"),
                )
                for adj in parsed.get("adjustments", [])
            ]

            return TuningRecommendationResult(
                analyzer_type="ollama",
                adjustments=adjustments,
                summary=parsed.get("summary", ""),
                raw_output=parsed,
            )
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.error("OllamaAnalyzer failed: %s", exc)
            raise RuntimeError(f"AI server is unreachable or returned invalid data. Check your Ollama host connection. Error: {exc}") from exc

    async def _call_ollama(self, user_message: str) -> str:
        system_prompt = _SYSTEM_PROMPT
        if self._knowledge_context:
            system_prompt += "\n\n--- FORZA.GUIDE KNOWLEDGE BASE ---\n"
            system_prompt += "Use the following knowledge base to formulate your recommendations.\n\n"
            system_prompt += self._knowledge_context

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/chat", json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

    def _build_user_message(
        self, session_metrics: dict[str, Any], setup: SetupSnapshot, tuning_goal: str = "street_road"
    ) -> str:
        active_goal = tuning_goal or getattr(setup, "tuning_goal", "street_road")
        guidance = _GOAL_GUIDANCE.get(active_goal, _GOAL_GUIDANCE["street_road"])
        setup_data = setup.__dict__.copy()
        setup_data["tuning_goal"] = active_goal
        return (
            f"TUNING GOAL: {active_goal.upper()}\n"
            f"DISCIPLINE PHYSICS OBJECTIVE: {guidance}\n\n"
            "SESSION METRICS:\n"
            f"{json.dumps(session_metrics, indent=2)}\n\n"
            "CURRENT VEHICLE SETUP (With Bounds):\n"
            f"{json.dumps(setup_data, default=lambda o: o.__dict__, indent=2)}"
        )
