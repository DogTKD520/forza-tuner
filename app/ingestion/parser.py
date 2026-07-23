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
    # Each corner: [inner, center, outer]  (Motorsport format provides all three)
    tire_temp_fl: list[float]   # [inner, center, outer]
    tire_temp_fr: list[float]
    tire_temp_rl: list[float]
    tire_temp_rr: list[float]

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

    # --- Meta ---
    gear: int
    is_race_on: bool
    game_type: str            # "FM" | "FH"


# ---------------------------------------------------------------------------
# Struct layouts
# ---------------------------------------------------------------------------

# Common fields shared by both FM and FH.
# Format string uses little-endian (<) throughout.
# Field order matches the official Forza Dash UDP output spec.
_COMMON_FMT = "<"  # we build incrementally below

# Offsets (byte positions) for each group — documented for maintainability.
# Sled block: bytes 0–231
# Dash block: bytes 232–311 (FM) / 232–324 (FH)

_SLED_STRUCT = struct.Struct(
    "<"
    "i"        # [0]  is_race_on          int32
    "I"        # [1]  timestamp_ms        uint32
    "3f"       # [2-4] EngineMaxRpm, EngineIdleRpm, CurrentEngineRpm
    "9f"       # [5-13] accel xyz, vel xyz, roll/pitch/yaw
    "f"        # [14] normalized_driving_line (ignored)
    "f"        # [15] normalized_ai_brake_difference (ignored)
    "f"        # [16] speed (m/s)
    "f"        # [17] power (watts, ignored)
    "f"        # [18] torque (nm, ignored)
    "4f"       # [19-22] tire_temp_FL/FR/RL/RR  (single-value surface temp in FH sled)
    "f"        # [23] boost
    "f"        # [24] fuel (ignored)
    "f"        # [25] distance_traveled (ignored)
    "f"        # [26] best_lap_time (ignored)
    "f"        # [27] last_lap_time (ignored)
    "f"        # [28] cur_lap_time (ignored)
    "f"        # [29] cur_race_time (ignored)
    "H"        # [30] lap_no  uint16
    "H"        # [31] race_position uint16
    "B"        # [32] accel pedal 0-255
    "B"        # [33] brake pedal 0-255
    "B"        # [34] clutch 0-255 (ignored)
    "B"        # [35] hand_brake (ignored)
    "B"        # [36] gear (ignored)
    "b"        # [37] steer -127 to 127
    "b"        # [38] normalized_driving_line (ignored, repeated)
    "b"        # [39] normalized_ai_brake_difference (ignored, repeated)
)

# Dash extension block — appended after the sled block in both FM and FH.
_DASH_STRUCT = struct.Struct(
    "<"
    "f"        # [0]  position_x (ignored)
    "f"        # [1]  position_y (ignored)
    "f"        # [2]  position_z (ignored)
    "f"        # [3]  speed (duplicate, ignored)
    "f"        # [4]  power (ignored)
    "f"        # [5]  torque (ignored)
    "4f"       # [6-9]  tire_temp_FL/FR/RL/RR (duplicate surface temps)
    "4f"       # [10-13] boost/fuel/dist/bestlap (ignored)
    "4f"       # [14-17] last_lap/cur_lap/cur_race/lap_no (ignored)
    "4f"       # [18-21] race_position/accel/brake/clutch (ignored)
    "4f"       # [22-25] hand_brake/gear/steer/unk (ignored)
    "4f"       # [26-29] normalized_suspension_travel FL/FR/RL/RR  ← KEY
    "4f"       # [30-33] tire_slip_ratio FL/FR/RL/RR (ignored)
    "4f"       # [34-37] wheel_rotation_speed FL/FR/RL/RR  ← KEY
    "4f"       # [38-41] tire_slip_angle FL/FR/RL/RR (ignored)
    "4f"       # [42-45] tire_combined_slip FL/FR/RL/RR (ignored)
    "4f"       # [46-49] suspension_travel_meters FL/FR/RL/RR (ignored)
    "i"        # [50] car_ordinal
    "i"        # [51] car_class
    "i"        # [52] car_PI
    "i"        # [53] drivetrain_type (ignored)
    "i"        # [54] num_cylinders (ignored)
)

# FM additionally includes tri-zone tyre temps after the dash block
# Format: 12 floats = [FL_inner, FL_center, FL_outer, FR_inner, ...]
_FM_TRIZONE_STRUCT = struct.Struct("<12f")

_FM_SLED_SIZE = _SLED_STRUCT.size   # 232 bytes
_FM_DASH_OFFSET = _FM_SLED_SIZE      # 232
_FM_DASH_SIZE = _DASH_STRUCT.size
_FM_TRIZONE_OFFSET = _FM_DASH_OFFSET + _FM_DASH_SIZE
_FM_MIN_SIZE = _FM_TRIZONE_OFFSET + _FM_TRIZONE_STRUCT.size   # ~311 bytes

_FH_MIN_SIZE = _FM_DASH_OFFSET + _DASH_STRUCT.size   # 324 — no trizone


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class ForzaPacketParser:
    """
    Converts raw UDP bytes into a `TelemetryFrame`.

    Raises `ValueError` for packets that are too short to parse safely.
    """

    def parse(
        self, raw_bytes: bytes, game_type: Literal["FM", "FH"]
    ) -> TelemetryFrame:
        if game_type == "FM":
            return self._parse_fm(raw_bytes)
        return self._parse_fh(raw_bytes)

    # ------------------------------------------------------------------
    # Forza Motorsport
    # ------------------------------------------------------------------

    def _parse_fm(self, data: bytes) -> TelemetryFrame:
        if len(data) < _FM_MIN_SIZE:
            raise ValueError(
                f"FM packet too short: got {len(data)} bytes, need {_FM_MIN_SIZE}"
            )

        sled = _SLED_STRUCT.unpack_from(data, 0)
        dash = _DASH_STRUCT.unpack_from(data, _FM_DASH_OFFSET)
        trizone = _FM_TRIZONE_STRUCT.unpack_from(data, _FM_TRIZONE_OFFSET)

        # trizone: FL_i, FL_c, FL_o, FR_i, FR_c, FR_o, RL_i, RL_c, RL_o, RR_i, RR_c, RR_o
        tire_temps = [
            list(trizone[0:3]),
            list(trizone[3:6]),
            list(trizone[6:9]),
            list(trizone[9:12]),
        ]

        return self._build_frame(sled, dash, tire_temps, "FM")

    # ------------------------------------------------------------------
    # Forza Horizon
    # ------------------------------------------------------------------

    def _parse_fh(self, data: bytes) -> TelemetryFrame:
        if len(data) < _FH_MIN_SIZE:
            raise ValueError(
                f"FH packet too short: got {len(data)} bytes, need {_FH_MIN_SIZE}"
            )

        sled = _SLED_STRUCT.unpack_from(data, 0)
        dash = _DASH_STRUCT.unpack_from(data, _FM_DASH_OFFSET)

        # FH only provides a single surface temperature per tyre — replicate
        # it across all three zones so downstream code stays identical.
        sled_temps = sled[19:23]  # FL, FR, RL, RR single values
        tire_temps = [[t, t, t] for t in sled_temps]

        return self._build_frame(sled, dash, tire_temps, "FH")

    # ------------------------------------------------------------------
    # Shared construction
    # ------------------------------------------------------------------

    def _build_frame(
        self,
        sled: tuple,
        dash: tuple,
        tire_temps: list[list[float]],
        game_type: str,
    ) -> TelemetryFrame:
        return TelemetryFrame(
            is_race_on=bool(sled[0]),
            speed_mps=sled[16],
            rpm=sled[4],
            boost=sled[23],
            throttle=sled[32] / 255.0,
            brake=sled[33] / 255.0,
            steer=sled[37] / 127.0,
            accel_x=sled[5],
            accel_y=sled[6],
            accel_z=sled[7],
            tire_temp_fl=tire_temps[0],
            tire_temp_fr=tire_temps[1],
            tire_temp_rl=tire_temps[2],
            tire_temp_rr=tire_temps[3],
            suspension_fl=dash[26],
            suspension_fr=dash[27],
            suspension_rl=dash[28],
            suspension_rr=dash[29],
            wheel_speed_fl=dash[34],
            wheel_speed_fr=dash[35],
            wheel_speed_rl=dash[36],
            wheel_speed_rr=dash[37],
            tire_slip_ratio_fl=dash[30],
            tire_slip_ratio_fr=dash[31],
            tire_slip_ratio_rl=dash[32],
            tire_slip_ratio_rr=dash[33],
            tire_slip_angle_fl=dash[38],
            tire_slip_angle_fr=dash[39],
            tire_slip_angle_rl=dash[40],
            tire_slip_angle_rr=dash[41],
            gear=sled[36],
            game_type=game_type,
        )
