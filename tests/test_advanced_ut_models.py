"""Tests for multi-gate, TCG, and scan geometry models."""

from __future__ import annotations

import numpy as np

from app.model.gate_analyzer import GateAnalyzer, GateConfig
from app.model.scan_geometry import ScanGrid
from app.model.tcg import TcgPoint, TcgProfile


def _depth_to_time_us(depth_mm: float) -> float:
    return depth_mm


def test_gate_analyzer_detects_three_independent_gates() -> None:
    time_axis = np.linspace(0.0, 100.0, 1001)
    envelope = np.zeros_like(time_axis)
    envelope[np.argmin(np.abs(time_axis - 10.0))] = 0.4
    envelope[np.argmin(np.abs(time_axis - 40.0))] = 0.9
    envelope[np.argmin(np.abs(time_axis - 80.0))] = 0.7
    gates = [
        GateConfig("A", "闸门A", 5.0, 10.0, 0.5),
        GateConfig("B", "闸门B", 30.0, 20.0, 0.5),
        GateConfig("C", "闸门C", 70.0, 20.0, 0.5),
    ]

    results = GateAnalyzer.analyze(time_axis, envelope, gates, _depth_to_time_us)

    assert results["A"].triggered is False
    assert results["B"].triggered is True
    assert results["C"].triggered is True
    assert results["B"].peak_amplitude > results["A"].peak_amplitude


def test_tcg_profile_interpolates_and_applies_gain() -> None:
    profile = TcgProfile(
        [
            TcgPoint(0.0, 0.0),
            TcgPoint(50.0, 6.0),
            TcgPoint(100.0, 12.0),
        ]
    )

    assert profile.gain_at(25.0) == 3.0

    time_axis = np.array([0.0, 10.0, 20.0], dtype=np.float32)
    signal = np.array([1.0, 1.0, 1.0], dtype=np.float32)
    compensated = profile.apply(signal, time_axis, sound_velocity_mps=5900.0)

    assert compensated[1] > compensated[0]
    assert compensated[2] > compensated[1]


def test_scan_grid_maps_raster_positions_and_builds_c_scan() -> None:
    grid = ScanGrid(rows=2, columns=3, row_spacing_mm=10.0, column_spacing_mm=5.0)

    assert grid.position_for_index(0) == (0.0, 0.0)
    assert grid.position_for_index(4) == (5.0, 10.0)

    c_scan = grid.build_c_scan([(0, 0.2), (1, 0.7), (5, 0.4)])

    assert c_scan.shape == (2, 3)
    assert c_scan[0, 1] == 0.7
    assert c_scan[1, 2] == 0.4
