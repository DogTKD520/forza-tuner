"""
Forza UDP packet parser.

Supports two game profiles:
  FM — Forza Motorsport  (Car Dash format, 311 bytes, floats at known offsets)
  FH — Forza Horizon     (Car Dash format, 324 bytes, identical layout + extras)

Both games output a superset of the "Sled" format.  We extract the fields we
need for tuning analysis and normalise them into a `TelemetryFrame` dataclass.

Byte-offset references:
  https://support.forzamotorsport.net/hc/en-us/articles/21742934024211
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Literal


# ---------------------------------------------------------------------------
# Domain model — one frame of telemetry data
# ---------------------------------------------------------------------------

@dataclass
class TelemetryFrame:
    # --- Kinematics ---
    speed_mps: float          # metres per second (convert to kph / mph in UI)
    rpm: float
    boost: float              # manifold pressure (not used in tuning, handy for UI)

    # --- Controls ---
    throttle: float           # 0–255 byte, normalised to 0.0–1.0
    brake: float
    steer: float              # -127 (full left) to 127 (full right), normalised to -1.0–1.0

    # --- G-forces ---
    accel_x: float            # lateral (left/right)  m/s²
    accel_y: float            # longitudinal (fwd/bwd) m/s²
    accel_z: float            # vertical               m/s²

    # --- Suspension travel (0.0 = fully extended, 1.0 = fully compressed) ---
    suspension_fl: float
    suspension_fr: float
    suspension_rl: float
    suspension_rr: float

    # --- Tyre surface temperatures (°C) ---
    tire_temp_fl: float
    tire_temp_fr: float
    tire_temp_rl: float
    tire_temp_rr: float

    # --- Wheel rotation speed (rad/s) ---
    wheel_speed_fl: float
    wheel_speed_fr: float
    wheel_speed_rl: float
    wheel_speed_rr: float

    # --- Tire Slip ---
    tire_slip_ratio_fl: float
    tire_slip_ratio_fr: float
    tire_slip_ratio_rl: float
    tire_slip_ratio_rr: float

    tire_slip_angle_fl: float
    tire_slip_angle_fr: float
    tire_slip_angle_rl: float
    tire_slip_angle_rr: float

    tire_combined_slip_fl: float
    tire_combined_slip_fr: float
    tire_combined_slip_rl: float
    tire_combined_slip_rr: float

    # --- Meta ---
    gear: int
    is_race_on: bool
    game_type: str            # "FM" | "FH" | "FM2023"


# ---------------------------------------------------------------------------
# Struct layouts
# Ground Truth References:
# csutorasa/go-forza-telemetry, 0x20F/forza-telemetry, richstokes/Forza-data-tools
# ---------------------------------------------------------------------------

# Sled block: bytes 0-231 (Shared by both FM and FH)
_SLED_STRUCT = struct.Struct(
    "<"
    "i"        # [0]  is_race_on
    "I"        # [1]  timestamp_ms
    "15f"      # [2-16] EngineMax, EngineIdle, EngineCurrent, Accel X/Y/Z, Vel X/Y/Z, AngVel X/Y/Z, Yaw/Pitch/Roll
    "4f"       # [17-20] normalized_suspension_travel FL/FR/RL/RR
    "4f"       # [21-24] tire_slip_ratio FL/FR/RL/RR
    "4f"       # [25-28] wheel_rotation_speed FL/FR/RL/RR
    "4i"       # [29-32] wheel_on_rumble_strip FL/FR/RL/RR
    "4f"       # [33-36] wheel_in_puddle FL/FR/RL/RR
    "4f"       # [37-40] surface_rumble FL/FR/RL/RR
    "4f"       # [41-44] tire_slip_angle FL/FR/RL/RR
    "4f"       # [45-48] tire_combined_slip FL/FR/RL/RR
    "4f"       # [49-52] suspension_travel_meters FL/FR/RL/RR
    "5i"       # [53-57] car_ordinal, car_class, car_pi, drivetrain_type, num_cylinders
)

# Dash block: Appended after Sled block.
_DASH_STRUCT = struct.Struct(
    "<"
    "3f"       # [0-2] position_x, position_y, position_z
    "f"        # [3] speed
    "f"        # [4] power
    "f"        # [5] torque
    "4f"       # [6-9] tire_temp_FL/FR/RL/RR
    "f"        # [10] boost
    "f"        # [11] fuel
    "f"        # [12] distance_traveled
    "f"        # [13] best_lap_time
    "f"        # [14] last_lap_time
    "f"        # [15] cur_lap_time
    "f"        # [16] cur_race_time
    "H"        # [17] lap_no
    "B"        # [18] race_position
    "B"        # [19] accel pedal 0-255
    "B"        # [20] brake pedal 0-255
    "B"        # [21] clutch 0-255
    "B"        # [22] hand_brake
    "B"        # [23] gear
    "b"        # [24] steer -127 to 127
    "b"        # [25] normalized_driving_line
    "b"        # [26] normalized_ai_brake_difference
)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class ForzaPacketParser:
    """
    Converts raw UDP bytes into a `TelemetryFrame`.

    Raises `ValueError` for packets with unknown lengths.
    """

    def parse(
        self, raw_bytes: bytes, game_type_hint: Literal["FM", "FH"] = "FM"
    ) -> TelemetryFrame:
        # Debug: Dump first FH packet to logs
        if not hasattr(self, "_debug_dumped") and len(raw_bytes) == 324:
            import logging
            logging.getLogger(__name__).info("RAW FH PACKET (HEX): %s", raw_bytes.hex())
            self._debug_dumped = True

        # Dispatch by precise packet length
        pkt_len = len(raw_bytes)
        
        if pkt_len == 311:
            return self._parse_fm(raw_bytes, "FM")
        elif pkt_len == 331:
            return self._parse_fm(raw_bytes, "FM2023")
        elif pkt_len == 324:
            return self._parse_fh(raw_bytes)
        else:
            raise ValueError(f"Unknown packet length: {pkt_len}")

    # ------------------------------------------------------------------
    # Forza Motorsport
    # ------------------------------------------------------------------

    def _parse_fm(self, data: bytes, game_type: str) -> TelemetryFrame:
        sled = _SLED_STRUCT.unpack_from(data, 0)
        # Dash block starts immediately at 232
        dash_offset = 232
        dash = _DASH_STRUCT.unpack_from(data, dash_offset)
        
        # FM: suspension travel is valid at sled[17-20] (byte offset 68)
        suspension = sled[17:21]
        
        # Temps are in Fahrenheit, convert to Celsius
        tire_temps = [(t - 32.0) * 5.0 / 9.0 for t in dash[6:10]]

        return self._build_frame(sled, dash, suspension, tire_temps, game_type)

    # ------------------------------------------------------------------
    # Forza Horizon
    # ------------------------------------------------------------------

    def _parse_fh(self, data: bytes) -> TelemetryFrame:
        sled = _SLED_STRUCT.unpack_from(data, 0)
        # FH: Dash block starts at 244 (skipping the 12-byte padding)
        dash_offset = 244
        dash = _DASH_STRUCT.unpack_from(data, dash_offset)

        # FH: normalized_suspension (sled[17]) is broken. We use suspension_travel_meters
        # which is normally at byte 196, but shifted by 12 bytes in FH.
        susp_offset = 196 + 12
        suspension = struct.unpack_from("<4f", data, susp_offset)

        # Temps are in Fahrenheit, convert to Celsius
        tire_temps = [(t - 32.0) * 5.0 / 9.0 for t in dash[6:10]]

        return self._build_frame(sled, dash, suspension, tire_temps, "FH")

    # ------------------------------------------------------------------
    # Shared construction
    # ------------------------------------------------------------------

    def _build_frame(
        self,
        sled: tuple,
        dash: tuple,
        suspension: tuple[float, float, float, float] | list[float],
        tire_temps: list[float],
        game_type: str,
    ) -> TelemetryFrame:
        return TelemetryFrame(
            is_race_on=bool(sled[0]),
            speed_mps=dash[3],
            rpm=sled[4],
            boost=dash[10],
            throttle=dash[19] / 255.0,
            brake=dash[20] / 255.0,
            steer=dash[24] / 127.0,
            accel_x=sled[5],
            accel_y=sled[6],
            accel_z=sled[7],
            tire_temp_fl=tire_temps[0],
            tire_temp_fr=tire_temps[1],
            tire_temp_rl=tire_temps[2],
            tire_temp_rr=tire_temps[3],
            suspension_fl=suspension[0],
            suspension_fr=suspension[1],
            suspension_rl=suspension[2],
            suspension_rr=suspension[3],
            wheel_speed_fl=sled[25],
            wheel_speed_fr=sled[26],
            wheel_speed_rl=sled[27],
            wheel_speed_rr=sled[28],
            tire_slip_ratio_fl=sled[21],
            tire_slip_ratio_fr=sled[22],
            tire_slip_ratio_rl=sled[23],
            tire_slip_ratio_rr=sled[24],
            tire_slip_angle_fl=sled[41],
            tire_slip_angle_fr=sled[42],
            tire_slip_angle_rl=sled[43],
            tire_slip_angle_rr=sled[44],
            tire_combined_slip_fl=sled[45],
            tire_combined_slip_fr=sled[46],
            tire_combined_slip_rl=sled[47],
            tire_combined_slip_rr=sled[48],
            gear=dash[23],
            game_type=game_type,
        )
