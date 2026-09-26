"""Time-corrected gain profile models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class TcgPoint:
    """One depth/gain calibration point."""

    depth_mm: float
    gain_db: float


class TcgProfile:
    """Piecewise linear TCG profile."""

    def __init__(self, points: list[TcgPoint] | None = None) -> None:
        source = points or [TcgPoint(0.0, 0.0)]
        ordered = sorted(source, key=lambda point: point.depth_mm)
        if len({point.depth_mm for point in ordered}) != len(ordered):
            raise ValueError("TCG深度点不能重复")

        self.points = ordered
        self._depths = np.asarray([point.depth_mm for point in ordered], dtype=float)
        self._gains = np.asarray([point.gain_db for point in ordered], dtype=float)

    def gain_at(self, depth_mm: float) -> float:
        """Interpolate gain at a depth, clamping outside the profile range."""
        return float(np.interp(float(depth_mm), self._depths, self._gains))

    def apply(
        self,
        signal: np.ndarray,
        time_axis_us: np.ndarray,
        sound_velocity_mps: float,
    ) -> np.ndarray:
        """Apply depth-dependent linear gain to a copy of the signal."""
        signal_array = np.asarray(signal, dtype=float).reshape(-1)
        time_array = np.asarray(time_axis_us, dtype=float).reshape(-1)
        if signal_array.size != time_array.size:
            raise ValueError("信号和时间轴长度必须一致")
        depths = np.maximum(time_array * float(sound_velocity_mps) / 2000.0, 0.0)
        gains_db = np.interp(depths, self._depths, self._gains)
        gains_linear = np.power(10.0, gains_db / 20.0)
        return signal_array * gains_linear

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": [
                {"depth_mm": point.depth_mm, "gain_db": point.gain_db}
                for point in self.points
            ]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TcgProfile":
        return cls(
            [
                TcgPoint(float(item["depth_mm"]), float(item["gain_db"]))
                for item in data.get("points", [])
            ]
        )
