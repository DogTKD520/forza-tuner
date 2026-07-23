"""
Concrete TelemetryProcessor and async UDP listener.

`ForzaTelemetryProcessor` implements `AbstractTelemetryProcessor`, wiring
together the packet parser and session aggregator.

`UDPListenerProtocol` is an asyncio DatagramProtocol that receives raw UDP
datagrams from the OS and hands them to the processor — keeping the transport
completely decoupled from processing logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.ingestion.base import AbstractTelemetryProcessor, SourceInfo
from app.ingestion.parser import ForzaPacketParser, TelemetryFrame
from app.ingestion.session_aggregator import SessionAggregator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Concrete TelemetryProcessor
# ---------------------------------------------------------------------------

class ForzaTelemetryProcessor(AbstractTelemetryProcessor):
    """
    Bridges the transport layer (UDP) and the processing pipeline
    (parser → aggregator).

    A single shared instance lives on the FastAPI app state so the UDP
    listener and the WebSocket broadcaster both access the same aggregator.
    """

    def __init__(self) -> None:
        self._parser = ForzaPacketParser()
        self._aggregator = SessionAggregator()
        self._is_recording: bool = False

    # ------------------------------------------------------------------
    # AbstractTelemetryProcessor interface
    # ------------------------------------------------------------------

    async def process_raw_packet(
        self, raw_bytes: bytes, source_info: SourceInfo
    ) -> None:
        """Parse bytes and, if a session is active, feed into the aggregator."""
        try:
            frame: TelemetryFrame = self._parser.parse(raw_bytes, source_info.game_type)
        except (ValueError, struct.error) as exc:
            logger.debug("Packet parse error from %s: %s", source_info.address, exc)
            return

        if self._is_recording:
            self._aggregator.ingest(frame)
        else:
            # Always update latest frame for the live WebSocket feed
            self._aggregator._latest_frame = frame  # noqa: SLF001

    async def get_latest_frame(self) -> dict[str, Any] | None:
        return self._aggregator.get_latest_frame_dict()

    # ------------------------------------------------------------------
    # Session control
    # ------------------------------------------------------------------

    def start_recording(self) -> None:
        self._aggregator.reset()
        self._is_recording = True
        logger.info("Telemetry recording started.")

    def stop_recording(self) -> dict[str, Any]:
        self._is_recording = False
        summary = self._aggregator.get_summary()
        logger.info(
            "Telemetry recording stopped. %d frames captured.",
            summary.get("total_frames", 0),
        )
        return summary

    @property
    def is_recording(self) -> bool:
        return self._is_recording


# ---------------------------------------------------------------------------
# asyncio UDP transport
# ---------------------------------------------------------------------------

class _UDPListenerProtocol(asyncio.DatagramProtocol):
    """
    Minimal asyncio protocol that forwards every datagram to the processor.
    Transport concerns (buffering, socket errors) stay here.
    """

    def __init__(
        self,
        processor: AbstractTelemetryProcessor,
        game_type_getter,
    ) -> None:
        self._processor = processor
        self._game_type_getter = game_type_getter   # callable returning "FM"|"FH"

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        source = SourceInfo(
            address=addr[0],
            port=addr[1],
            game_type=self._game_type_getter(),
        )
        # Fire-and-forget — schedule the coroutine on the running loop
        asyncio.get_event_loop().create_task(
            self._processor.process_raw_packet(data, source)
        )

    def error_received(self, exc: Exception) -> None:
        logger.warning("UDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        logger.info("UDP socket closed.")


async def start_udp_listener(
    host: str,
    port: int,
    processor: AbstractTelemetryProcessor,
    game_type_getter,
) -> asyncio.BaseTransport:
    """
    Bind a UDP socket and return the transport handle.

    Call this once at FastAPI startup.  The returned transport can be used to
    close the socket on shutdown.
    """
    loop = asyncio.get_event_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _UDPListenerProtocol(processor, game_type_getter),
        local_addr=(host, port),
    )
    logger.info("UDP telemetry listener started on %s:%d", host, port)
    return transport


# Avoid NameError for struct in except clause
import struct  # noqa: E402
