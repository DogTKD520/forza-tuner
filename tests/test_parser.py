"""
Tests for ForzaPacketParser.

Uses synthetically constructed binary payloads so no live game connection
is needed.  Each test verifies a specific field after a round-trip through
struct.pack → parse → TelemetryFrame.
"""

import struct
import pytest

from app.ingestion.parser import (
    ForzaPacketParser,
    TelemetryFrame,
    _SLED_STRUCT,
    _DASH_STRUCT,
    _FM_TRIZONE_STRUCT,
    _FM_MIN_SIZE,
    _FH_MIN_SIZE,
)


def _build_fm_packet(
    speed: float = 50.0,
    throttle: int = 200,
    brake: int = 0,
    steer: int = 0,
    boost: float = 0.5,
    suspension: tuple = (0.5, 0.5, 0.5, 0.5),
    trizone_temps: tuple = (80.0,) * 12,
) -> bytes:
    """Build a minimal but valid FM-format UDP packet."""
    # Build sled block
    sled_values = [
        1,           # is_race_on
        1000,        # timestamp_ms
        0.1, 0.0, 0.0,  # accel xyz
        0.0, 0.0, 0.0,  # vel xyz
        0.0, 0.0, 0.0,  # pos xyz
        0.0, 0.0, 0.0,  # roll xyz
        0.0,         # norm_driving_line
        0.0,         # norm_ai_brake
        speed,       # speed m/s
        0.0,         # power
        0.0,         # torque
        80.0, 80.0, 80.0, 80.0,   # tire temps (single, FH only)
        boost,       # boost
        0.5,         # fuel
        0.0, 0.0, 0.0, 0.0,      # dist/best/last/cur lap
        0.0,         # cur_race
        1,           # lap_no uint16
        1,           # race_pos uint16
        throttle,    # accel pedal
        brake,       # brake pedal
        0,           # clutch
        0,           # hand_brake
        1,           # gear
        steer,       # steer
        0,           # dup norm_driving_line
        0,           # dup ai_brake
    ]
    sled_bytes = _SLED_STRUCT.pack(*sled_values)

    # Build dash block — suspension at indices 26-29, wheel speed 34-37
    dash_values = [
        0.0, 0.0, 0.0,       # pos xyz
        speed, 0.0, 0.0,     # speed/power/torque
        80.0, 80.0, 80.0, 80.0,  # tire temps
        0.0, 0.0, 0.0, 0.0,  # boost/fuel/dist/best
        0.0, 0.0, 0.0, 0.0,  # last/cur/race/lap
        0.0, 0.0, 0.0, 0.0,  # pos/accel/brake/clutch
        0.0, 0.0, 0.0, 0.0,  # hbrake/gear/steer/unk
        *suspension,          # [26-29] normalized_suspension FL FR RL RR
        0.0, 0.0, 0.0, 0.0,  # slip ratio
        20.0, 20.0, 20.0, 20.0,  # [34-37] wheel rotation speed
        0.0, 0.0, 0.0, 0.0,  # slip angle
        0.0, 0.0, 0.0, 0.0,  # combined slip
        0.0, 0.0, 0.0, 0.0,  # susp travel meters
        123,                  # car ordinal
        4,                    # car class
        800,                  # car PI
        0, 4,                 # drivetrain / cylinders
    ]
    dash_bytes = _DASH_STRUCT.pack(*dash_values)
    trizone_bytes = _FM_TRIZONE_STRUCT.pack(*trizone_temps)

    return sled_bytes + dash_bytes + trizone_bytes


def _build_fh_packet(speed: float = 30.0) -> bytes:
    """Build a minimal FH packet (no trizone, pad to FH min size)."""
    packet = _build_fm_packet(speed=speed)
    # FH packets are the sled + dash blocks only (no trizone suffix)
    fh_data = packet[:len(packet) - _FM_TRIZONE_STRUCT.size]
    # Pad to FH expected minimum if needed
    if len(fh_data) < _FH_MIN_SIZE:
        fh_data += b'\x00' * (_FH_MIN_SIZE - len(fh_data))
    return fh_data


class TestForzaPacketParser:
    def setup_method(self):
        self.parser = ForzaPacketParser()

    def test_fm_speed_parsed_correctly(self):
        packet = _build_fm_packet(speed=55.6)
        frame = self.parser.parse(packet, "FM")
        assert abs(frame.speed_mps - 55.6) < 0.01

    def test_fm_throttle_normalised_to_0_to_1(self):
        packet = _build_fm_packet(throttle=255)
        frame = self.parser.parse(packet, "FM")
        assert abs(frame.throttle - 1.0) < 0.01

    def test_fm_brake_zero(self):
        packet = _build_fm_packet(brake=0)
        frame = self.parser.parse(packet, "FM")
        assert frame.brake == pytest.approx(0.0, abs=0.01)

    def test_fm_trizone_temps_parsed_per_corner(self):
        # FL inner=100, FL center=80, FL outer=60, rest 80
        trizone = (100.0, 80.0, 60.0, *([80.0] * 9))
        packet = _build_fm_packet(trizone_temps=trizone)
        frame = self.parser.parse(packet, "FM")
        assert frame.tire_temp_fl[0] == pytest.approx(100.0, abs=0.1)
        assert frame.tire_temp_fl[1] == pytest.approx(80.0, abs=0.1)
        assert frame.tire_temp_fl[2] == pytest.approx(60.0, abs=0.1)

    def test_fm_suspension_travel_values(self):
        packet = _build_fm_packet(suspension=(0.75, 0.80, 0.65, 0.70))
        frame = self.parser.parse(packet, "FM")
        assert frame.suspension_fl == pytest.approx(0.75, abs=0.01)
        assert frame.suspension_fr == pytest.approx(0.80, abs=0.01)

    def test_fm_packet_too_short_raises_value_error(self):
        with pytest.raises(ValueError, match="FM packet too short"):
            self.parser.parse(b'\x00' * 100, "FM")

    def test_fh_speed_parsed_correctly(self):
        packet = _build_fh_packet(speed=25.0)
        frame = self.parser.parse(packet, "FH")
        assert abs(frame.speed_mps - 25.0) < 0.1

    def test_fh_single_temp_replicated_across_zones(self):
        """FH only supplies one temp per tyre — all three zones should match."""
        packet = _build_fh_packet()
        frame = self.parser.parse(packet, "FH")
        # All zones should be the same value (replicated from sled block)
        assert frame.tire_temp_fl[0] == frame.tire_temp_fl[1] == frame.tire_temp_fl[2]

    def test_fh_packet_too_short_raises_value_error(self):
        with pytest.raises(ValueError, match="FH packet too short"):
            self.parser.parse(b'\x00' * 50, "FH")

    def test_game_type_set_on_frame(self):
        fm_packet = _build_fm_packet()
        frame = self.parser.parse(fm_packet, "FM")
        assert frame.game_type == "FM"
