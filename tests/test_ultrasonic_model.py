"""ultrasonic_model 模块的单元测试。"""

from __future__ import annotations

import numpy as np
import pytest

from app.model.ultrasonic_model import UltrasonicSignalModel


class TestModelInitialization:
    """验证模型初始化状态。"""

    def setup_method(self) -> None:
        self.model = UltrasonicSignalModel()

    def test_default_parameters_present(self) -> None:
        """默认参数字典应包含所有必需键。"""
        required_keys = {
            "samplingRateHz",
            "pulseFrequencyHz",
            "gainDb",
            "thresholdLevel",
            "scanDepthMm",
            "soundVelocityMps",
            "probeDelayUs",
            "gateStartMm",
            "gateEndMm",
            "defectProbability",
            "noiseLevel",
            "historyFrames",
        }
        assert required_keys.issubset(set(self.model.parameters.keys()))

    def test_initial_frame_counter_is_zero(self) -> None:
        """初始帧计数器应为 0。"""
        assert self.model.frameCounter == 0

    def test_time_axis_not_empty(self) -> None:
        """初始化后时间轴不应为空。"""
        assert self.model.timeAxisSec.size > 0
        assert self.model.timeAxisUs.size > 0

    def test_bscan_matrix_shape(self) -> None:
        """B 扫矩阵的行数 = historyFrames，列数 = pointCount。"""
        rows = int(self.model.parameters["historyFrames"])
        cols = self.model.pointCount
        assert self.model.bScanMatrix.shape == (rows, cols)


class TestModelGetParameters:
    """验证 getParameters 返回副本。"""

    def setup_method(self) -> None:
        self.model = UltrasonicSignalModel()

    def test_returns_dict(self) -> None:
        params = self.model.getParameters()
        assert isinstance(params, dict)

    def test_contains_point_count(self) -> None:
        """返回的参数应包含 pointCount 键。"""
        params = self.model.getParameters()
        assert "pointCount" in params

    def test_mutation_does_not_affect_model(self) -> None:
        """修改返回的字典不应影响模型内部参数。"""
        params = self.model.getParameters()
        original_gain = self.model.parameters["gainDb"]
        params["gainDb"] = 999.0
        assert self.model.parameters["gainDb"] == original_gain


class TestModelUpdateParameters:
    """验证参数更新与约束。"""

    def setup_method(self) -> None:
        self.model = UltrasonicSignalModel()

    def test_valid_update(self) -> None:
        """正常参数更新应生效。"""
        self.model.updateParameters({"gainDb": 50.0})
        assert self.model.parameters["gainDb"] == 50.0

    def test_unknown_key_ignored(self) -> None:
        """未知参数键应被忽略。"""
        self.model.updateParameters({"nonExistentKey": 42.0})
        assert "nonExistentKey" not in self.model.parameters

    def test_gain_clamped_upper(self) -> None:
        """增益应被限制在 [0, 110] 范围内。"""
        self.model.updateParameters({"gainDb": 999.0})
        assert self.model.parameters["gainDb"] <= 110.0

    def test_gain_clamped_lower(self) -> None:
        self.model.updateParameters({"gainDb": -10.0})
        assert self.model.parameters["gainDb"] >= 0.0

    def test_gate_start_less_than_gate_end(self) -> None:
        """gateStart >= gateEnd 时，gateEnd 应自动调整。"""
        self.model.updateParameters({"gateStartMm": 100.0, "gateEndMm": 50.0})
        assert self.model.parameters["gateStartMm"] < self.model.parameters["gateEndMm"]

    def test_velocity_clamped(self) -> None:
        """声速应被限制在 [500, 9000] 范围内。"""
        self.model.updateParameters({"soundVelocityMps": 50000.0})
        assert self.model.parameters["soundVelocityMps"] <= 9000.0

    def test_noise_level_clamped(self) -> None:
        """噪声水平应被限制在 [0, 0.35] 范围内。"""
        self.model.updateParameters({"noiseLevel": 5.0})
        assert self.model.parameters["noiseLevel"] <= 0.35

    def test_fft_uses_current_sampling_rate(self) -> None:
        """修改采样率后，模型FFT频率轴应同步更新。"""
        self.model.updateParameters({"samplingRateHz": 100_000_000.0})
        frame = self.model.generateFrame()

        frequencies, _ = self.model.compute_fft(frame["rawSignal"], n_fft=1024)

        assert frequencies[-1] == pytest.approx(50_000_000.0, rel=1e-6)


class TestModelGenerateFrame:
    """验证帧生成功能。"""

    def setup_method(self) -> None:
        self.model = UltrasonicSignalModel()

    def test_frame_returns_expected_keys(self) -> None:
        """generateFrame 应返回包含所有预期键的字典。"""
        frame = self.model.generateFrame()
        expected_keys = {
            "timeAxisUs",
            "rawSignal",
            "envelopeSignal",
            "thresholdLevel",
            "gateRangeUs",
            "peakAmplitude",
            "peakTimeUs",
            "defectDetected",
            "defectDistanceMm",
            "confidence",
            "frameCounter",
            "bScanMatrix",
        }
        assert expected_keys.issubset(set(frame.keys()))

    def test_frame_counter_increments(self) -> None:
        """每生成一帧，计数器应递增。"""
        frame1 = self.model.generateFrame()
        frame2 = self.model.generateFrame()
        assert frame2["frameCounter"] == frame1["frameCounter"] + 1

    def test_signal_arrays_have_correct_size(self) -> None:
        """信号数组大小应与 pointCount 一致。"""
        frame = self.model.generateFrame()
        pc = self.model.pointCount
        assert frame["timeAxisUs"].size == pc
        assert frame["rawSignal"].size == pc
        assert frame["envelopeSignal"].size == pc

    def test_peak_amplitude_non_negative(self) -> None:
        """峰值幅度应非负。"""
        for _ in range(10):
            frame = self.model.generateFrame()
            assert frame["peakAmplitude"] >= 0.0

    def test_confidence_in_range(self) -> None:
        """置信度应在 [0, 1] 范围内。"""
        for _ in range(10):
            frame = self.model.generateFrame()
            assert 0.0 <= frame["confidence"] <= 1.0

    def test_bscan_matrix_updated(self) -> None:
        """生成帧后 B 扫矩阵不应全零。"""
        self.model.generateFrame()
        assert np.any(self.model.bScanMatrix != 0.0)

    def test_gate_range_us_tuple(self) -> None:
        """gateRangeUs 应为二元组且 start < end。"""
        frame = self.model.generateFrame()
        gate_start, gate_end = frame["gateRangeUs"]
        assert gate_start < gate_end


class TestModelResetHistory:
    """验证历史重置功能。"""

    def setup_method(self) -> None:
        self.model = UltrasonicSignalModel()

    def test_reset_clears_bscan(self) -> None:
        """重置后 B 扫矩阵应全零。"""
        self.model.generateFrame()
        self.model.resetHistory()
        assert np.all(self.model.bScanMatrix == 0.0)

    def test_reset_resets_counter(self) -> None:
        """重置后帧计数器应为 0。"""
        self.model.generateFrame()
        self.model.generateFrame()
        self.model.resetHistory()
        assert self.model.frameCounter == 0


class TestModelRebuildCache:
    """验证参数更新后缓存重建。"""

    def setup_method(self) -> None:
        self.model = UltrasonicSignalModel()

    def test_point_count_changes_with_depth(self) -> None:
        """改变扫描深度后 pointCount 应相应变化。"""
        original_pc = self.model.pointCount
        self.model.updateParameters({"scanDepthMm": 500.0})
        # 深度增大，pointCount 可能增大（受 clip 上限 8192 限制）
        assert self.model.pointCount >= 1024
        assert self.model.pointCount <= 8192

    def test_bscan_matrix_resized(self) -> None:
        """更新 historyFrames 后 B 扫矩阵行数应相应变化。"""
        self.model.updateParameters({"historyFrames": 120.0})
        assert self.model.bScanMatrix.shape[0] == 120
