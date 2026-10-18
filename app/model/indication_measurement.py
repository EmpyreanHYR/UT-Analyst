"""缺陷指示长度与指示高度自动测量。

在 B-Scan 帧序列（扫查位置 × 深度采样）上，采用相对落差法（默认 6 dB）自动
定位指示的起止位置，得到指示长度；再在峰值所在位置沿深度方向做同样的落差
测量，得到指示高度（深度方向）。

需要注意的边界：

- 位置轴由"扫查步距 × 帧序号"得到，因此测量精度直接取决于步距设置；
- 落差法测得的是相对值，仍须结合探头参数、曲面耦合与人工判读；
- 当指示触达扫查范围边界时，测量结果偏小，方法会在 `notes` 中给出提示。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class IndicationMeasurement:
    """一次指示测量的结果。"""

    length_mm: float | None = None
    height_mm: float | None = None
    peak_amplitude: float = 0.0
    peak_position_mm: float | None = None
    start_position_mm: float | None = None
    end_position_mm: float | None = None
    peak_depth_mm: float | None = None
    drop_db: float = 6.0
    method: str = "相对落差法"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "length_mm": self.length_mm,
            "height_mm": self.height_mm,
            "peak_amplitude": self.peak_amplitude,
            "peak_position_mm": self.peak_position_mm,
            "start_position_mm": self.start_position_mm,
            "end_position_mm": self.end_position_mm,
            "peak_depth_mm": self.peak_depth_mm,
            "drop_db": self.drop_db,
            "method": self.method,
            "notes": list(self.notes),
        }


def _empty_measurement(drop_db: float, note: str) -> IndicationMeasurement:
    """构造一条无有效结果的测量记录。"""
    return IndicationMeasurement(
        drop_db=drop_db,
        method=f"相对落差法（{drop_db:.0f} dB）",
        notes=[note],
    )


def measure_indication(
    bscan: np.ndarray,
    positions_mm: np.ndarray,
    depths_mm: np.ndarray,
    depth_window_mm: tuple[float, float] | None = None,
    drop_db: float = 6.0,
) -> IndicationMeasurement:
    """在 B-Scan 矩阵上测量指示长度与指示高度。

    参数：
    - bscan: 形状为 (扫查位置数, 深度采样数) 的幅值矩阵；
    - positions_mm: 每个扫查位置对应的位置坐标（mm），单调递增；
    - depths_mm: 每个深度采样对应的深度（mm），单调递增；
    - depth_window_mm: 只在 (min, max) 深度窗内测量，None 表示全深度；
    - drop_db: 相对峰值下降多少分贝作为指示边界，默认 6 dB。

    返回：
    - IndicationMeasurement 测量结果。
    """
    matrix = np.asarray(bscan, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("B-Scan 矩阵必须是二维数组")
    positions = np.asarray(positions_mm, dtype=float).ravel()
    depths = np.asarray(depths_mm, dtype=float).ravel()

    matrix_rows, matrix_cols = matrix.shape
    if positions.size != matrix_rows or depths.size != matrix_cols:
        raise ValueError("位置轴 / 深度轴长度与 B-Scan 矩阵不一致")

    method = f"相对落差法（{drop_db:.0f} dB）"
    if matrix_rows < 2 or matrix_cols < 2:
        return _empty_measurement(drop_db, "扫查位置或深度采样不足，无法测量。")

    depth_mask = np.ones(matrix_cols, dtype=bool)
    if depth_window_mm is not None:
        low, high = sorted(depth_window_mm)
        depth_mask = (depths >= low) & (depths <= high)
    if not np.any(depth_mask):
        return _empty_measurement(drop_db, "深度窗口内没有有效采样点。")

    work = np.where(depth_mask[None, :], matrix, 0.0)
    peak_flat = int(np.argmax(work))
    peak_pos_index, peak_sample_index = np.unravel_index(peak_flat, work.shape)
    peak_amplitude = float(work[peak_pos_index, peak_sample_index])
    if peak_amplitude <= 0.0:
        return _empty_measurement(drop_db, "深度窗口内没有可用的回波幅值。")

    threshold = peak_amplitude * (10.0 ** (-drop_db / 20.0))
    notes: list[str] = []

    # 位置方向：每个位置在深度窗内的最大幅值构成剖面。
    position_profile = work.max(axis=1)
    left_index = int(peak_pos_index)
    while left_index - 1 >= 0 and position_profile[left_index - 1] >= threshold:
        left_index -= 1
    right_index = int(peak_pos_index)
    while right_index + 1 < matrix_rows and position_profile[right_index + 1] >= threshold:
        right_index += 1

    start_position = float(positions[left_index])
    end_position = float(positions[right_index])
    length_mm = max(end_position - start_position, 0.0)
    if left_index == 0 or right_index == matrix_rows - 1:
        notes.append("指示触及扫查范围边界，指示长度可能偏小，建议扩大扫查范围后复测。")
    if right_index - left_index <= 1:
        notes.append("指示仅覆盖 1~2 个扫查位置，长度测量分辨率有限。")

    # 深度方向：峰值位置处沿深度采样构成剖面。
    depth_profile = work[peak_pos_index, :]
    top_index = int(peak_sample_index)
    while (
        top_index - 1 >= 0
        and depth_mask[top_index - 1]
        and depth_profile[top_index - 1] >= threshold
    ):
        top_index -= 1
    bottom_index = int(peak_sample_index)
    while (
        bottom_index + 1 < matrix_cols
        and depth_mask[bottom_index + 1]
        and depth_profile[bottom_index + 1] >= threshold
    ):
        bottom_index += 1
    height_mm = max(float(depths[bottom_index] - depths[top_index]), 0.0)

    return IndicationMeasurement(
        length_mm=length_mm,
        height_mm=height_mm,
        peak_amplitude=peak_amplitude,
        peak_position_mm=float(positions[peak_pos_index]),
        start_position_mm=start_position,
        end_position_mm=end_position,
        peak_depth_mm=float(depths[peak_sample_index]),
        drop_db=float(drop_db),
        method=method,
        notes=notes,
    )


def measure_from_history(
    history: np.ndarray,
    scan_step_mm: float,
    depths_mm: np.ndarray,
    depth_window_mm: tuple[float, float] | None = None,
    drop_db: float = 6.0,
) -> IndicationMeasurement:
    """按固定扫查步距把帧历史折算成位置轴后测量。

    参数：
    - history: 形状为 (帧数, 深度采样数) 的 B-Scan 历史矩阵；
    - scan_step_mm: 相邻帧之间的扫查步距（mm）；
    - depths_mm: 每个深度采样对应的深度（mm）；
    - depth_window_mm: 只在 (min, max) 深度窗内测量；
    - drop_db: 落差分贝，默认 6 dB。
    """
    matrix = np.asarray(history, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("B-Scan 历史矩阵必须是二维数组")
    positions = np.arange(matrix.shape[0], dtype=float) * float(scan_step_mm)
    return measure_indication(
        matrix,
        positions,
        depths_mm,
        depth_window_mm=depth_window_mm,
        drop_db=drop_db,
    )
