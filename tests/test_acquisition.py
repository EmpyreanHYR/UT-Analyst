"""Acquisition source and worker tests."""

from __future__ import annotations

import numpy as np
import pytest
from PyQt5.QtCore import QEventLoop, QThread, QTimer

from app.model.acquisition import (
    AcquisitionError,
    AcquisitionWorker,
    DetectionFrame,
    PseudoHardwareSource,
    ReplaySource,
    SimulatorSource,
)
from app.model.ultrasonic_model import UltrasonicSignalModel


def test_simulator_source_returns_detection_frame() -> None:
    model = UltrasonicSignalModel()
    source = SimulatorSource(model)
    source.start()

    frame = source.read_frame(timeout_ms=0)

    assert isinstance(frame, DetectionFrame)
    assert frame.raw_signal.size == model.pointCount
    assert frame.sample_rate_hz == pytest.approx(model.parameters["samplingRateHz"])
    assert source.capabilities().source_id == "simulator"
    source.close()


def test_replay_source_returns_frames_in_order_and_loops() -> None:
    frames = [
        DetectionFrame(
            time_axis_us=np.array([0.0, 1.0], dtype=np.float32),
            raw_signal=np.array([1.0, 2.0], dtype=np.float32),
            envelope_signal=np.array([1.0, 2.0], dtype=np.float32),
            sample_rate_hz=20_000_000.0,
            sequence_id=index,
            captured_at="",
            source_id="test",
        )
        for index in range(2)
    ]
    source = ReplaySource(frames, loop=True)
    source.start()

    assert source.read_frame(0).sequence_id == 0
    assert source.read_frame(0).sequence_id == 1
    assert source.read_frame(0).sequence_id == 0


def test_pseudo_hardware_disconnect_raises_clear_error() -> None:
    model = UltrasonicSignalModel()
    source = PseudoHardwareSource(model, frames_before_disconnect=1)
    source.start()

    source.read_frame(0)
    with pytest.raises(AcquisitionError, match="连接中断"):
        source.read_frame(0)


def test_worker_emits_frame_on_worker_thread(qapp) -> None:
    source = SimulatorSource(UltrasonicSignalModel())
    thread = QThread()
    worker = AcquisitionWorker(source, interval_ms=20)
    worker.moveToThread(thread)
    received: list[DetectionFrame] = []
    loop = QEventLoop()

    def on_frame(frame: DetectionFrame) -> None:
        received.append(frame)
        loop.quit()

    worker.frameReady.connect(on_frame)
    thread.started.connect(worker.start)
    thread.start()
    QTimer.singleShot(2000, loop.quit)
    loop.exec_()
    worker.stop()
    thread.quit()
    thread.wait(2000)

    assert received
    assert received[0].source_id == "simulator"
