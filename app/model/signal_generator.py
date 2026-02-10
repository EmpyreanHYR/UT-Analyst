"""超声信号仿真引擎。"""

from __future__ import annotations

import numpy as np


class SignalGenerator:
    """
    超声波信号生成器。

    功能说明：
    1. 根据输入参数生成时间轴（time_array）和幅值数组（amplitude_array）。
    2. 波形由始波、底波、缺陷波和噪声组成。
    3. 缺陷波默认随机生成 1~2 个高斯包络正弦脉冲。

    默认参数符合需求：
    - 采样率：100 MHz
    - 频率：2.5 MHz
    """

    def __init__(
        self,
        samplingRateHz: float = 100_000_000.0,
        frequencyHz: float = 2_500_000.0,
        soundVelocityMps: float = 5900.0,
        randomGenerator: np.random.Generator | None = None,
        randomSeed: int | None = None,
    ) -> None:
        """初始化信号生成器。"""
        self.samplingRateHz = samplingRateHz
        self.frequencyHz = frequencyHz
        self.soundVelocityMps = soundVelocityMps
        self.randomGenerator = randomGenerator if randomGenerator is not None else np.random.default_rng(randomSeed)

    def generateSignal(
        self,
        samplingRateHz: float = 100_000_000.0,
        frequencyHz: float = 2_500_000.0,
        gainDb: float = 20.0,
        soundPathMm: float = 120.0,
        *,
        soundVelocityMps: float | None = None,
        pointCount: int | None = None,
        defectCount: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        生成一帧超声信号。

        参数：
        - samplingRateHz: 采样率（Hz）。
        - frequencyHz: 探头频率（Hz）。
        - gainDb: 增益（dB）。
        - soundPathMm: 声程（mm）。
        - soundVelocityMps: 声速（m/s），未传入时使用实例默认值。
        - pointCount: 可选采样点数，传入后优先使用该值。
        - defectCount: 缺陷波数量。None 表示自动随机 1~2 个。

        返回：
        - time_array: 时间轴数组，单位秒（s）。
        - amplitude_array: 幅值数组。
        """
        samplingRateHz = float(np.clip(samplingRateHz, 1_000_000.0, 100_000_000.0))
        frequencyHz = float(np.clip(frequencyHz, 100_000.0, 20_000_000.0))
        gainDb = float(np.clip(gainDb, 0.0, 110.0))
        soundPathMm = float(np.clip(soundPathMm, 1.0, 500.0))

        if soundVelocityMps is None:
            soundVelocityMps = self.soundVelocityMps
        soundVelocityMps = float(np.clip(soundVelocityMps, 500.0, 9000.0))

        # 根据声程计算超声往返传播时间窗口。
        maxTimeSec = (2.0 * (soundPathMm / 1000.0)) / soundVelocityMps

        # 采样点数既可由采样率推导，也可由外部显式指定。
        if pointCount is None:
            pointCount = int(np.ceil(maxTimeSec * samplingRateHz))
            pointCount = int(np.clip(pointCount, 1024, 32768))
        else:
            pointCount = int(np.clip(pointCount, 512, 65536))

        # 构建时间轴，使用 float32 可降低内存与绘图开销。
        timeArray = (np.arange(pointCount, dtype=np.float32) / samplingRateHz).astype(np.float32)
        amplitudeArray = np.zeros(pointCount, dtype=np.float32)

        # 计算统一角频率，减少重复计算。
        angularFrequency = 2.0 * np.pi * frequencyHz

        # ------------------------------------------------------------
        # 1) 始波 Initial Pulse：t=0 附近高幅度衰减正弦波。
        # ------------------------------------------------------------
        initialPulseTau = max(2.4 / frequencyHz, 0.08e-6)
        initialCarrier = np.sin(angularFrequency * timeArray)
        initialEnvelope = np.exp(-timeArray / initialPulseTau)

        # 始波只保留前若干周期，避免在全时域拖尾。
        initialWindowMask = (timeArray <= (6.0 / frequencyHz)).astype(np.float32)
        initialPulse = 1.25 * initialCarrier * initialEnvelope * initialWindowMask
        amplitudeArray += initialPulse.astype(np.float32)

        # ------------------------------------------------------------
        # 2) 底波 Backwall Echo：在时间窗口末端附近叠加反射回波。
        # ------------------------------------------------------------
        backwallTimeSec = float(timeArray[-1])
        backwallSigma = max(2.0 / frequencyHz, 0.10e-6)
        backwallEnvelope = np.exp(-0.5 * ((timeArray - backwallTimeSec) / backwallSigma) ** 2)
        backwallCarrier = np.sin(angularFrequency * (timeArray - backwallTimeSec))
        backwallEcho = 0.72 * backwallEnvelope * backwallCarrier
        amplitudeArray += backwallEcho.astype(np.float32)

        # ------------------------------------------------------------
        # 3) 缺陷波 Defect Echo：中间区域随机生成 1~2 个高斯包络正弦波。
        # ------------------------------------------------------------
        if defectCount is None:
            defectCount = int(self.randomGenerator.integers(1, 3))
        defectCount = int(np.clip(defectCount, 0, 6))

        defectStartSec = maxTimeSec * 0.20
        defectEndSec = maxTimeSec * 0.80

        for _ in range(defectCount):
            defectTimeSec = float(self.randomGenerator.uniform(defectStartSec, defectEndSec))
            defectAmplitude = float(self.randomGenerator.uniform(0.35, 0.95))
            defectSigma = float(self.randomGenerator.uniform(1.2, 2.8) / frequencyHz)
            defectPhase = float(self.randomGenerator.uniform(-np.pi, np.pi))

            defectEnvelope = np.exp(-0.5 * ((timeArray - defectTimeSec) / defectSigma) ** 2)
            defectCarrier = np.sin(angularFrequency * (timeArray - defectTimeSec) + defectPhase)
            defectEcho = defectAmplitude * defectEnvelope * defectCarrier
            amplitudeArray += defectEcho.astype(np.float32)

        # ------------------------------------------------------------
        # 4) 噪声 Noise：叠加高斯白噪声，且噪声幅度随增益变化。
        # ------------------------------------------------------------
        # 增益缩放采用线性映射，避免 dB 指数换算导致仿真信号过饱和。
        gainScale = float(np.clip(1.0 + (gainDb / 55.0), 1.0, 3.2))
        noiseSigma = float(0.010 * gainScale)

        # 回波与噪声都会受增益影响，符合接收链路放大特性。
        amplifiedSignal = amplitudeArray * gainScale
        noiseArray = self.randomGenerator.normal(0.0, noiseSigma, pointCount).astype(np.float32)
        amplitudeArray = amplifiedSignal + noiseArray

        # 为绘图显示做软限幅，防止偶发尖峰影响视觉稳定性。
        amplitudeArray = np.clip(amplitudeArray, -1.5, 1.5).astype(np.float32)

        return timeArray, amplitudeArray
