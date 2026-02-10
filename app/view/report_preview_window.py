"""检测报告预览窗口（View）。"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class ReportPreviewWindow(QDialog):
    """
    报告预览窗口。

    设计原则：
    - 该类仅负责界面展示与交互信号发出；
    - 具体文件保存逻辑由 Controller 处理，保持 MVC 解耦。
    """

    saveRequested = pyqtSignal()

    def __init__(self, waveformPixmap: QPixmap, reportHtml: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("检测报告预览")
        self.resize(980, 760)

        # 保留原始截图，用于窗口大小变化时重新缩放显示。
        self.originalWaveformPixmap = waveformPixmap

        self._buildUi(reportHtml)
        self._updatePreviewPixmap()

    def _buildUi(self, reportHtml: str) -> None:
        """构建预览窗口布局。"""
        rootLayout = QVBoxLayout(self)
        rootLayout.setContentsMargins(12, 12, 12, 12)
        rootLayout.setSpacing(10)

        screenshotTitleLabel = QLabel("波形截图预览")
        screenshotTitleLabel.setStyleSheet("font-size: 14px; font-weight: 600;")
        rootLayout.addWidget(screenshotTitleLabel)

        self.screenshotLabel = QLabel(self)
        self.screenshotLabel.setAlignment(Qt.AlignCenter)
        self.screenshotLabel.setMinimumHeight(260)
        self.screenshotLabel.setStyleSheet(
            "border: 1px solid #3a4a5c; background-color: #0f141a; border-radius: 6px;"
        )
        rootLayout.addWidget(self.screenshotLabel)

        reportTitleLabel = QLabel("报告内容预览")
        reportTitleLabel.setStyleSheet("font-size: 14px; font-weight: 600;")
        rootLayout.addWidget(reportTitleLabel)

        self.reportBrowser = QTextBrowser(self)
        self.reportBrowser.setHtml(reportHtml)
        rootLayout.addWidget(self.reportBrowser, stretch=1)

        buttonLayout = QHBoxLayout()
        buttonLayout.addStretch(1)
        self.saveButton = QPushButton("保存报告", self)
        self.closeButton = QPushButton("关闭", self)
        buttonLayout.addWidget(self.saveButton)
        buttonLayout.addWidget(self.closeButton)
        rootLayout.addLayout(buttonLayout)

        self.saveButton.clicked.connect(self.saveRequested.emit)
        self.closeButton.clicked.connect(self.close)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """窗口尺寸变化时同步更新截图缩放显示。"""
        super().resizeEvent(event)
        self._updatePreviewPixmap()

    def _updatePreviewPixmap(self) -> None:
        """按当前控件尺寸缩放截图，保持比例且不失真。"""
        if self.originalWaveformPixmap.isNull():
            self.screenshotLabel.setText("暂无截图")
            return

        availableWidth = max(self.screenshotLabel.width() - 20, 80)
        availableHeight = max(self.screenshotLabel.height() - 20, 80)
        scaledPixmap = self.originalWaveformPixmap.scaled(
            availableWidth,
            availableHeight,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.screenshotLabel.setPixmap(scaledPixmap)

