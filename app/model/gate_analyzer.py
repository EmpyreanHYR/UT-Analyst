"""Multi-gate analysis models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class GateConfig:
    """Configuration for one UT gate."""

    gate_id: str
    name: str
    start_mm: float
    width_mm: float
    level: float
    enabled: bool = True
    color: str = "#ff7a7a"

    @property
    def end_mm(self) -> float:
        return self.start_mm + self.width_mm


@dataclass(frozen=True)
class GateResult:
    """Result produced by one gate."""

    gate_id: str
    enabled: bool
    triggered: bool
    peak_amplitude: float
    peak_time_us: float
    start_us: float
    end_us: float


class GateAnalyzer:
    """Evaluate one or more gates over an envelope trace."""

    @staticmethod
    def analyze(
        time_axis_us: np.ndarray,
        envelope: np.ndarray,
        gates: list[GateConfig],
        depth_to_time_us: Callable[[float], float],
    ) -> dict[str, GateResult]:
        time_axis = np.asarray(time_axis_us, dtype=float).reshape(-1)
        amplitude = np.asarray(envelope, dtype=float).reshape(-1)
        if time_axis.size != amplitude.size or time_axis.size == 0:
            raise ValueError("时间轴和包络长度必须一致且非空")

        results: dict[str, GateResult] = {}
        for gate in gates:
            start_us = float(depth_to_time_us(gate.start_mm))
            end_us = float(depth_to_time_us(gate.end_mm))
            start_index = int(np.clip(np.searchsorted(time_axis, start_us, side="left"), 0, time_axis.size - 1))
            end_index = int(np.clip(np.searchsorted(time_axis, end_us, side="right"), start_index + 1, time_axis.size))

            if not gate.enabled or end_index <= start_index:
                results[gate.gate_id] = GateResult(
                    gate_id=gate.gate_id,
                    enabled=gate.enabled,
                    triggered=False,
                    peak_amplitude=0.0,
                    peak_time_us=start_us,
                    start_us=start_us,
                    end_us=end_us,
                )
                continue

            local_index = int(np.argmax(amplitude[start_index:end_index]))
            peak_index = start_index + local_index
            peak_amplitude = float(amplitude[peak_index])
            results[gate.gate_id] = GateResult(
                gate_id=gate.gate_id,
                enabled=gate.enabled,
                triggered=peak_amplitude >= float(gate.level),
                peak_amplitude=peak_amplitude,
                peak_time_us=float(time_axis[peak_index]),
                start_us=start_us,
                end_us=end_us,
            )
        return results
