"""signal_generator 模块的单元测试。"""

from __future__ import annotations

import numpy as np
import pytest

from app.model.signal_generator import SignalGenerator


class TestSignalGeneratorBasic:
    """验证信号生成器的基本输出属性。"""

    def setup_method(self) -> None:
        """每个测试前创建带固定种子的生成器，确保可重复性。"""
        self.generator = SignalGenerator(randomSeed=42)

    def test_output_shapes_match(self) -> None:
        """时间轴和幅值数组长度一致。"""
        time_arr, amp_arr = self.generator.generateSignal(pointCount=2048)
        assert time_arr.shape == amp_arr.shape
        assert time_arr.size == 2048

    def test_output_dtype_float32(self) -> None:
        """输出应为 float32 以优化内存和绘图性能。"""
        time_arr, amp_arr = self.generator.generateSignal(pointCount=1024)
        assert time_arr.dtype == np.float32
        assert amp_arr.dtype == np.float32

    def test_time_axis_starts_at_zero(self) -> None:
        """时间轴应从 0 开始。"""
        time_arr, _ = self.generator.generateSignal(pointCount=1024)
        assert time_arr[0] == pytest.approx(0.0, abs=1e-9)

    def test_time_axis_is_monotonic(self) -> None:
        """时间轴应单调递增。"""
        time_arr, _ = self.generator.generateSignal(pointCount=2048)
        diffs = np.diff(time_arr)
        assert np.all(diffs >= 0)

    def test_amplitude_within_clip_range(self) -> None:
        """幅值应在软限幅范围内 [-1.5, 1.5]。"""
        _, amp_arr = self.generator.generateSignal(pointCount=4096)
        assert float(amp_arr.min()) >= -1.5
        assert float(amp_arr.max()) <= 1.5


class TestSignalGeneratorDefectCount:
    """验证缺陷数量控制。"""

    def setup_method(self) -> None:
        self.generator = SignalGenerator(randomSeed=123)

    def test_zero_defects_no_random_defects(self) -> None:
        """defectCount=0 时不应注入缺陷波（但始波和底波仍存在）。"""
        _, amp_arr = self.generator.generateSignal(pointCount=2048, defectCount=0)
        # 信号仍然非零（始波 + 底波 + 噪声）
        assert np.any(amp_arr != 0)

    def test_defect_count_clamped(self) -> None:
        """defectCount 超过上限时应被截断为 6。"""
        # 不应抛出异常
        _, amp_arr = self.generator.generateSignal(pointCount=2048, defectCount=100)
        assert amp_arr.size == 2048

    def test_multiple_frames_differ(self) -> None:
        """不同帧（含随机缺陷）的波形应不完全相同。"""
        _, amp1 = self.generator.generateSignal(pointCount=2048)
        _, amp2 = self.generator.generateSignal(pointCount=2048)
        assert not np.array_equal(amp1, amp2)


class TestSignalGeneratorGainEffect:
    """验证增益参数对信号的影响。"""

    def setup_method(self) -> None:
        self.generator = SignalGenerator(randomSeed=99)

    def test_higher_gain_increases_amplitude(self) -> None:
        """更高增益应产生更大振幅。"""
        _, amp_low = self.generator.generateSignal(gainDb=10.0, pointCount=2048)
        _, amp_high = self.generator.generateSignal(gainDb=80.0, pointCount=2048)
        # 使用最大绝对值比较
        assert float(np.max(np.abs(amp_high))) > float(np.max(np.abs(amp_low)))


class TestSignalGeneratorPointCount:
    """验证 pointCount 参数控制。"""

    def setup_method(self) -> None:
        self.generator = SignalGenerator(randomSeed=7)

    @pytest.mark.parametrize("count", [512, 1024, 2048, 4096])
    def test_custom_point_count(self, count: int) -> None:
        """自定义 pointCount 应精确匹配输出大小。"""
        time_arr, amp_arr = self.generator.generateSignal(pointCount=count)
        assert time_arr.size == count
        assert amp_arr.size == count

    def test_auto_point_count_within_bounds(self) -> None:
        """未指定 pointCount 时，自动推导的点数应在 [1024, 32768] 范围内。"""
        time_arr, _ = self.generator.generateSignal()
        assert 1024 <= time_arr.size <= 32768
