"""耦合与探头健康监测。

在实时检测过程中，底波（工件底面回波）幅值对耦合状态非常敏感：耦合不良时
底波会明显下降，探头未贴实或扫查速度过快时底波会剧烈波动。因此本模块对底波
幅值做滑动窗口统计，输出耦合状态与处置建议。

需要说明的边界：

- 监测只给出提示，不参与合格 / 不合格判定，也不会自动停止采集；
- 阈值是经验值，可随时调整；
- 底波幅值本身受材料衰减、曲面、扫查深度影响，首次使用应先空扫一段时间
  建立正常基准。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

STATE_NORMAL = "正常"
STATE_POOR_COUPLING = "耦合不良"
STATE_FLUCTUATION = "波动异常"
STATE_INSUFFICIENT = "数据不足"


@dataclass
class CouplingStatus:
    """一次耦合监测的结果。"""

    state: str
    message: str
    backwall_mean: float = 0.0
    backwall_ratio: float = 0.0
    snr_db: float = 0.0
    sample_count: int = 0
    advice: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "message": self.message,
            "backwall_mean": self.backwall_mean,
            "backwall_ratio": self.backwall_ratio,
            "snr_db": self.snr_db,
            "sample_count": self.sample_count,
            "advice": self.advice,
        }


def extract_backwall_metrics(
    envelope: np.ndarray,
    tail_ratio: float = 0.15,
    noise_ratio: float = 0.10,
) -> tuple[float, float]:
    """从包络信号中取末段底波幅值与前段噪声水平。

    参数：
    - envelope: 一帧包络信号；
    - tail_ratio: 末段占整帧的比例，用于搜索底波峰值；
    - noise_ratio: 前段占整帧的比例，用于估计噪声本底。

    返回：
    - (backwall_amplitude, noise_amplitude)
    """
    signal = np.asarray(envelope, dtype=float).ravel()
    if signal.size == 0:
        return 0.0, 0.0
    tail_count = max(1, int(signal.size * tail_ratio))
    noise_count = max(1, int(signal.size * noise_ratio))
    backwall = float(np.max(signal[-tail_count:]))
    noise = float(np.median(signal[:noise_count]))
    return backwall, noise


class CouplingMonitor:
    """底波幅值滑动窗口统计。

    参数：
    - window_size: 滑动窗口长度（帧数）；
    - min_samples: 判定所需的最少样本数；
    - low_ratio: 底波均值低于参考值的该比例时判为耦合不良；
    - fluctuation_ratio: 底波相对标准差超过该比例时判为波动异常。
    """

    def __init__(
        self,
        window_size: int = 20,
        min_samples: int = 5,
        low_ratio: float = 0.6,
        fluctuation_ratio: float = 0.35,
    ) -> None:
        self.window_size = max(2, int(window_size))
        self.min_samples = max(2, int(min_samples))
        self.low_ratio = float(low_ratio)
        self.fluctuation_ratio = float(fluctuation_ratio)
        self._backwall: deque[float] = deque(maxlen=self.window_size)
        self._noise: deque[float] = deque(maxlen=self.window_size)
        self._reference: float | None = None

    @property
    def sample_count(self) -> int:
        return len(self._backwall)

    @property
    def reference_amplitude(self) -> float | None:
        """当前使用的底波参考幅值。"""
        return self._reference

    def reset(self) -> None:
        """清空窗口与基准，用于重新建立耦合基准。"""
        self._backwall.clear()
        self._noise.clear()
        self._reference = None

    def update(
        self,
        backwall_amplitude: float,
        noise_amplitude: float = 0.0,
    ) -> CouplingStatus:
        """追加一帧底波幅值并返回当前耦合状态。"""
        amplitude = max(float(backwall_amplitude), 0.0)
        noise = max(float(noise_amplitude), 0.0)
        self._backwall.append(amplitude)
        self._noise.append(noise)

        # 以窗口早期的较大值作为参考，避免一开始就锁定在低耦合状态。
        if self._reference is None or amplitude > self._reference:
            self._reference = amplitude if self._reference is None else max(self._reference, amplitude)

        if self.sample_count < self.min_samples:
            return CouplingStatus(
                state=STATE_INSUFFICIENT,
                message=f"正在建立耦合基准（{self.sample_count}/{self.min_samples}）。",
                backwall_mean=float(np.mean(self._backwall)),
                sample_count=self.sample_count,
            )

        values = np.asarray(self._backwall, dtype=float)
        mean = float(np.mean(values))
        std = float(np.std(values))
        noise_mean = float(np.mean(self._noise)) if self._noise else 0.0
        snr_db = 20.0 * np.log10((mean + 1e-9) / (noise_mean + 1e-9))
        reference = self._reference or mean
        ratio = mean / reference if reference > 1e-9 else 0.0
        fluctuation = std / mean if mean > 1e-9 else 0.0

        if ratio < self.low_ratio:
            return CouplingStatus(
                state=STATE_POOR_COUPLING,
                message=f"底波幅值偏低（约为基准的 {ratio * 100:.0f}%）。",
                backwall_mean=mean,
                backwall_ratio=ratio,
                snr_db=snr_db,
                sample_count=self.sample_count,
                advice="请重新耦合或补充耦合剂，并确认探头与工件贴合良好。",
            )
        if fluctuation > self.fluctuation_ratio:
            return CouplingStatus(
                state=STATE_FLUCTUATION,
                message=f"底波幅值波动偏大（相对标准差 {fluctuation * 100:.0f}%）。",
                backwall_mean=mean,
                backwall_ratio=ratio,
                snr_db=snr_db,
                sample_count=self.sample_count,
                advice="请降低扫查速度、保持探头压力稳定，必要时复查校准。",
            )

        return CouplingStatus(
            state=STATE_NORMAL,
            message="耦合状态正常。",
            backwall_mean=mean,
            backwall_ratio=ratio,
            snr_db=snr_db,
            sample_count=self.sample_count,
        )
