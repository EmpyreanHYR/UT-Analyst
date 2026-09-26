"""缺陷统计分析模块，提供缺陷统计、趋势分析和DAC曲线功能。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger("ut_analyst.defect_analyzer")


@dataclass
class DefectRecord:
    """单条缺陷记录。"""
    uid: int
    depth_mm: float
    amplitude: float
    timestamp: str = ""
    waveform_snapshot: Any = None


@dataclass
class DefectStatistics:
    """缺陷统计结果。"""
    total_count: int = 0
    depth_min_mm: float = 0.0
    depth_max_mm: float = 0.0
    depth_mean_mm: float = 0.0
    depth_std_mm: float = 0.0
    amplitude_min: float = 0.0
    amplitude_max: float = 0.0
    amplitude_mean: float = 0.0
    amplitude_std: float = 0.0
    depth_distribution: dict[str, int] = field(default_factory=dict)
    amplitude_distribution: dict[str, int] = field(default_factory=dict)


class DefectAnalyzer:
    """
    缺陷统计分析器。

    功能：
    1. 缺陷深度分布统计
    2. 缺陷波幅分布统计
    3. 缺陷趋势分析（深度随时间变化）
    4. DAC曲线（距离-波幅校正曲线）模拟
    """

    def __init__(self) -> None:
        """初始化缺陷分析器。"""
        self.defect_records: list[DefectRecord] = []

    def add_record(self, record: DefectRecord) -> None:
        """添加一条缺陷记录。"""
        self.defect_records.append(record)

    def clear_records(self) -> None:
        """清空所有缺陷记录。"""
        self.defect_records.clear()

    def get_statistics(self) -> DefectStatistics:
        """计算缺陷统计信息。"""
        stats = DefectStatistics()

        if not self.defect_records:
            return stats

        depths = np.array([r.depth_mm for r in self.defect_records])
        amplitudes = np.array([r.amplitude for r in self.defect_records])

        stats.total_count = len(self.defect_records)
        stats.depth_min_mm = float(np.min(depths))
        stats.depth_max_mm = float(np.max(depths))
        stats.depth_mean_mm = float(np.mean(depths))
        stats.depth_std_mm = float(np.std(depths))
        stats.amplitude_min = float(np.min(amplitudes))
        stats.amplitude_max = float(np.max(amplitudes))
        stats.amplitude_mean = float(np.mean(amplitudes))
        stats.amplitude_std = float(np.std(amplitudes))

        # 深度分布：按 10mm 区间统计
        bin_edges = np.arange(0, max(stats.depth_max_mm + 10, 100), 10)
        hist, _ = np.histogram(depths, bins=bin_edges)
        for i, count in enumerate(hist):
            label = f"{bin_edges[i]:.0f}-{bin_edges[i+1]:.0f}mm"
            stats.depth_distribution[label] = int(count)

        # 波幅分布：按 10% 区间统计
        amp_bin_edges = np.arange(0, 1.1, 0.1)
        amp_hist, _ = np.histogram(amplitudes, bins=amp_bin_edges)
        for i, count in enumerate(amp_hist):
            label = f"{amp_bin_edges[i]*100:.0f}-{amp_bin_edges[i+1]*100:.0f}%"
            stats.amplitude_distribution[label] = int(count)

        return stats

    def get_depth_trend(self) -> tuple[list[str], list[float]]:
        """
        获取缺陷深度趋势数据。

        返回：
        - timestamps: 时间标签列表
        - depths: 深度值列表
        """
        timestamps = [r.timestamp for r in self.defect_records]
        depths = [r.depth_mm for r in self.defect_records]
        return timestamps, depths

    @staticmethod
    def generate_dac_curve(
        depth_range_mm: tuple[float, float] = (0.0, 200.0),
        reference_depth_mm: float = 50.0,
        reference_amplitude: float = 1.0,
        material_attenuation_db_per_mm: float = 0.02,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        生成模拟DAC曲线（距离-波幅校正曲线）。

        基于超声衰减原理：波幅随距离增大而减小。

        参数：
        - depth_range_mm: 深度范围 (min, max)
        - reference_depth_mm: 参考深度
        - reference_amplitude: 参考深度处的波幅
        - material_attenuation_db_per_mm: 材料衰减系数（dB/mm）

        返回：
        - depths: 深度数组（mm）
        - amplitudes: 对应的波幅阈值数组
        """
        depths = np.linspace(depth_range_mm[0], depth_range_mm[1], 200)

        # DAC曲线公式：A(d) = A_ref * 10^(-alpha * (d - d_ref) / 20)
        # 考虑了扩散和衰减
        amplitudes = reference_amplitude * np.power(
            reference_depth_mm / np.maximum(depths, 1.0),
            1.0  # 扩散因子（简化为线性）
        ) * np.power(
            10.0,
            -material_attenuation_db_per_mm * (depths - reference_depth_mm) / 20.0
        )

        amplitudes = np.clip(amplitudes, 0.0, 1.5)

        return depths, amplitudes

    def check_defect_against_dac(
        self,
        depth_mm: float,
        amplitude: float,
        dac_depths: np.ndarray,
        dac_amplitudes: np.ndarray,
    ) -> dict[str, Any]:
        """
        检查缺陷是否超过DAC曲线。

        参数：
        - depth_mm: 缺陷深度
        - amplitude: 缺陷波幅
        - dac_depths: DAC曲线深度数组
        - dac_amplitudes: DAC曲线波幅数组

        返回：
        - result: 判定结果字典
        """
        # 在DAC曲线上插值获取该深度对应的阈值
        if depth_mm < dac_depths[0] or depth_mm > dac_depths[-1]:
            return {
                "in_range": False,
                "threshold": 0.0,
                "exceeded": False,
                "db_above_dac": 0.0,
            }

        threshold = float(np.interp(depth_mm, dac_depths, dac_amplitudes))
        exceeded = amplitude > threshold

        db_above = 0.0
        if threshold > 1e-9 and amplitude > 1e-9:
            db_above = 20.0 * np.log10(amplitude / threshold)

        return {
            "in_range": True,
            "threshold": threshold,
            "exceeded": exceeded,
            "db_above_dac": float(db_above),
        }
