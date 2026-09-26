"""signal_processor 模块的单元测试。"""

from __future__ import annotations

import numpy as np
import pytest

from app.model.signal_processor import SignalProcessor


class TestSignalProcessorFFT:
    """验证FFT频谱分析功能。"""

    def setup_method(self) -> None:
        """每个测试前创建信号处理器实例。"""
        self.processor = SignalProcessor(sampling_rate_hz=100_000_000.0)

    def test_fft_output_shapes(self) -> None:
        """FFT输出形状应正确。"""
        # 创建一个简单的正弦信号
        t = np.linspace(0, 1e-3, 1000, dtype=np.float32)
        signal = np.sin(2 * np.pi * 1e6 * t).astype(np.float32)

        frequencies, magnitude = self.processor.compute_fft(signal, n_fft=1024)

        assert frequencies.shape == magnitude.shape
        assert len(frequencies) == 513  # 单边频谱，1024/2 + 1

    def test_fft_peak_frequency(self) -> None:
        """FFT应能正确识别峰值频率。"""
        # 创建一个包含1MHz和5MHz成分的信号
        sampling_rate = 100e6
        t = np.arange(0, 1000, dtype=np.float32) / sampling_rate
        signal = (np.sin(2 * np.pi * 1e6 * t) + 0.5 * np.sin(2 * np.pi * 5e6 * t)).astype(np.float32)

        frequencies, magnitude = self.processor.compute_fft(signal, n_fft=1024)

        # 找到峰值频率
        peak_index = np.argmax(magnitude)
        peak_freq = frequencies[peak_index]

        # 峰值应该在1MHz附近（因为1MHz的幅值更大）
        assert abs(peak_freq - 1e6) < 0.5e6  # 允许0.5MHz的误差

    def test_fft_magnitude_normalization(self) -> None:
        """FFT幅值应归一化到[0, 1]范围。"""
        signal = np.random.randn(1000).astype(np.float32)

        _, magnitude = self.processor.compute_fft(signal)

        assert magnitude.max() <= 1.0
        assert magnitude.min() >= 0.0

    def test_fft_uses_supplied_sampling_rate(self) -> None:
        """FFT频率轴应使用本次分析传入的采样率。"""
        signal = np.random.randn(1024).astype(np.float32)

        frequencies, _ = self.processor.compute_fft(
            signal,
            n_fft=1024,
            sample_rate_hz=100_000_000.0,
        )

        assert frequencies[-1] == pytest.approx(50_000_000.0, rel=1e-6)

    def test_fft_supports_documented_window_functions(self) -> None:
        """所有界面提供的窗函数都应被实际应用。"""
        signal = np.sin(np.linspace(0.0, 100.0, 1024)).astype(np.float32)

        _, rectangular = self.processor.compute_fft(signal, window="矩形窗")
        _, blackman = self.processor.compute_fft(signal, window="布莱克曼窗")

        assert not np.allclose(rectangular, blackman)

    def test_fft_rejects_unknown_window(self) -> None:
        """未知窗函数应给出明确错误。"""
        signal = np.ones(256, dtype=np.float32)

        with pytest.raises(ValueError, match="不支持的窗函数"):
            self.processor.compute_fft(signal, window="未知窗")


class TestSignalProcessorFilter:
    """验证数字滤波器功能。"""

    def setup_method(self) -> None:
        """每个测试前创建信号处理器实例。"""
        self.processor = SignalProcessor(sampling_rate_hz=100_000_000.0)

    def test_bandpass_filter_output_length(self) -> None:
        """带通滤波器输出长度应与输入相同。"""
        signal = np.random.randn(1000).astype(np.float32)

        b, a = self.processor.design_bandpass_filter(1e6, 10e6, order=4)
        filtered = self.processor.apply_filter(signal, b, a)

        assert len(filtered) == len(signal)

    def test_lowpass_filter_reduces_high_frequency(self) -> None:
        """低通滤波器应减少高频成分。"""
        # 创建包含高频和低频成分的信号
        t = np.linspace(0, 1e-4, 10_000, dtype=np.float32)
        low_freq = np.sin(2 * np.pi * 1e5 * t)  # 100kHz
        high_freq = 0.5 * np.sin(2 * np.pi * 10e6 * t)  # 10MHz
        signal = (low_freq + high_freq).astype(np.float32)

        # 应用低通滤波器（截止频率1MHz）
        b, a = self.processor.design_bandpass_filter(0.001e6, 1e6, order=4)
        filtered = self.processor.apply_filter(signal, b, a)

        # 滤波后的信号应该更接近低频成分
        # 计算与原始低频成分的相关性
        correlation = np.corrcoef(filtered, low_freq)[0, 1]
        assert correlation > 0.5  # 应该有较高的相关性

    def test_filter_rejects_invalid_cutoff_order(self) -> None:
        """截止频率必须满足 0 < low < high < Nyquist。"""
        with pytest.raises(ValueError, match="截止频率"):
            self.processor.design_bandpass_filter(5e6, 1e6, order=4)

        with pytest.raises(ValueError, match="截止频率"):
            self.processor.design_bandpass_filter(1e6, 60e6, order=4)

    def test_filter_returns_sos_coefficients(self) -> None:
        """SciPy SOS设计应返回二维系数矩阵，而不是手写FIR系数。"""
        sos = self.processor.design_filter(
            "bandpass",
            1e6,
            10e6,
            order=4,
            sample_rate_hz=100_000_000.0,
        )

        assert sos.ndim == 2
        assert sos.shape[1] == 6


class TestSignalProcessorAverage:
    """验证信号平均功能。"""

    def setup_method(self) -> None:
        """每个测试前创建信号处理器实例。"""
        self.processor = SignalProcessor()

    def test_mean_average(self) -> None:
        """均值平均应正确计算。"""
        signals = [
            np.array([1.0, 2.0, 3.0], dtype=np.float32),
            np.array([4.0, 5.0, 6.0], dtype=np.float32),
            np.array([7.0, 8.0, 9.0], dtype=np.float32),
        ]

        result = self.processor.compute_signal_average(signals, method='mean')

        expected = np.array([4.0, 5.0, 6.0], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_median_average(self) -> None:
        """中位数平均应正确计算。"""
        signals = [
            np.array([1.0, 2.0, 3.0], dtype=np.float32),
            np.array([4.0, 5.0, 6.0], dtype=np.float32),
            np.array([7.0, 8.0, 9.0], dtype=np.float32),
        ]

        result = self.processor.compute_signal_average(signals, method='median')

        expected = np.array([4.0, 5.0, 6.0], dtype=np.float32)
        np.testing.assert_array_almost_equal(result, expected)

    def test_average_with_different_lengths_raises_error(self) -> None:
        """不同长度的信号平均应抛出错误。"""
        signals = [
            np.array([1.0, 2.0], dtype=np.float32),
            np.array([4.0, 5.0, 6.0], dtype=np.float32),
        ]

        with pytest.raises(ValueError, match="所有信号长度必须相同"):
            self.processor.compute_signal_average(signals)


class TestSignalProcessorFeatures:
    """验证信号特征提取功能。"""

    def setup_method(self) -> None:
        """每个测试前创建信号处理器实例。"""
        self.processor = SignalProcessor()

    def test_extract_features_returns_all_keys(self) -> None:
        """特征提取应返回所有必需的键。"""
        signal = np.random.randn(1000).astype(np.float32)
        time_axis = np.linspace(0, 1e-3, 1000, dtype=np.float32)

        features = self.processor.extract_signal_features(signal, time_axis)

        required_keys = ['mean', 'std', 'max', 'min', 'peak_to_peak', 'rms',
                        'zero_crossing_rate', 'energy', 'peak_time_us', 'peak_amplitude']
        for key in required_keys:
            assert key in features

    def test_extract_features_values_are_floats(self) -> None:
        """特征值应为浮点数。"""
        signal = np.random.randn(1000).astype(np.float32)
        time_axis = np.linspace(0, 1e-3, 1000, dtype=np.float32)

        features = self.processor.extract_signal_features(signal, time_axis)

        for key, value in features.items():
            assert isinstance(value, float), f"Feature '{key}' should be float, got {type(value)}"


class TestSignalProcessorCompare:
    """验证信号对比功能。"""

    def setup_method(self) -> None:
        """每个测试前创建信号处理器实例。"""
        self.processor = SignalProcessor()

    def test_compare_identical_signals(self) -> None:
        """相同信号的对比应返回零差异。"""
        signal = np.random.randn(1000).astype(np.float32)
        time_axis = np.linspace(0, 1e-3, 1000, dtype=np.float32)

        result = self.processor.compare_signals(signal, signal, time_axis)

        assert result['mean_difference'] == pytest.approx(0.0, abs=1e-6)
        assert result['max_difference'] == pytest.approx(0.0, abs=1e-6)
        assert result['rms_difference'] == pytest.approx(0.0, abs=1e-6)
        assert result['correlation'] == pytest.approx(1.0, abs=1e-6)

    def test_compare_different_signals(self) -> None:
        """不同信号的对比应返回非零差异。"""
        signal1 = np.random.randn(1000).astype(np.float32)
        signal2 = signal1 + 0.1  # 添加偏移
        time_axis = np.linspace(0, 1e-3, 1000, dtype=np.float32)

        result = self.processor.compare_signals(signal1, signal2, time_axis)

        assert abs(result['mean_difference']) > 0.0
        assert result['correlation'] > 0.9  # 应该高度相关

    def test_compare_signals_returns_required_keys(self) -> None:
        """信号对比应返回所有必需的键。"""
        signal1 = np.random.randn(1000).astype(np.float32)
        signal2 = np.random.randn(1000).astype(np.float32)
        time_axis = np.linspace(0, 1e-3, 1000, dtype=np.float32)

        result = self.processor.compare_signals(signal1, signal2, time_axis)

        required_keys = ['mean_difference', 'max_difference', 'rms_difference',
                        'correlation', 'difference_signal', 'time_axis',
                        'max_diff_time_us', 'max_diff_value']
        for key in required_keys:
            assert key in result
