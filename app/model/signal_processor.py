"""超声信号处理模块，提供频谱分析、滤波和信号平均功能。"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import signal as scipy_signal


class SignalProcessor:
    """
    超声信号处理器。

    提供以下功能：
    1. FFT频谱分析
    2. 数字滤波器（带通、低通、高通）
    3. 信号平均（多次采样平均）
    """

    def __init__(self, sampling_rate_hz: float = 100_000_000.0) -> None:
        """初始化信号处理器。"""
        self.sampling_rate_hz = sampling_rate_hz

    def compute_fft(
        self,
        signal: np.ndarray,
        n_fft: int | None = None,
        window: str = "汉宁窗",
        sample_rate_hz: float | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        计算信号的FFT频谱。

        参数：
        - signal: 输入时域信号
        - n_fft: FFT点数，None表示使用信号长度

        返回：
        - frequencies: 频率数组（Hz）
        - magnitude: 幅值数组（归一化）
        """
        if n_fft is None:
            n_fft = len(signal)
        n_fft = int(n_fft)
        if n_fft < 2:
            raise ValueError("FFT点数必须大于等于2")

        analysis_signal = np.asarray(signal, dtype=float).reshape(-1)
        if analysis_signal.size < n_fft:
            analysis_signal = np.pad(analysis_signal, (0, n_fft - analysis_signal.size))
        else:
            analysis_signal = analysis_signal[:n_fft]

        window_values = self._build_window(window, analysis_signal.size)
        windowed_signal = analysis_signal * window_values

        sample_rate_hz = float(sample_rate_hz or self.sampling_rate_hz)
        if sample_rate_hz <= 0:
            raise ValueError("采样率必须大于0")

        fft_result = np.fft.rfft(windowed_signal, n=n_fft)
        frequencies = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate_hz)
        magnitude = np.abs(fft_result)

        # 归一化幅值
        if magnitude.max() > 0:
            magnitude = magnitude / magnitude.max()

        return frequencies, magnitude
    @staticmethod
    def _build_window(window: str, size: int) -> np.ndarray:
        """将界面窗函数名称转换为 NumPy 窗数组。"""
        normalized = str(window).strip().lower()
        window_map = {
            "矩形窗": np.ones,
            "rectangular": np.ones,
            "boxcar": np.ones,
            "汉宁窗": np.hanning,
            "hann": np.hanning,
            "汉明窗": np.hamming,
            "hamming": np.hamming,
            "布莱克曼窗": np.blackman,
            "blackman": np.blackman,
        }
        factory = window_map.get(normalized)
        if factory is None:
            raise ValueError(f"不支持的窗函数: {window}")
        return factory(size)

    def design_filter(
        self,
        filter_type: str,
        low_freq_hz: float | None = None,
        high_freq_hz: float | None = None,
        order: int = 4,
        sample_rate_hz: float | None = None,
    ) -> np.ndarray:
        """设计 Butterworth SOS 滤波器。"""
        sample_rate_hz = float(sample_rate_hz or self.sampling_rate_hz)
        if sample_rate_hz <= 0:
            raise ValueError("采样率必须大于0")
        if int(order) < 1:
            raise ValueError("滤波器阶数必须大于等于1")

        nyquist = 0.5 * sample_rate_hz
        normalized_type = str(filter_type).strip().lower()
        type_map = {
            "带通": "bandpass",
            "bandpass": "bandpass",
            "低通": "lowpass",
            "lowpass": "lowpass",
            "高通": "highpass",
            "highpass": "highpass",
        }
        btype = type_map.get(normalized_type)
        if btype is None:
            raise ValueError(f"不支持的滤波器类型: {filter_type}")

        if btype in {"bandpass", "bandstop"}:
            if low_freq_hz is None or high_freq_hz is None:
                raise ValueError("带通滤波器必须提供低、高截止频率")
            low = float(low_freq_hz)
            high = float(high_freq_hz)
            if not 0.0 < low < high < nyquist:
                raise ValueError(
                    f"截止频率必须满足 0 < low < high < Nyquist({nyquist:g} Hz)"
                )
            critical = [low, high]
        elif btype == "lowpass":
            if high_freq_hz is None:
                raise ValueError("低通滤波器必须提供高截止频率")
            cutoff = float(high_freq_hz)
            if not 0.0 < cutoff < nyquist:
                raise ValueError(f"截止频率必须满足 0 < cutoff < Nyquist({nyquist:g} Hz)")
            critical = cutoff
        else:
            if low_freq_hz is None:
                raise ValueError("高通滤波器必须提供低截止频率")
            cutoff = float(low_freq_hz)
            if not 0.0 < cutoff < nyquist:
                raise ValueError(f"截止频率必须满足 0 < cutoff < Nyquist({nyquist:g} Hz)")
            critical = cutoff

        return scipy_signal.butter(
            int(order),
            critical,
            btype=btype,
            fs=sample_rate_hz,
            output="sos",
        )

    def design_bandpass_filter(
        self,
        low_freq_hz: float,
        high_freq_hz: float,
        order: int = 4,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """
        设计巴特沃斯带通滤波器。

        参数：
        - low_freq_hz: 低频截止频率（Hz）
        - high_freq_hz: 高频截止频率（Hz）
        - order: 滤波器阶数

        返回：
        - b: 滤波器分子系数
        - a: 滤波器分母系数
        """
        sos = self.design_filter(
            "bandpass",
            low_freq_hz,
            high_freq_hz,
            order=order,
        )
        return sos, None

    def apply_filter(self, signal: np.ndarray, b: np.ndarray, a: np.ndarray | None = None) -> np.ndarray:
        """
        应用数字滤波器。

        参数：
        - signal: 输入信号
        - b: 滤波器分子系数
        - a: 滤波器分母系数（FIR滤波器为[1.0]）

        返回：
        - 滤波后的信号
        """
        signal_array = np.asarray(signal, dtype=float).reshape(-1)
        sos = np.asarray(b)
        if sos.ndim == 2:
            try:
                return scipy_signal.sosfiltfilt(sos, signal_array)
            except ValueError:
                return scipy_signal.sosfilt(sos, signal_array)
        if a is None:
            a = np.array([1.0])
        return scipy_signal.lfilter(np.asarray(b), np.asarray(a), signal_array)

    def compute_signal_average(self, signals: list[np.ndarray], method: str = 'mean') -> np.ndarray:
        """
        计算多信号平均。

        参数：
        - signals: 信号列表
        - method: 平均方法，'mean'或'median'

        返回：
        - 平均后的信号
        """
        if not signals:
            raise ValueError("信号列表不能为空")

        # 确保所有信号长度相同
        signal_lengths = [len(s) for s in signals]
        if len(set(signal_lengths)) > 1:
            raise ValueError("所有信号长度必须相同")

        # 堆叠信号
        stacked_signals = np.vstack(signals)

        if method == 'mean':
            return np.mean(stacked_signals, axis=0)
        elif method == 'median':
            return np.median(stacked_signals, axis=0)
        else:
            raise ValueError(f"不支持的平均方法: {method}")

    def compute_enhanced_envelope(self, signal: np.ndarray, window_size: int = 50) -> np.ndarray:
        """
        计算增强包络线（平滑包络）。

        参数：
        - signal: 输入信号
        - window_size: 平滑窗口大小

        返回：
        - 增强包络信号
        """
        # 取绝对值
        abs_signal = np.abs(signal)

        # 滑动平均平滑
        kernel = np.ones(window_size) / window_size
        envelope = np.convolve(abs_signal, kernel, mode='same')

        return envelope

    def extract_signal_features(self, signal: np.ndarray, time_axis_us: np.ndarray) -> dict[str, Any]:
        """
        提取信号特征。

        参数：
        - signal: 输入信号
        - time_axis_us: 时间轴（微秒）

        返回：
        - 特征字典
        """
        # 计算基本统计特征
        features = {
            'mean': float(np.mean(signal)),
            'std': float(np.std(signal)),
            'max': float(np.max(signal)),
            'min': float(np.min(signal)),
            'peak_to_peak': float(np.max(signal) - np.min(signal)),
            'rms': float(np.sqrt(np.mean(signal**2))),
        }

        # 计算过零率
        zero_crossings = np.where(np.diff(np.sign(signal)))[0]
        features['zero_crossing_rate'] = len(zero_crossings) / len(signal)

        # 计算能量
        features['energy'] = float(np.sum(signal**2))

        # 计算峰值位置
        peak_index = np.argmax(np.abs(signal))
        features['peak_time_us'] = float(time_axis_us[peak_index])
        features['peak_amplitude'] = float(signal[peak_index])

        return features

    def compare_signals(self, signal1: np.ndarray, signal2: np.ndarray,
                        time_axis_us: np.ndarray) -> dict[str, Any]:
        """
        比较两个信号的差异。

        参数：
        - signal1: 第一个信号
        - signal2: 第二个信号
        - time_axis_us: 时间轴（微秒）

        返回：
        - 比较结果字典
        """
        # 确保信号长度相同
        min_len = min(len(signal1), len(signal2))
        s1 = signal1[:min_len]
        s2 = signal2[:min_len]
        time_axis = time_axis_us[:min_len]

        # 计算差异信号
        diff_signal = s2 - s1

        # 计算统计指标
        result = {
            'mean_difference': float(np.mean(diff_signal)),
            'max_difference': float(np.max(np.abs(diff_signal))),
            'rms_difference': float(np.sqrt(np.mean(diff_signal**2))),
            'correlation': float(np.corrcoef(s1, s2)[0, 1]) if len(s1) > 1 else 0.0,
            'difference_signal': diff_signal,
            'time_axis': time_axis,
        }

        # 找到最大差异位置
        max_diff_index = np.argmax(np.abs(diff_signal))
        result['max_diff_time_us'] = float(time_axis[max_diff_index])
        result['max_diff_value'] = float(diff_signal[max_diff_index])

        return result
