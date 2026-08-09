"""超声检测单位换算工具模块。

集中管理「时间 ↔ 深度」等物理量换算公式，供 Model / Controller / View 统一调用，
消除三层之间的重复实现，保证校准参数变更后换算结果一致。
"""

from __future__ import annotations


def depth_mm_to_time_sec(depth_mm: float, sound_velocity_mps: float, probe_delay_us: float = 0.0) -> float:
    """将深度 (mm) 转换为超声往返传播时间 (s)。

    公式: t = probe_delay + 2 * depth / velocity

    Args:
        depth_mm: 深度，单位 mm。
        sound_velocity_mps: 声速，单位 m/s。
        probe_delay_us: 探头零点延迟，单位 us。

    Returns:
        往返传播时间，单位 s。
    """
    depth_m = depth_mm / 1000.0
    delay_s = probe_delay_us * 1e-6
    return delay_s + (2.0 * depth_m) / max(sound_velocity_mps, 1.0)


def time_sec_to_depth_mm(time_sec: float, sound_velocity_mps: float, probe_delay_us: float = 0.0) -> float:
    """将往返传播时间 (s) 转换为深度 (mm)。

    公式: d = (t - probe_delay) * velocity / 2

    Args:
        time_sec: 往返传播时间，单位 s。
        sound_velocity_mps: 声速，单位 m/s。
        probe_delay_us: 探头零点延迟，单位 us。

    Returns:
        深度，单位 mm。不小于 0。
    """
    delay_s = probe_delay_us * 1e-6
    effective_time = max(time_sec - delay_s, 0.0)
    depth_m = (effective_time * sound_velocity_mps) / 2.0
    return depth_m * 1000.0


def depth_mm_to_time_us(depth_mm: float, sound_velocity_mps: float, probe_delay_us: float = 0.0) -> float:
    """将深度 (mm) 转换为往返传播时间 (us)。"""
    return depth_mm_to_time_sec(depth_mm, sound_velocity_mps, probe_delay_us) * 1e6


def time_us_to_depth_mm(time_us: float, sound_velocity_mps: float, probe_delay_us: float = 0.0) -> float:
    """将往返传播时间 (us) 转换为深度 (mm)。"""
    return time_sec_to_depth_mm(time_us * 1e-6, sound_velocity_mps, probe_delay_us)
