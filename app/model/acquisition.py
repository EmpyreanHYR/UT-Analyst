"""Hardware-independent acquisition sources and worker loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

import numpy as np
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from app.model.ultrasonic_model import UltrasonicSignalModel


class AcquisitionError(RuntimeError):
    """Raised when an acquisition source cannot continue."""


@dataclass(frozen=True)
class DetectionFrame:
    """One immutable acquisition frame."""

    time_axis_us: np.ndarray
    raw_signal: np.ndarray
    envelope_signal: np.ndarray
    sample_rate_hz: float
    sequence_id: int
    captured_at: str
    source_id: str
    scan_position: tuple[float, float] | None = None
    b_scan_matrix: np.ndarray | None = None

    def to_frame_dict(self) -> dict[str, Any]:
        """Convert to the legacy controller frame dictionary."""
        return {
            "timeAxisUs": self.time_axis_us,
            "rawSignal": self.raw_signal,
            "envelopeSignal": self.envelope_signal,
            "samplingRateHz": self.sample_rate_hz,
            "frameCounter": self.sequence_id,
            "sourceId": self.source_id,
            "capturedAt": self.captured_at,
            "scanPosition": self.scan_position,
            "bScanMatrix": (
                self.b_scan_matrix
                if self.b_scan_matrix is not None
                else np.zeros((1, self.raw_signal.size), dtype=np.float32)
            ),
        }


@dataclass(frozen=True)
class SourceCapabilities:
    """Capabilities exposed by an acquisition source."""

    source_id: str
    channel_count: int
    max_sample_rate_hz: float
    supports_position: bool
    trigger_modes: tuple[str, ...] = ("auto", "gate")


@runtime_checkable
class AcquisitionSource(Protocol):
    """Protocol implemented by simulator, replay, and hardware adapters."""

    @pyqtSlot()
    def start(self) -> None:
        """Start acquisition."""

    @pyqtSlot()
    def stop(self) -> None:
        """Stop acquisition."""

    def read_frame(self, timeout_ms: int) -> DetectionFrame | None:
        """Read one frame or return None when no frame is available."""

    def capabilities(self) -> SourceCapabilities:
        """Return source capabilities."""

    def close(self) -> None:
        """Release source resources."""


class SimulatorSource:
    """Adapt the existing signal model to the acquisition protocol."""

    def __init__(self, model: UltrasonicSignalModel) -> None:
        self.model = model
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def read_frame(self, timeout_ms: int) -> DetectionFrame | None:
        _ = timeout_ms
        if not self._running:
            return None
        frame = self.model.generateFrame()
        return DetectionFrame(
            time_axis_us=np.asarray(frame["timeAxisUs"], dtype=np.float32),
            raw_signal=np.asarray(frame["rawSignal"], dtype=np.float32),
            envelope_signal=np.asarray(frame["envelopeSignal"], dtype=np.float32),
            sample_rate_hz=float(self.model.parameters["samplingRateHz"]),
            sequence_id=int(frame["frameCounter"]),
            captured_at=datetime.now().isoformat(timespec="milliseconds"),
            source_id="simulator",
            b_scan_matrix=np.asarray(frame["bScanMatrix"], dtype=np.float32),
        )

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source_id="simulator",
            channel_count=1,
            max_sample_rate_hz=float(self.model.parameters["samplingRateHz"]),
            supports_position=False,
        )

    def close(self) -> None:
        self.stop()


class ReplaySource:
    """Replay immutable detection frames from memory or persisted storage."""

    def __init__(self, frames: list[DetectionFrame], loop: bool = False) -> None:
        self.frames = list(frames)
        self.loop = bool(loop)
        self._index = 0
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def read_frame(self, timeout_ms: int) -> DetectionFrame | None:
        _ = timeout_ms
        if not self._running or not self.frames:
            return None
        if self._index >= len(self.frames):
            if not self.loop:
                self._running = False
                return None
            self._index = 0
        frame = self.frames[self._index]
        self._index += 1
        return frame

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source_id="replay",
            channel_count=1,
            max_sample_rate_hz=(
                self.frames[0].sample_rate_hz if self.frames else 0.0
            ),
            supports_position=True,
        )

    def close(self) -> None:
        self.stop()
        self._index = 0


class PseudoHardwareSource:
    """Simulator-backed source used to test disconnect and timeout paths."""

    def __init__(
        self,
        model: UltrasonicSignalModel,
        frames_before_disconnect: int | None = None,
    ) -> None:
        self._simulator = SimulatorSource(model)
        self.frames_before_disconnect = frames_before_disconnect
        self._frames_read = 0

    def start(self) -> None:
        self._simulator.start()
        self._frames_read = 0

    def stop(self) -> None:
        self._simulator.stop()

    def read_frame(self, timeout_ms: int) -> DetectionFrame | None:
        if (
            self.frames_before_disconnect is not None
            and self._frames_read >= self.frames_before_disconnect
        ):
            raise AcquisitionError("伪硬件连接中断")
        frame = self._simulator.read_frame(timeout_ms)
        self._frames_read += 1
        return frame

    def capabilities(self) -> SourceCapabilities:
        capabilities = self._simulator.capabilities()
        return SourceCapabilities(
            source_id="pseudo-hardware",
            channel_count=capabilities.channel_count,
            max_sample_rate_hz=capabilities.max_sample_rate_hz,
            supports_position=True,
            trigger_modes=("auto", "gate", "external"),
        )

    def close(self) -> None:
        self._simulator.close()


class HardwareAdapter:
    """Base class for future vendor-specific acquisition adapters."""

    def start(self) -> None:
        raise NotImplementedError("厂商硬件适配器尚未配置")

    def stop(self) -> None:
        raise NotImplementedError("厂商硬件适配器尚未配置")

    def read_frame(self, timeout_ms: int) -> DetectionFrame | None:
        raise NotImplementedError("厂商硬件适配器尚未配置")

    def capabilities(self) -> SourceCapabilities:
        raise NotImplementedError("厂商硬件适配器尚未配置")

    def close(self) -> None:
        self.stop()


class AcquisitionWorker(QObject):
    """Read frames from a source inside a QThread."""

    frameReady = pyqtSignal(object)
    errorRaised = pyqtSignal(str)

    def __init__(
        self,
        source: AcquisitionSource,
        interval_ms: int = 100,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.source = source
        self.interval_ms = max(1, int(interval_ms))
        self._timer: QTimer | None = None

    def start(self) -> None:
        """Create and start the worker timer in the worker thread."""
        self.source.start()
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._read_once)
        self._timer.start(self.interval_ms)

    def stop(self) -> None:
        """Stop the source and worker timer."""
        if self._timer is not None:
            self._timer.stop()
        self.source.stop()

    def _read_once(self) -> None:
        try:
            frame = self.source.read_frame(0)
            if frame is not None:
                self.frameReady.emit(frame)
        except Exception as error:
            self.stop()
            self.errorRaised.emit(str(error))
