"""Session replay controls."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class ReplayPanel(QWidget):
    """Select a saved session and navigate through stored frames."""

    sessionSelected = pyqtSignal(str)
    refreshRequested = pyqtSignal()
    frameChanged = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame_count = 0
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._advance_frame)

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.session_combo = QComboBox()
        self.session_combo.currentIndexChanged.connect(self._emit_session)
        form.addRow("检测会话:", self.session_combo)
        root.addLayout(form)

        controls = QHBoxLayout()
        self.refresh_button = QPushButton("刷新列表")
        self.refresh_button.clicked.connect(self.refreshRequested.emit)
        controls.addWidget(self.refresh_button)
        root.addLayout(controls)

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.valueChanged.connect(self._emit_frame)
        root.addWidget(self.frame_slider)

        navigation = QHBoxLayout()
        self.previous_button = QPushButton("上一帧")
        self.play_button = QPushButton("播放")
        self.play_button.setCheckable(True)
        self.next_button = QPushButton("下一帧")
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "1x", "2x", "4x"])
        self.speed_combo.setCurrentText("1x")
        self.speed_combo.currentTextChanged.connect(self._update_timer_interval)
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.play_button)
        navigation.addWidget(self.next_button)
        navigation.addWidget(self.speed_combo)
        root.addLayout(navigation)

        self.frame_label = QLabel("0 / 0")
        root.addWidget(self.frame_label)

        self.previous_button.clicked.connect(lambda: self._step_frame(-1))
        self.next_button.clicked.connect(lambda: self._step_frame(1))
        self.play_button.toggled.connect(self._set_playing)
        self._update_timer_interval()

    def set_sessions(self, sessions: list[dict[str, Any]]) -> None:
        current_id = self.session_combo.currentData()
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        for session in sessions:
            label = (
                f"{session.get('workpiece') or '未命名工件'} | "
                f"{session.get('started_at', '')}"
            )
            self.session_combo.addItem(label, session.get("id"))
        if current_id:
            index = self.session_combo.findData(current_id)
            if index >= 0:
                self.session_combo.setCurrentIndex(index)
        self.session_combo.blockSignals(False)
        self._emit_session()

    def set_frame_count(self, frame_count: int) -> None:
        self._frame_count = max(0, int(frame_count))
        maximum = max(0, self._frame_count - 1)
        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, maximum)
        self.frame_slider.setValue(0)
        self.frame_slider.blockSignals(False)
        self._update_frame_label(0)

    def _emit_session(self, _index: int = -1) -> None:
        session_id = self.session_combo.currentData()
        if session_id:
            self.sessionSelected.emit(str(session_id))

    def _emit_frame(self, index: int) -> None:
        self._update_frame_label(index)
        self.frameChanged.emit(int(index))

    def _update_frame_label(self, index: int) -> None:
        displayed = index + 1 if self._frame_count else 0
        self.frame_label.setText(f"{displayed} / {self._frame_count}")

    def _step_frame(self, offset: int) -> None:
        if self._frame_count <= 0:
            return
        self.frame_slider.setValue(
            min(max(self.frame_slider.value() + offset, 0), self._frame_count - 1)
        )

    def _set_playing(self, playing: bool) -> None:
        self.play_button.setText("暂停" if playing else "播放")
        if playing:
            self._play_timer.start()
        else:
            self._play_timer.stop()

    def _advance_frame(self) -> None:
        if self._frame_count <= 0:
            return
        next_index = self.frame_slider.value() + 1
        if next_index >= self._frame_count:
            next_index = 0
        self.frame_slider.setValue(next_index)

    def _update_timer_interval(self, _value: str | None = None) -> None:
        speed_text = self.speed_combo.currentText().rstrip("x")
        speed = float(speed_text or "1")
        self._play_timer.setInterval(max(30, int(500 / speed)))
