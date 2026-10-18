"""B-scan and C-scan image display."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from app.common.plot_style import create_plot_widget


class ScanPanel(QWidget):
    """Tabbed B-scan and C-scan image views."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        self.b_scan_widget = create_plot_widget("B-Scan")
        self.b_scan_widget.setLabel("left", "深度/时间")
        self.b_scan_widget.setLabel("bottom", "扫描位置")
        self.b_scan_image = pg.ImageItem()
        self.b_scan_widget.addItem(self.b_scan_image)

        self.c_scan_widget = create_plot_widget("C-Scan")
        self.c_scan_widget.setLabel("left", "Y (mm)")
        self.c_scan_widget.setLabel("bottom", "X (mm)")
        self.c_scan_image = pg.ImageItem()
        self.c_scan_widget.addItem(self.c_scan_image)

        self.tabs.addTab(self.b_scan_widget, "B-Scan")
        self.tabs.addTab(self.c_scan_widget, "C-Scan")
        layout.addWidget(self.tabs)

    def update_b_scan(self, matrix: np.ndarray) -> None:
        source = np.asarray(matrix, dtype=np.float32)
        image = source.T
        self.b_scan_image.setImage(image, autoLevels=False, levels=(0.0, 1.2))
        self.b_scan_image.setRect(0.0, 0.0, source.shape[0], source.shape[1])

    def update_c_scan(self, matrix: np.ndarray) -> None:
        image = np.asarray(matrix, dtype=np.float32)
        self.c_scan_image.setImage(image, autoLevels=False, levels=(0.0, 1.2))
        self.c_scan_image.setRect(0.0, 0.0, image.shape[1], image.shape[0])
