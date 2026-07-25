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

_SLED_FMT = (
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

_DASH_FMT = (
    "3f"       # [58-60] position_x, position_y, position_z
    "f"        # [61] speed
    "f"        # [62] power
    "f"        # [63] torque
    "4f"       # [64-67] tire_temp_FL/FR/RL/RR
    "f"        # [68] boost
    "f"        # [69] fuel
    "f"        # [70] distance_traveled
    "f"        # [71] best_lap_time
    "f"        # [72] last_lap_time
    "f"        # [73] cur_lap_time
    "f"        # [74] cur_race_time
    "H"        # [75] lap_no
    "B"        # [76] race_position
    "B"        # [77] accel pedal 0-255
    "B"        # [78] brake pedal 0-255
    "B"        # [79] clutch 0-255
    "B"        # [80] hand_brake
    "B"        # [81] gear
    "b"        # [82] steer -127 to 127
    "b"        # [83] normalized_driving_line
    "b"        # [84] normalized_ai_brake_difference
)

_FM_STRUCT = struct.Struct("<" + _SLED_FMT + _DASH_FMT)
_FH_STRUCT = struct.Struct("<" + _SLED_FMT + "12x" + _DASH_FMT)

_KEYS = (
    "is_race_on", "timestamp_ms",
    "engine_max_rpm", "engine_idle_rpm", "engine_current_rpm",
    "accel_x", "accel_y", "accel_z",
    "velocity_x", "velocity_y", "velocity_z",
    "angular_velocity_x", "angular_velocity_y", "angular_velocity_z",
    "yaw", "pitch", "roll",
    "normalized_suspension_travel_fl", "normalized_suspension_travel_fr", "normalized_suspension_travel_rl", "normalized_suspension_travel_rr",
    "tire_slip_ratio_fl", "tire_slip_ratio_fr", "tire_slip_ratio_rl", "tire_slip_ratio_rr",
    "wheel_rotation_speed_fl", "wheel_rotation_speed_fr", "wheel_rotation_speed_rl", "wheel_rotation_speed_rr",
    "wheel_on_rumble_strip_fl", "wheel_on_rumble_strip_fr", "wheel_on_rumble_strip_rl", "wheel_on_rumble_strip_rr",
    "wheel_in_puddle_depth_fl", "wheel_in_puddle_depth_fr", "wheel_in_puddle_depth_rl", "wheel_in_puddle_depth_rr",
    "surface_rumble_fl", "surface_rumble_fr", "surface_rumble_rl", "surface_rumble_rr",
    "tire_slip_angle_fl", "tire_slip_angle_fr", "tire_slip_angle_rl", "tire_slip_angle_rr",
    "tire_combined_slip_fl", "tire_combined_slip_fr", "tire_combined_slip_rl", "tire_combined_slip_rr",
    "suspension_travel_meters_fl", "suspension_travel_meters_fr", "suspension_travel_meters_rl", "suspension_travel_meters_rr",
    "car_ordinal", "car_class", "car_performance_index", "drivetrain_type", "num_cylinders",
    
    # Dash variables
    "position_x", "position_y", "position_z",
    "speed", "power", "torque",
    "tire_temp_fl", "tire_temp_fr", "tire_temp_rl", "tire_temp_rr",
    "boost", "fuel", "distance_traveled",
    "best_lap_time", "last_lap_time", "cur_lap_time", "cur_race_time",
    "lap_no", "race_position",
    "accel_pedal", "brake_pedal", "clutch", "hand_brake", "gear",
    "steer", "normalized_driving_line", "normalized_ai_brake_difference"
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
            return self._parse_and_build(raw_bytes, _FM_STRUCT, "FM")
        elif pkt_len == 331:
            return self._parse_and_build(raw_bytes, _FM_STRUCT, "FM2023")
        elif pkt_len == 324:
            return self._parse_and_build(raw_bytes, _FH_STRUCT, "FH")
        else:
            raise ValueError(f"Unknown packet length: {pkt_len}")

    def _parse_and_build(self, raw_bytes: bytes, struct_schema: struct.Struct, game_type: str) -> TelemetryFrame:
        unpacked = struct_schema.unpack_from(raw_bytes)
        data = dict(zip(_KEYS, unpacked))

        def c_temp(f: float) -> float:
            return (f - 32.0) * 5.0 / 9.0

        return TelemetryFrame(
            is_race_on=bool(data["is_race_on"]),
            speed_mps=data["speed"],
            rpm=data["engine_current_rpm"],
            boost=data["boost"],
            throttle=data["accel_pedal"] / 255.0,
            brake=data["brake_pedal"] / 255.0,
            steer=data["steer"] / 127.0,
            accel_x=data["accel_x"],
            accel_y=data["accel_y"],
            accel_z=data["accel_z"],
            tire_temp_fl=c_temp(data["tire_temp_fl"]),
            tire_temp_fr=c_temp(data["tire_temp_fr"]),
            tire_temp_rl=c_temp(data["tire_temp_rl"]),
            tire_temp_rr=c_temp(data["tire_temp_rr"]),
            suspension_fl=data["normalized_suspension_travel_fl"],
            suspension_fr=data["normalized_suspension_travel_fr"],
            suspension_rl=data["normalized_suspension_travel_rl"],
            suspension_rr=data["normalized_suspension_travel_rr"],
            wheel_speed_fl=data["wheel_rotation_speed_fl"],
            wheel_speed_fr=data["wheel_rotation_speed_fr"],
            wheel_speed_rl=data["wheel_rotation_speed_rl"],
            wheel_speed_rr=data["wheel_rotation_speed_rr"],
            tire_slip_ratio_fl=data["tire_slip_ratio_fl"],
            tire_slip_ratio_fr=data["tire_slip_ratio_fr"],
            tire_slip_ratio_rl=data["tire_slip_ratio_rl"],
            tire_slip_ratio_rr=data["tire_slip_ratio_rr"],
            tire_slip_angle_fl=data["tire_slip_angle_fl"],
            tire_slip_angle_fr=data["tire_slip_angle_fr"],
            tire_slip_angle_rl=data["tire_slip_angle_rl"],
            tire_slip_angle_rr=data["tire_slip_angle_rr"],
            tire_combined_slip_fl=data["tire_combined_slip_fl"],
            tire_combined_slip_fr=data["tire_combined_slip_fr"],
            tire_combined_slip_rl=data["tire_combined_slip_rl"],
            tire_combined_slip_rr=data["tire_combined_slip_rr"],
            gear=data["gear"],
            game_type=game_type,
        )
