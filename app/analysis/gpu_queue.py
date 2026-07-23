"""
GPU task queue — ensures LLM analysis requests are processed sequentially.

An `asyncio.Queue` with a single background worker guarantees that only one
Ollama inference request is in-flight at a time, preventing GPU VRAM
exhaustion.

When USE_LLM=False the queue is never used — the math analyser responds
synchronously and immediately.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.analysis.base import AnalysisStrategy, SetupSnapshot, TuningRecommendationResult

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AnalysisTask:
    task_id: str
    session_metrics: dict[str, Any]
    setup: SetupSnapshot
    status: TaskStatus = TaskStatus.QUEUED
    result: TuningRecommendationResult | None = None
    error: str | None = None


class AnalysisQueue:
    """
    Singleton-style async task queue for sequential LLM inference.

    Usage:
        queue = AnalysisQueue(ollama_strategy)
        await queue.start()                       # call once at app startup
        task_id = await queue.enqueue(metrics, setup)
        # ... poll GET /api/tasks/{task_id}
        await queue.stop()                        # call at shutdown
    """

    def __init__(self, strategy: AnalysisStrategy) -> None:
        self._strategy = strategy
        self._queue: asyncio.Queue[AnalysisTask] = asyncio.Queue()
        self._tasks: dict[str, AnalysisTask] = {}
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Launch the background worker. Call once at application startup."""
        self._worker_task = asyncio.create_task(self._worker_loop(), name="gpu-queue-worker")
        logger.info("Analysis queue worker started.")

    async def stop(self) -> None:
        """Gracefully shut down the worker."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Analysis queue worker stopped.")

    async def enqueue(
        self,
        session_metrics: dict[str, Any],
        setup: SetupSnapshot,
    ) -> str:
        """Add a job to the queue and return its task_id for status polling."""
        task_id = str(uuid.uuid4())
        task = AnalysisTask(
            task_id=task_id,
            session_metrics=session_metrics,
            setup=setup,
        )
        self._tasks[task_id] = task
        await self._queue.put(task)
        logger.info("Enqueued analysis task %s (queue depth: %d)", task_id, self._queue.qsize())
        return task_id

    def get_task_status(self, task_id: str) -> AnalysisTask | None:
        return self._tasks.get(task_id)

    # ------------------------------------------------------------------
    # Internal worker
    # ------------------------------------------------------------------

    async def _worker_loop(self) -> None:
        """Single-concurrency consumer — processes one job at a time."""
        while True:
            task = await self._queue.get()
            task.status = TaskStatus.PROCESSING
            logger.info("Processing analysis task %s", task.task_id)
            try:
                task.result = await self._strategy.analyze(
                    task.session_metrics, task.setup
                )
                task.status = TaskStatus.COMPLETED
                logger.info("Completed analysis task %s", task.task_id)
            except Exception as exc:
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                logger.error("Analysis task %s failed: %s", task.task_id, exc)
            finally:
                self._queue.task_done()
