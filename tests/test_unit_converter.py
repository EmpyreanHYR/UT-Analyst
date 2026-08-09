"""unit_converter 模块的单元测试。"""

from __future__ import annotations

import math

import pytest

from app.common.unit_converter import (
    depth_mm_to_time_sec,
    depth_mm_to_time_us,
    time_sec_to_depth_mm,
    time_us_to_depth_mm,
)


# ---------------------------------------------------------------------------
# depth_mm_to_time_sec / time_sec_to_depth_mm 互为逆运算
# ---------------------------------------------------------------------------


class TestRoundTripSec:
    """验证 depth ↔ time (秒) 互转的正确性。"""

    @pytest.mark.parametrize(
        "depth_mm, velocity",
        [
            (10.0, 5900.0),
            (50.0, 5900.0),
            (100.0, 6300.0),
            (0.0, 5900.0),
            (1.0, 3000.0),
        ],
    )
    def test_roundtrip_without_delay(self, depth_mm: float, velocity: float) -> None:
        """无零点延迟时，depth → time → depth 应返回原始值。"""
        t = depth_mm_to_time_sec(depth_mm, velocity)
        result = time_sec_to_depth_mm(t, velocity)
        assert result == pytest.approx(depth_mm, abs=1e-6)

    @pytest.mark.parametrize(
        "depth_mm, velocity, delay_us",
        [
            (50.0, 5900.0, 0.5),
            (100.0, 6300.0, 1.2),
            (20.0, 3000.0, 0.0),
        ],
    )
    def test_roundtrip_with_delay(self, depth_mm: float, velocity: float, delay_us: float) -> None:
        """有零点延迟时，depth → time → depth 应返回原始值。"""
        t = depth_mm_to_time_sec(depth_mm, velocity, delay_us)
        result = time_sec_to_depth_mm(t, velocity, delay_us)
        assert result == pytest.approx(depth_mm, abs=1e-6)


# ---------------------------------------------------------------------------
# depth_mm_to_time_us / time_us_to_depth_mm 互为逆运算
# ---------------------------------------------------------------------------


class TestRoundTripUs:
    """验证 depth ↔ time (微秒) 互转的正确性。"""

    def test_roundtrip_us_basic(self) -> None:
        """基本微秒往返测试。"""
        depth = 50.0
        velocity = 5900.0
        t_us = depth_mm_to_time_us(depth, velocity)
        result = time_us_to_depth_mm(t_us, velocity)
        assert result == pytest.approx(depth, abs=1e-4)

    def test_us_is_sec_times_1e6(self) -> None:
        """验证 us 函数是 sec 函数的 1e6 倍。"""
        depth = 75.0
        velocity = 5900.0
        t_sec = depth_mm_to_time_sec(depth, velocity)
        t_us = depth_mm_to_time_us(depth, velocity)
        assert t_us == pytest.approx(t_sec * 1e6, rel=1e-9)


# ---------------------------------------------------------------------------
# 物理正确性
# ---------------------------------------------------------------------------


class TestPhysicsCorrectness:
    """验证换算结果符合物理公式。"""

    def test_known_steel_value(self) -> None:
        """已知钢材 50mm 深度的往返时间 ≈ 16.95 us。"""
        t_us = depth_mm_to_time_us(50.0, 5900.0)
        expected_us = (2.0 * 0.050) / 5900.0 * 1e6
        assert t_us == pytest.approx(expected_us, rel=1e-6)

    def test_zero_depth_returns_delay_only(self) -> None:
        """深度为 0 时，时间应仅等于探头延迟。"""
        delay = 1.5
        t_sec = depth_mm_to_time_sec(0.0, 5900.0, delay)
        assert t_sec == pytest.approx(delay * 1e-6, rel=1e-9)

    def test_zero_depth_result_is_zero_with_no_delay(self) -> None:
        """无延迟、零深度 → 零时间 → 回转深度也为零。"""
        t = depth_mm_to_time_sec(0.0, 5900.0, 0.0)
        assert t == pytest.approx(0.0, abs=1e-12)
        d = time_sec_to_depth_mm(0.0, 5900.0, 0.0)
        assert d == pytest.approx(0.0, abs=1e-9)

    def test_negative_effective_time_clamped_to_zero(self) -> None:
        """当传入时间小于延迟时，深度应为 0（不为负）。"""
        result = time_sec_to_depth_mm(0.1e-6, 5900.0, 1.0)  # delay=1us > 0.1us
        assert result == 0.0


# ---------------------------------------------------------------------------
# 边界 / 安全值
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """验证极端输入不会崩溃。"""

    def test_very_small_velocity(self) -> None:
        """极小声速不应除零。"""
        t = depth_mm_to_time_sec(10.0, 1.0)
        assert math.isfinite(t)
        assert t > 0

    def test_large_depth(self) -> None:
        """大深度值能正常换算。"""
        t = depth_mm_to_time_sec(600.0, 5900.0)
        d = time_sec_to_depth_mm(t, 5900.0)
        assert d == pytest.approx(600.0, abs=1e-3)
