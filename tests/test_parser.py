"""
Tests for ForzaPacketParser.

Uses synthetically constructed binary payloads so no live game connection
is needed.  Each test verifies a specific field after a round-trip through
raw struct.pack -> parse -> TelemetryFrame.
"""

import struct
import pytest

from app.ingestion.parser import (
    ForzaPacketParser,
    _SLED_STRUCT,
    _DASH_STRUCT,
)

# Reference offset tables independent of parser.py
SLED_FMT = (
    "<"
    "i"        # 0
    "I"        # 4
    "15f"      # 8
    "4f"       # 68: NormalizedSuspensionTravel
    "4f"       # 84: TireSlipRatio
    "4f"       # 100: WheelRotationSpeed
    "4i"       # 116: WheelOnRumbleStrip (s32)
    "4f"       # 132: WheelInPuddleDepth
    "4f"       # 148: SurfaceRumble
    "4f"       # 164: TireSlipAngle
    "4f"       # 180: TireCombinedSlip
    "4f"       # 196: SuspensionTravelMeters
    "5i"       # 212: Car stats
) # 232 bytes total

DASH_FMT = (
    "<"
    "3f"       # 0 (232)
    "f"        # 12 (244): Speed
    "f"        # 16 (248)
    "f"        # 20 (252)
    "4f"       # 24 (256): TireTemp
    "f"        # 40 (272): Boost
    "f"        # 44
    "f"        # 48
    "f"        # 52
    "f"        # 56
    "f"        # 60
    "f"        # 64
    "H"        # 68
    "B"        # 70
    "B"        # 71 (303): Accel
    "B"        # 72 (304): Brake
    "B"        # 73
    "B"        # 74
    "B"        # 75 (307): Gear
    "b"        # 76 (308): Steer
    "b"        # 77
    "b"        # 78
) # 75 bytes (+4 pad = 79 bytes)

def _build_fm_packet(
    speed: float = 50.0,
    throttle: int = 200,
    brake: int = 0,
    steer: int = 0,
    boost: float = 0.5,
    suspension: tuple = (0.5, 0.5, 0.5, 0.5),
    tire_temps_f: tuple = (212.0, 212.0, 212.0, 212.0), # 100 C
) -> bytes:
    """Build a minimal but valid FM-format UDP packet using raw struct strings."""
    sled_values = [
        1,           # is_race_on
        1000,        # timestamp_ms
    ]
    sled_values.extend([0.0] * 15)  # 15 floats
    sled_values.extend(suspension)  # 4 floats: NormSusp FL/FR/RL/RR
    sled_values.extend([0.0] * 8)   # SlipRatio, WheelRot
    sled_values.extend([0] * 4)     # Rumble (4i)
    sled_values.extend([0.0] * 16)  # Puddle, Surface, SlipAngle, CombSlip
    sled_values.extend([0.0] * 4)   # SuspMeters
    sled_values.extend([123, 4, 800, 0, 4])  # 5 ints (car stats)
    
    sled_bytes = struct.pack(SLED_FMT, *sled_values)

    dash_values = [
        0.0, 0.0, 0.0,       # pos xyz
        speed,               # speed
        0.0, 0.0,            # power, torque
    ]
    dash_values.extend(tire_temps_f)  # 4 floats: tire temps
    dash_values.extend([boost, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    dash_values.extend([
        1,           # lap_no uint16
        1,           # race_pos uint8
        throttle,    # accel pedal
        brake,       # brake pedal
        0,           # clutch
        0,           # hand_brake
        1,           # gear
        steer,       # steer
        0,           # norm_driving_line
        0,           # ai_brake
    ])
    dash_bytes = struct.pack(DASH_FMT, *dash_values)
    
    # Base FM is 311 bytes, which is 232 + 79
    # Struct packing gives exactly 232 + 79.
    packet = sled_bytes + dash_bytes
    assert len(packet) == 311
    return packet

def _build_fm2023_packet(speed: float = 50.0) -> bytes:
    # 331 bytes
    packet = _build_fm_packet(speed=speed)
    # Add 20 bytes tail
    return packet + (b'\x00' * 20)

def _build_fh_packet(speed: float = 30.0) -> bytes:
    """Build a minimal FH packet (with 12 byte gap)."""
    packet_fm = _build_fm_packet(speed=speed)
    sled_bytes = packet_fm[:232]
    dash_bytes = packet_fm[232:232+79]  # DASH struct is 79 bytes
    
    fh_data = sled_bytes + (b'\x00' * 12) + dash_bytes
    # Pad to FH expected minimum (324) - FH packets don't have padding usually, they just have 323 or 324? 232 + 12 + 79 = 323 bytes. The spec says 324 bytes. We pad by 1.
    fh_data += b'\x00' * 1
    assert len(fh_data) == 324
    return fh_data

class TestForzaPacketParser:
    def setup_method(self):
        self.parser = ForzaPacketParser()

    def test_module_load_struct_sizes(self):
        # Reference confirmed by csutorasa/go-forza-telemetry & 0x20F/forza-telemetry
        assert _SLED_STRUCT.size == 232
        assert _DASH_STRUCT.size == 79

    def test_fm_speed_parsed_correctly(self):
        packet = _build_fm_packet(speed=55.6)
        frame = self.parser.parse(packet)
        assert abs(frame.speed_mps - 55.6) < 0.01
        assert frame.game_type == "FM"

    def test_fm2023_packet_parsed_correctly(self):
        packet = _build_fm2023_packet(speed=60.0)
        frame = self.parser.parse(packet)
        assert abs(frame.speed_mps - 60.0) < 0.01
        assert frame.game_type == "FM2023"

    def test_fh_packet_parsed_correctly(self):
        packet = _build_fh_packet(speed=40.0)
        frame = self.parser.parse(packet)
        assert abs(frame.speed_mps - 40.0) < 0.01
        assert frame.game_type == "FH"

    def test_unknown_packet_length_raises(self):
        with pytest.raises(ValueError, match="Unknown packet length"):
            self.parser.parse(b'\x00' * 100)

    def test_fm_tire_temps_fahrenheit_to_celsius(self):
        # We supply 4 tire temps in Fahrenheit (212 F = 100 C)
        packet = _build_fm_packet(tire_temps_f=(212.0, 32.0, -40.0, 122.0))
        frame = self.parser.parse(packet)
        assert frame.tire_temp_fl == pytest.approx(100.0, abs=0.1)
        assert frame.tire_temp_fr == pytest.approx(0.0, abs=0.1)
        assert frame.tire_temp_rl == pytest.approx(-40.0, abs=0.1)
        assert frame.tire_temp_rr == pytest.approx(50.0, abs=0.1)

    def test_suspension_travel_values(self):
        packet = _build_fm_packet(suspension=(0.75, 0.80, 0.65, 0.70))
        frame = self.parser.parse(packet)
        assert frame.suspension_fl == pytest.approx(0.75, abs=0.01)
        assert frame.suspension_fr == pytest.approx(0.80, abs=0.01)
        assert frame.suspension_rl == pytest.approx(0.65, abs=0.01)
        assert frame.suspension_rr == pytest.approx(0.70, abs=0.01)
