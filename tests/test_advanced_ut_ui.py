"""UI tests for advanced UT controls and scan display."""

from __future__ import annotations

import numpy as np

from app.view.advanced_ut_panel import AdvancedUTPanel
from app.view.scan_panel import ScanPanel


def test_advanced_panel_emits_gate_and_tcg_changes(qapp) -> None:
    panel = AdvancedUTPanel()
    changes: list[dict] = []
    panel.gateChanged.connect(changes.append)
    panel.tcgChanged.connect(changes.append)

    panel.gate_rows["B"].enabled_checkbox.setChecked(True)
    panel.gate_rows["B"].start_spinbox.setValue(40.0)
    panel.tcg_enabled_checkbox.setChecked(True)
    panel.tcg_table.setItem(0, 0, __import__("PyQt5.QtWidgets", fromlist=["QTableWidgetItem"]).QTableWidgetItem("0"))
    panel.tcg_table.setItem(0, 1, __import__("PyQt5.QtWidgets", fromlist=["QTableWidgetItem"]).QTableWidgetItem("6"))
    panel._emit_tcg()

    assert any(item.get("gate_id") == "B" and item.get("enabled") for item in changes)
    assert any(item.get("enabled") is True and item.get("points") for item in changes)


def test_scan_panel_accepts_b_and_c_scan_images(qapp) -> None:
    panel = ScanPanel()
    b_scan = np.arange(20, dtype=np.float32).reshape(4, 5)
    c_scan = np.arange(6, dtype=np.float32).reshape(2, 3)

    panel.update_b_scan(b_scan)
    panel.update_c_scan(c_scan)

    assert panel.b_scan_image.image.shape == b_scan.T.shape
    assert panel.c_scan_image.image.shape == c_scan.shape
