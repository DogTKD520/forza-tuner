import sys
import pytest
from app.ingestion.parser import TelemetryFrame
from app.ingestion.session_aggregator import SessionAggregator, _CornerStats

def build_frame(temp=80.0, ratio=0.1, angle=0.05, combined=0.08, travel=0.5, speed=20.0, lat_g=0.5):
    return TelemetryFrame(
        game_type="FH",
        speed_mps=speed,
        rpm=5000,
        gear=3,
        boost=0,
        throttle=0.5,
        brake=0,
        steer=0,
        accel_x=lat_g * 9.81,
        accel_y=0,
        accel_z=0,
        suspension_fl=travel,
        suspension_fr=travel,
        suspension_rl=travel,
        suspension_rr=travel,
        tire_temp_fl=temp,
        tire_temp_fr=temp,
        tire_temp_rl=temp,
        tire_temp_rr=temp,
        tire_slip_ratio_fl=ratio,
        tire_slip_ratio_fr=ratio,
        tire_slip_ratio_rl=ratio,
        tire_slip_ratio_rr=ratio,
        tire_slip_angle_fl=angle,
        tire_slip_angle_fr=angle,
        tire_slip_angle_rl=angle,
        tire_slip_angle_rr=angle,
        tire_combined_slip_fl=combined,
        tire_combined_slip_fr=combined,
        tire_combined_slip_rl=combined,
        tire_combined_slip_rr=combined,
        wheel_speed_fl=0,
        wheel_speed_fr=0,
        wheel_speed_rl=0,
        wheel_speed_rr=0,
        is_race_on=True,
    )

def test_empty_session_summary():
    aggregator = SessionAggregator()
    summary = aggregator.get_summary()
    assert summary["total_frames"] == 0
    assert summary["avg_speed_mps"] == 0.0
    assert summary["avg_lateral_g"] == 0.0
    assert len(summary["corners"]) == 0

def test_session_averages_and_maxima():
    aggregator = SessionAggregator()
    # Frame 1
    aggregator.ingest(build_frame(temp=70.0, angle=0.10, travel=0.4, speed=10.0, lat_g=0.5))
    # Frame 2
    aggregator.ingest(build_frame(temp=90.0, angle=0.20, travel=0.8, speed=30.0, lat_g=1.5))
    
    summary = aggregator.get_summary()
    assert summary["total_frames"] == 2
    assert summary["avg_speed_mps"] == 20.0
    assert summary["avg_lateral_g"] == pytest.approx(1.0 * 9.81)
    
    fl = summary["corners"]["fl"]
    assert fl["avg_temp"] == 80.0
    assert fl["avg_slip_angle"] == pytest.approx(0.15)
    assert fl["max_slip_angle"] == 0.20
    assert fl["avg_suspension_travel"] == pytest.approx(0.6)
    assert fl["peak_suspension_travel"] == 0.8
    assert summary["front_avg_suspension_travel"] == pytest.approx(0.6)

def test_bottom_out_ratio():
    aggregator = SessionAggregator()
    # Bottom out threshold is 0.95
    aggregator.ingest(build_frame(travel=0.96))
    aggregator.ingest(build_frame(travel=0.50))
    aggregator.ingest(build_frame(travel=0.98))
    
    summary = aggregator.get_summary()
    assert summary["corners"]["fl"]["bottom_out_ratio"] == pytest.approx(2/3)

def test_memory_does_not_grow_per_frame():
    aggregator = SessionAggregator()
    aggregator.ingest(build_frame())
    size_after_one = sys.getsizeof(aggregator) + sum(sys.getsizeof(c) for c in aggregator._corners.values())
    
    for _ in range(100):
        aggregator.ingest(build_frame())
        
    size_after_many = sys.getsizeof(aggregator) + sum(sys.getsizeof(c) for c in aggregator._corners.values())
    
    # Internal list growth would dramatically increase size.
    assert size_after_one == size_after_many
