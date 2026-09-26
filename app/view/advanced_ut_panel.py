"""Controls for multi-gate and TCG configuration."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.model.gate_analyzer import GateConfig


class GateRow(QWidget):
    """Editor for one gate."""

    changed = pyqtSignal(str)

    def __init__(self, gate: GateConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.gate_id = gate.gate_id
        layout = QHBoxLayout(self)
        self.enabled_checkbox = QCheckBox(gate.name)
        self.enabled_checkbox.setChecked(gate.enabled)
        self.start_spinbox = self._depth_spinbox(gate.start_mm)
        self.width_spinbox = self._depth_spinbox(gate.width_mm)
        self.level_spinbox = QDoubleSpinBox()
        self.level_spinbox.setRange(0.0, 1.5)
        self.level_spinbox.setSingleStep(0.05)
        self.level_spinbox.setValue(gate.level)
        self.status_label = QLabel("未触发")

        layout.addWidget(self.enabled_checkbox)
        layout.addWidget(QLabel("起点"))
        layout.addWidget(self.start_spinbox)
        layout.addWidget(QLabel("宽度"))
        layout.addWidget(self.width_spinbox)
        layout.addWidget(QLabel("门限"))
        layout.addWidget(self.level_spinbox)
        layout.addWidget(self.status_label)

        self.enabled_checkbox.toggled.connect(lambda _value: self.changed.emit(self.gate_id))
        self.start_spinbox.valueChanged.connect(lambda _value: self.changed.emit(self.gate_id))
        self.width_spinbox.valueChanged.connect(lambda _value: self.changed.emit(self.gate_id))
        self.level_spinbox.valueChanged.connect(lambda _value: self.changed.emit(self.gate_id))

    @staticmethod
    def _depth_spinbox(value: float) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setRange(0.0, 600.0)
        spinbox.setSuffix(" mm")
        spinbox.setValue(float(value))
        return spinbox

    def to_config(self) -> GateConfig:
        return GateConfig(
            gate_id=self.gate_id,
            name=self.enabled_checkbox.text(),
            start_mm=self.start_spinbox.value(),
            width_mm=self.width_spinbox.value(),
            level=self.level_spinbox.value(),
            enabled=self.enabled_checkbox.isChecked(),
        )

    def set_result(self, triggered: bool, peak_amplitude: float) -> None:
        self.status_label.setText(
            f"触发 {peak_amplitude:.2f}" if triggered else f"未触发 {peak_amplitude:.2f}"
        )


class AdvancedUTPanel(QWidget):
    """Dock panel containing Gate A/B/C and TCG controls."""

    gateChanged = pyqtSignal(dict)
    tcgChanged = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        gate_group = QGroupBox("多闸门")
        gate_layout = QFormLayout(gate_group)
        self.gate_rows: dict[str, GateRow] = {}
        defaults = [
            GateConfig("A", "闸门A", 25.0, 70.0, 0.55),
            GateConfig("B", "闸门B", 40.0, 20.0, 0.60, enabled=False),
            GateConfig("C", "闸门C", 70.0, 20.0, 0.65, enabled=False),
        ]
        for gate in defaults:
            row = GateRow(gate)
            row.changed.connect(self._emit_gate)
            self.gate_rows[gate.gate_id] = row
            gate_layout.addRow(row)
        root.addWidget(gate_group)

        tcg_group = QGroupBox("TCG 时间增益补偿")
        tcg_layout = QVBoxLayout(tcg_group)
        self.tcg_enabled_checkbox = QCheckBox("启用TCG")
        tcg_layout.addWidget(self.tcg_enabled_checkbox)
        self.tcg_table = QTableWidget(3, 2)
        self.tcg_table.setHorizontalHeaderLabels(["深度(mm)", "增益(dB)"])
        defaults_tcg = [(0.0, 0.0), (50.0, 3.0), (100.0, 6.0)]
        for row, (depth, gain) in enumerate(defaults_tcg):
            self.tcg_table.setItem(row, 0, QTableWidgetItem(str(depth)))
            self.tcg_table.setItem(row, 1, QTableWidgetItem(str(gain)))
        tcg_layout.addWidget(self.tcg_table)
        tcg_buttons = QHBoxLayout()
        self.apply_tcg_button = QPushButton("应用TCG")
        self.add_tcg_point_button = QPushButton("添加点")
        tcg_buttons.addWidget(self.apply_tcg_button)
        tcg_buttons.addWidget(self.add_tcg_point_button)
        tcg_layout.addLayout(tcg_buttons)
        root.addWidget(tcg_group)

        self.apply_tcg_button.clicked.connect(self._emit_tcg)
        self.tcg_enabled_checkbox.toggled.connect(lambda _value: self._emit_tcg())
        self.add_tcg_point_button.clicked.connect(self._add_tcg_row)

    def _emit_gate(self, gate_id: str) -> None:
        config = self.gate_rows[gate_id].to_config()
        self.gateChanged.emit(
            {
                "gate_id": config.gate_id,
                "name": config.name,
                "start_mm": config.start_mm,
                "width_mm": config.width_mm,
                "level": config.level,
                "enabled": config.enabled,
            }
        )

    def _emit_tcg(self) -> None:
        points = []
        for row in range(self.tcg_table.rowCount()):
            depth_item = self.tcg_table.item(row, 0)
            gain_item = self.tcg_table.item(row, 1)
            if depth_item is None or gain_item is None:
                continue
            try:
                points.append(
                    {
                        "depth_mm": float(depth_item.text()),
                        "gain_db": float(gain_item.text()),
                    }
                )
            except ValueError:
                continue
        self.tcgChanged.emit(
            {
                "enabled": self.tcg_enabled_checkbox.isChecked(),
                "points": points,
            }
        )

    def _add_tcg_row(self) -> None:
        row = self.tcg_table.rowCount()
        self.tcg_table.insertRow(row)
        self.tcg_table.setItem(row, 0, QTableWidgetItem("0"))
        self.tcg_table.setItem(row, 1, QTableWidgetItem("0"))
