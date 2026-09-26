"""超声检测系统的数据模型层（Model）。"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.common.unit_converter import depth_mm_to_time_sec, time_sec_to_depth_mm
from app.model.signal_generator import SignalGenerator
from app.model.signal_processor import SignalProcessor


class UltrasonicSignalModel:
    """
    超声波信号模型。

    主要职责：
    1. 管理检测参数（采样率、频率、增益、检测门等）。
    2. 使用 NumPy 生成仿真的超声回波数据。
    3. 完成检测门内峰值分析并输出缺陷判定结果。
    4. 维护 B 扫历史图像矩阵，供界面实时刷新显示。
    """

    def __init__(self) -> None:
        """初始化模型参数与缓存。"""
        # 随机数发生器：用于模拟工业现场中的噪声与缺陷随机分布。
        self.randomGenerator = np.random.default_rng()
        self.signalGenerator = SignalGenerator(randomGenerator=self.randomGenerator)
        self.signalProcessor = SignalProcessor(sampling_rate_hz=20_000_000.0)

        # 系统默认参数（工程化命名，便于后期接入真实硬件配置）。
        self.parameters: dict[str, float] = {
            "samplingRateHz": 20_000_000.0,  # 采样率，单位 Hz
            "pulseFrequencyHz": 2_500_000.0,  # 激励中心频率，单位 Hz
            "gainDb": 18.0,  # 接收通道增益，单位 dB
            "thresholdLevel": 0.55,  # 缺陷阈值（包络幅值）
            "scanDepthMm": 120.0,  # 扫查深度，单位 mm
            "soundVelocityMps": 5900.0,  # 声速，单位 m/s（如钢材）
            "probeDelayUs": 0.0,  # 零点/楔块延迟，单位 us
            "gateStartMm": 25.0,  # 检测门起点深度，单位 mm
            "gateEndMm": 95.0,  # 检测门终点深度，单位 mm
            "defectProbability": 0.28,  # 模拟缺陷出现概率（0~1）
            "noiseLevel": 0.035,  # 高斯噪声强度
            "historyFrames": 240.0,  # B 扫历史帧数
        }

        # 采样点数由“采样率 + 扫查深度”动态推导，避免参数耦合错误。
        self.pointCount = 2048

        # 时间轴缓存（秒和微秒各一份），避免每帧重复计算。
        self.timeAxisSec = np.zeros(self.pointCount, dtype=np.float32)
        self.timeAxisUs = np.zeros(self.pointCount, dtype=np.float32)

        # B 扫矩阵：每一行是一次 A 扫的包络，滚动形成历史图像。
        self.bScanMatrix = np.zeros((int(self.parameters["historyFrames"]), self.pointCount), dtype=np.float32)

        # 运行帧计数器，可用于界面显示和后续日志追踪。
        self.frameCounter = 0

        # 初始构建时间轴与缓存尺寸。
        self._rebuildTimeAxisAndCache()

    def getParameters(self) -> dict[str, float]:
        """返回当前参数副本，避免外部直接修改内部状态。"""
        parametersCopy = dict(self.parameters)
        parametersCopy["pointCount"] = float(self.pointCount)
        return parametersCopy

    def updateParameters(self, newParameters: dict[str, float]) -> None:
        """
        更新模型参数，并做边界约束。

        参数说明：
        - newParameters: 来自界面层的参数字典。
        """
        for parameterName, parameterValue in newParameters.items():
            if parameterName in self.parameters:
                self.parameters[parameterName] = float(parameterValue)

        # 基础物理和工艺参数约束，避免不合法输入导致算法异常。
        self.parameters["samplingRateHz"] = float(np.clip(self.parameters["samplingRateHz"], 2_000_000.0, 100_000_000.0))
        self.parameters["pulseFrequencyHz"] = float(np.clip(self.parameters["pulseFrequencyHz"], 200_000.0, 20_000_000.0))
        self.parameters["gainDb"] = float(np.clip(self.parameters["gainDb"], 0.0, 110.0))
        self.parameters["thresholdLevel"] = float(np.clip(self.parameters["thresholdLevel"], 0.05, 1.2))
        self.parameters["scanDepthMm"] = float(np.clip(self.parameters["scanDepthMm"], 10.0, 600.0))
        self.parameters["soundVelocityMps"] = float(np.clip(self.parameters["soundVelocityMps"], 500.0, 9000.0))
        self.parameters["probeDelayUs"] = float(np.clip(self.parameters["probeDelayUs"], -200.0, 2000.0))
        self.parameters["defectProbability"] = float(np.clip(self.parameters["defectProbability"], 0.0, 1.0))
        self.parameters["noiseLevel"] = float(np.clip(self.parameters["noiseLevel"], 0.0, 0.35))
        self.parameters["historyFrames"] = float(np.clip(self.parameters["historyFrames"], 60.0, 600.0))

        # 检测门参数约束：必须保证 gateStart < gateEnd 且都在扫描深度内。
        gateStartMm = float(np.clip(self.parameters["gateStartMm"], 0.0, self.parameters["scanDepthMm"]))
        gateEndMm = float(np.clip(self.parameters["gateEndMm"], 0.5, self.parameters["scanDepthMm"]))
        if gateStartMm >= gateEndMm:
            gateEndMm = min(self.parameters["scanDepthMm"], gateStartMm + 1.0)
        self.parameters["gateStartMm"] = gateStartMm
        self.parameters["gateEndMm"] = gateEndMm

        # 参数更新后重建时间轴和缓存。
        self._rebuildTimeAxisAndCache()

    def resetHistory(self) -> None:
        """清空历史数据，重置帧计数。"""
        self.bScanMatrix.fill(0.0)
        self.frameCounter = 0

    def generateFrame(self) -> dict[str, Any]:
        """
        生成一帧检测数据。

        返回字段包含：
        - 时域波形（A 扫）
        - 包络曲线
        - 检测门范围
        - 峰值与缺陷判定
        - B 扫历史矩阵
        """
        rawSignal = self._simulateEchoSignal()
        envelopeSignal = self._buildEnvelope(rawSignal)

        gateStartIndex, gateEndIndex = self._getGateIndexRange()
        gateEnvelope = envelopeSignal[gateStartIndex:gateEndIndex]
        if gateEnvelope.size == 0:
            peakAmplitude = 0.0
            peakIndex = gateStartIndex
        else:
            localPeakIndex = int(np.argmax(gateEnvelope))
            peakAmplitude = float(gateEnvelope[localPeakIndex])
            peakIndex = gateStartIndex + localPeakIndex

        thresholdLevel = self.parameters["thresholdLevel"]
        defectDetected = peakAmplitude >= thresholdLevel

        peakTimeUs = float(self.timeAxisUs[peakIndex]) if peakIndex < self.timeAxisUs.size else 0.0
        defectDistanceMm = self._timeSecToDepthMm(float(self.timeAxisSec[peakIndex])) if defectDetected else None
        confidence = float(np.clip((peakAmplitude - thresholdLevel) / (1.2 - thresholdLevel + 1e-6), 0.0, 1.0))

        # 使用包络更新 B 扫历史：旧帧上移，新帧放在末尾，形成滚动视觉效果。
        normalizedEnvelope = np.clip(envelopeSignal, 0.0, 1.2).astype(np.float32)
        self.bScanMatrix = np.roll(self.bScanMatrix, -1, axis=0)
        self.bScanMatrix[-1, :] = normalizedEnvelope

        self.frameCounter += 1

        gateStartUs = float(self._depthMmToTimeSec(self.parameters["gateStartMm"]) * 1e6)
        gateEndUs = float(self._depthMmToTimeSec(self.parameters["gateEndMm"]) * 1e6)

        return {
            "timeAxisUs": self.timeAxisUs.copy(),
            "rawSignal": rawSignal,
            "envelopeSignal": envelopeSignal,
            "thresholdLevel": thresholdLevel,
            "gateRangeUs": (gateStartUs, gateEndUs),
            "peakAmplitude": peakAmplitude,
            "peakTimeUs": peakTimeUs,
            "defectDetected": defectDetected,
            "defectDistanceMm": defectDistanceMm,
            "confidence": confidence,
            "frameCounter": self.frameCounter,
            "bScanMatrix": self.bScanMatrix.copy(),
        }

    def _rebuildTimeAxisAndCache(self) -> None:
        """
        依据扫描窗口和采样率重建时间轴，并同步历史缓存尺寸。

        该方法保证：
        1. 时间轴与参数一致；
        2. B 扫矩阵列数与采样点数一致；
        3. B 扫矩阵行数与 historyFrames 一致。
        """
        samplingRateHz = self.parameters["samplingRateHz"]
        scanDepthMm = self.parameters["scanDepthMm"]

        # 超声往返传播时间 = 2 * 深度 / 声速。
        scanWindowSec = self._depthMmToTimeSec(scanDepthMm)

        # 根据采样率推导理论采样点数，再做边界控制保证性能稳定。
        derivedPointCount = int(np.ceil(scanWindowSec * samplingRateHz))
        self.pointCount = int(np.clip(derivedPointCount, 1024, 8192))

        # 生成采样时间序列。
        self.timeAxisSec = (np.arange(self.pointCount, dtype=np.float32) / float(samplingRateHz)).astype(np.float32)
        self.timeAxisUs = (self.timeAxisSec * 1e6).astype(np.float32)

        targetRows = int(self.parameters["historyFrames"])
        if self.bScanMatrix.shape != (targetRows, self.pointCount):
            # 参数变更时重建历史缓存，避免维度不匹配。
            self.bScanMatrix = np.zeros((targetRows, self.pointCount), dtype=np.float32)

    def _simulateEchoSignal(self) -> np.ndarray:
        """
        构造一条仿真 A 扫波形。

        实现说明：
        1. 核心波形由 SignalGenerator 统一生成；
        2. Model 层额外负责“缺陷触发概率”与“额外噪声系数”控制；
        3. 最终输出归一化到可视化友好范围。
        """
        # 缺陷触发概率逻辑：触发后由生成器随机产生 1~2 个缺陷波。
        defectTriggered = self.randomGenerator.random() < self.parameters["defectProbability"]
        defectCount = int(self.randomGenerator.integers(1, 3)) if defectTriggered else 0

        generatedTimeSec, generatedSignal = self.signalGenerator.generateSignal(
            samplingRateHz=self.parameters["samplingRateHz"],
            frequencyHz=self.parameters["pulseFrequencyHz"],
            gainDb=self.parameters["gainDb"],
            soundPathMm=self.parameters["scanDepthMm"],
            soundVelocityMps=self.parameters["soundVelocityMps"],
            pointCount=self.pointCount,
            defectCount=defectCount,
        )

        # 同步时间轴，确保后续检测门索引换算与当前信号一致。
        self.timeAxisSec = generatedTimeSec.astype(np.float32)
        self.timeAxisUs = (self.timeAxisSec * 1e6).astype(np.float32)

        # 额外噪声项：用于响应界面参数 noiseLevel（与增益相关噪声叠加）。
        noiseLevel = self.parameters["noiseLevel"]
        if noiseLevel > 0.0:
            extraNoise = self.randomGenerator.normal(0.0, noiseLevel, self.pointCount).astype(np.float32)
            generatedSignal = generatedSignal + extraNoise

        return np.clip(generatedSignal, -1.25, 1.25).astype(np.float32)

    def _buildEnvelope(self, rawSignal: np.ndarray) -> np.ndarray:
        """
        计算包络近似值。

        为保持依赖简单（仅 NumPy），采用“绝对值 + 滑动平均”方式近似包络，
        在在线监测场景中可满足实时告警需求。
        """
        absoluteSignal = np.abs(rawSignal).astype(np.float32)

        # 平滑窗口长度在“噪声抑制”和“响应速度”之间折中取值。
        windowSize = 31
        averageKernel = np.ones(windowSize, dtype=np.float32) / float(windowSize)
        envelopeSignal = np.convolve(absoluteSignal, averageKernel, mode="same").astype(np.float32)
        return envelopeSignal

    def _getGateIndexRange(self) -> tuple[int, int]:
        """将检测门深度转换为采样点索引范围。"""
        gateStartSec = self._depthMmToTimeSec(self.parameters["gateStartMm"])
        gateEndSec = self._depthMmToTimeSec(self.parameters["gateEndMm"])

        gateStartIndex = int(np.clip(np.searchsorted(self.timeAxisSec, gateStartSec), 0, self.pointCount - 1))
        gateEndIndex = int(np.clip(np.searchsorted(self.timeAxisSec, gateEndSec), gateStartIndex + 1, self.pointCount))
        return gateStartIndex, gateEndIndex

    def _depthMmToTimeSec(self, depthMm: float) -> float:
        """深度（mm）转往返传播时间（s）。委托给统一换算模块。"""
        return depth_mm_to_time_sec(
            depthMm,
            self.parameters["soundVelocityMps"],
            self.parameters.get("probeDelayUs", 0.0),
        )

    def _timeSecToDepthMm(self, timeSec: float) -> float:
        """往返传播时间（s）转深度（mm）。委托给统一换算模块。"""
        return time_sec_to_depth_mm(
            timeSec,
            self.parameters["soundVelocityMps"],
            self.parameters.get("probeDelayUs", 0.0),
        )

    def compute_fft(
        self,
        signal: np.ndarray,
        n_fft: int | None = None,
        window: str = "汉宁窗",
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
        return self.signalProcessor.compute_fft(
            signal,
            n_fft=n_fft,
            window=window,
            sample_rate_hz=float(self.parameters["samplingRateHz"]),
        )

    def apply_bandpass_filter(self, signal: np.ndarray, low_freq_hz: float, high_freq_hz: float, order: int = 4) -> np.ndarray:
        """
        应用带通滤波器。

        参数：
        - signal: 输入信号
        - low_freq_hz: 低频截止频率（Hz）
        - high_freq_hz: 高频截止频率（Hz）
        - order: 滤波器阶数

        返回：
        - 滤波后的信号
        """
        b, a = self.signalProcessor.design_bandpass_filter(low_freq_hz, high_freq_hz, order)
        return self.signalProcessor.apply_filter(signal, b, a)

    def apply_filter(
        self,
        signal: np.ndarray,
        filter_type: str,
        low_freq_hz: float | None,
        high_freq_hz: float | None,
        order: int = 4,
    ) -> np.ndarray:
        """使用当前采样率设计并应用数字滤波器。"""
        sos = self.signalProcessor.design_filter(
            filter_type,
            low_freq_hz,
            high_freq_hz,
            order=order,
            sample_rate_hz=float(self.parameters["samplingRateHz"]),
        )
        return self.signalProcessor.apply_filter(signal, sos)

    def compute_signal_average(self, signals: list[np.ndarray], method: str = 'mean') -> np.ndarray:
        """
        计算多信号平均。

        参数：
        - signals: 信号列表
        - method: 平均方法，'mean'或'median'

        返回：
        - 平均后的信号
        """
        return self.signalProcessor.compute_signal_average(signals, method)

    def compute_enhanced_envelope(self, signal: np.ndarray, window_size: int = 50) -> np.ndarray:
        """
        计算增强包络线（平滑包络）。

        参数：
        - signal: 输入信号
        - window_size: 平滑窗口大小

        返回：
        - 增强包络信号
        """
        return self.signalProcessor.compute_enhanced_envelope(signal, window_size)

    def extract_signal_features(self, signal: np.ndarray, time_axis_us: np.ndarray) -> dict[str, Any]:
        """
        提取信号特征。

        参数：
        - signal: 输入信号
        - time_axis_us: 时间轴（微秒）

        返回：
        - 特征字典
        """
        return self.signalProcessor.extract_signal_features(signal, time_axis_us)

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
        return self.signalProcessor.compare_signals(signal1, signal2, time_axis_us)
