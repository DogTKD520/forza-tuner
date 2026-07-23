"""
Abstract base class for the telemetry ingestion pipeline.

The UDP listener (and any future WebSocket remote agent) only depend on this
interface.  Concrete implementations handle parsing, aggregation and fan-out
without the transport layer knowing anything about them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceInfo:
    """Metadata attached to each raw packet by the transport layer."""
    address: str          # e.g. "192.168.1.5"
    port: int
    game_type: str        # "FM" | "FH"


class AbstractTelemetryProcessor(ABC):
    """
    Contract between transport (UDP / WebSocket) and the processing pipeline.

    Transport layers call `process_raw_packet` and hand off bytes completely.
    They never call the parser or aggregator directly.
    """

    @abstractmethod
    async def process_raw_packet(
        self, raw_bytes: bytes, source_info: SourceInfo
    ) -> None:
        """Parse `raw_bytes` and feed the result into the processing pipeline."""
        ...

    @abstractmethod
    async def get_latest_frame(self) -> dict[str, Any] | None:
        """Return the most recently parsed telemetry frame as a plain dict."""
        ...
