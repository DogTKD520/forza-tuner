"""
Tests for the async GPU analysis queue.

Verifies sequential processing order, task status transitions,
and that the worker completes tasks without dropping them.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio

from app.analysis.base import AnalysisStrategy, SetupSnapshot, TuningRecommendationResult
from app.analysis.gpu_queue import AnalysisQueue, TaskStatus


# ── Minimal stub strategy ──────────────────────────────────────

class _StubAnalyzer(AnalysisStrategy):
    """Records call order and simulates configurable processing delay."""

    def __init__(self, delay: float = 0.0):
        self.call_order: list[str] = []
        self._delay = delay

    async def analyze(
        self, session_metrics: dict, setup: SetupSnapshot
    ) -> TuningRecommendationResult:
        if self._delay:
            await asyncio.sleep(self._delay)
        tag = session_metrics.get("tag", "unknown")
        self.call_order.append(tag)
        return TuningRecommendationResult(
            analyzer_type="stub",
            summary=f"processed:{tag}",
        )


def _dummy_setup() -> SetupSnapshot:
    return SetupSnapshot(
        tire_pressure_front=30.0, tire_pressure_rear=30.0,
        camber_front=-2.5, camber_rear=-1.5,
        springs_front=500.0, springs_rear=450.0,
        arb_front=25.0, arb_rear=20.0,
        bump_front=5.0, bump_rear=5.0,
        rebound_front=5.0, rebound_rear=5.0,
    )


class TestAnalysisQueue:

    @pytest.mark.asyncio
    async def test_task_transitions_from_queued_to_completed(self):
        stub = _StubAnalyzer()
        queue = AnalysisQueue(stub)
        await queue.start()

        task_id = await queue.enqueue({"tag": "a"}, _dummy_setup())

        # Initially queued
        task = queue.get_task_status(task_id)
        assert task is not None
        assert task.status in (TaskStatus.QUEUED, TaskStatus.PROCESSING)

        # Wait for completion
        await asyncio.sleep(0.1)
        task = queue.get_task_status(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.result is not None
        assert "processed:a" in task.result.summary

        await queue.stop()

    @pytest.mark.asyncio
    async def test_tasks_processed_in_fifo_order(self):
        """With a delay, tasks enqueued first must be processed first."""
        stub = _StubAnalyzer(delay=0.02)
        queue = AnalysisQueue(stub)
        await queue.start()

        for tag in ["first", "second", "third"]:
            await queue.enqueue({"tag": tag}, _dummy_setup())

        # Give enough time for all three to complete
        await asyncio.sleep(0.5)

        assert stub.call_order == ["first", "second", "third"], (
            f"Expected FIFO order, got: {stub.call_order}"
        )

        await queue.stop()

    @pytest.mark.asyncio
    async def test_multiple_tasks_all_complete(self):
        stub = _StubAnalyzer()
        queue = AnalysisQueue(stub)
        await queue.start()

        task_ids = [
            await queue.enqueue({"tag": str(i)}, _dummy_setup())
            for i in range(5)
        ]

        await asyncio.sleep(0.3)

        for tid in task_ids:
            assert queue.get_task_status(tid).status == TaskStatus.COMPLETED

        await queue.stop()

    @pytest.mark.asyncio
    async def test_unknown_task_id_returns_none(self):
        stub = _StubAnalyzer()
        queue = AnalysisQueue(stub)
        await queue.start()
        assert queue.get_task_status("non-existent-id") is None
        await queue.stop()
