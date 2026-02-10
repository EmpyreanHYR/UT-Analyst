"""超声检测系统主界面（View）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """
    主窗口视图类。

    设计目标：
    1. 严格负责界面组织和显示；
    2. 通过信号把交互请求发送给控制器；
    3. 不在此类中编写业务判定逻辑，保持 MVC 分层清晰。
    """

    # 采集流程相关信号（供 Controller 订阅）。
    startRequested = pyqtSignal()
    stopRequested = pyqtSignal()
    singleShotRequested = pyqtSignal()
    resetRequested = pyqtSignal()
    parametersApplied = pyqtSignal(dict)

    # 文件与报告相关信号（后续可扩展文件读写、报表导出）。
    openRequested = pyqtSignal()
    saveRequested = pyqtSignal()
    reportRequested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("超声波智能辅助检测系统 V1.0")
        self.setMinimumSize(1360, 860)

        # 配置绘图全局抗锯齿，使高刷新曲线边缘更平滑。
        pg.setConfigOptions(antialias=True)

        # 缺陷表格内的行号计数器。
        self.defectCounter = 0
        self.lastLoggedDefectState = False
        self.gateRoiInitialized = False
        self.isCriticalWarningActive = False

        # 状态栏临时消息恢复定时器。
        self.statusRestoreTimer = QTimer(self)
        self.statusRestoreTimer.setSingleShot(True)
        self.statusRestoreTimer.timeout.connect(self._restoreReadyStatus)

        # 时钟刷新定时器：每秒更新一次当前时间显示。
        self.clockTimer = QTimer(self)
        self.clockTimer.setInterval(1000)
        self.clockTimer.timeout.connect(self._updateCurrentTime)

        self._buildMenuBar()
        self._buildToolBar()
        self._buildCentralArea()
        self._buildControlDock()
        self._buildStatusBar()
        self._connectInternalSignals()

        self._updateCurrentTime()
        self.clockTimer.start()

    def _buildMenuBar(self) -> None:
        """构建顶部菜单栏。"""
        menuBar = self.menuBar()

        self.fileMenu = menuBar.addMenu("文件(File)")
        self.settingsMenu = menuBar.addMenu("设置(Settings)")
        self.viewMenu = menuBar.addMenu("视图(View)")
        self.helpMenu = menuBar.addMenu("帮助(Help)")

        self.openAction = QAction("打开", self)
        self.saveAction = QAction("保存", self)
        self.exitAction = QAction("退出", self)

        self.fileMenu.addAction(self.openAction)
        self.fileMenu.addAction(self.saveAction)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.exitAction)

    def _buildToolBar(self) -> None:
        """构建工具栏和核心动作按钮。"""
        toolBar = QToolBar("主工具栏", self)
        toolBar.setMovable(False)
        toolBar.setIconSize(QSize(24, 24))
        self.addToolBar(Qt.TopToolBarArea, toolBar)

        # 使用系统标准图标，保证跨平台可用。
        self.openToolAction = QAction(self._standardIcon(QStyle.SP_DialogOpenButton), "打开", self)
        self.saveToolAction = QAction(self._standardIcon(QStyle.SP_DialogSaveButton), "保存", self)
        self.startDetectAction = QAction(self._standardIcon(QStyle.SP_MediaPlay), "开始检测", self)
        self.stopDetectAction = QAction(self._standardIcon(QStyle.SP_MediaStop), "停止检测", self)
        self.reportToolAction = QAction(self._standardIcon(QStyle.SP_FileDialogDetailedView), "生成报告", self)

        toolBar.addAction(self.openToolAction)
        toolBar.addAction(self.saveToolAction)
        toolBar.addSeparator()
        toolBar.addAction(self.startDetectAction)
        toolBar.addAction(self.stopDetectAction)
        toolBar.addSeparator()
        toolBar.addAction(self.reportToolAction)

    def _buildCentralArea(self) -> None:
        """
        构建中心区域。

        结构说明：
        - 上半区：A-Scan 波形绘图；
        - 下半区：缺陷列表表格。
        """
        centralWidget = QWidget(self)
        centralLayout = QVBoxLayout(centralWidget)
        centralLayout.setContentsMargins(10, 8, 10, 8)
        centralLayout.setSpacing(8)

        splitter = QSplitter(Qt.Vertical, centralWidget)

        # A-Scan 绘图区：背景黑色，网格绿色（按需求实现）。
        self.aScanPlot = pg.PlotWidget(title="A-Scan 波形")
        self.aScanPlot.setBackground("#000000")
        self.aScanPlot.showGrid(x=True, y=True, alpha=0.35)
        self.aScanPlot.setLabel("left", "幅值")
        self.aScanPlot.setLabel("bottom", "时间(us)")

        # 坐标轴和网格采用绿色系，符合工业示波视觉习惯。
        greenPen = pg.mkPen("#00cc66", width=1.0)
        self.aScanPlot.getAxis("left").setPen(greenPen)
        self.aScanPlot.getAxis("bottom").setPen(greenPen)
        self.aScanPlot.getAxis("left").setTextPen(greenPen)
        self.aScanPlot.getAxis("bottom").setTextPen(greenPen)

        self.rawSignalCurve = self.aScanPlot.plot(
            pen=pg.mkPen(color="#4fd1ff", width=1.6),
            name="原始波形",
        )
        self.envelopeCurve = self.aScanPlot.plot(
            pen=pg.mkPen(color="#ffd166", width=1.6),
            name="包络",
        )

        self.thresholdLine = pg.InfiniteLine(
            pos=0.55,
            angle=0,
            pen=pg.mkPen("#ff6b6b", width=1.2, style=Qt.DashLine),
        )
        self.gateStartLine = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            pen=pg.mkPen("#00cc66", width=1.0, style=Qt.DotLine),
        )
        self.gateEndLine = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            pen=pg.mkPen("#00cc66", width=1.0, style=Qt.DotLine),
        )
        self.peakMarker = pg.ScatterPlotItem(
            size=10,
            brush=pg.mkBrush(255, 80, 80, 220),
            pen=pg.mkPen("#ffe1e1", width=1.0),
        )

        self.aScanPlot.addItem(self.thresholdLine)
        self.aScanPlot.addItem(self.gateStartLine)
        self.aScanPlot.addItem(self.gateEndLine)
        self.aScanPlot.addItem(self.peakMarker)

        # 闸门 Gate：可拖拽、可缩放的矩形 ROI，颜色为半透明红色。
        self.gateRoi = pg.RectROI(
            [6.0, 0.15],
            [12.0, 0.90],
            pen=pg.mkPen("#ff4d4f", width=2.0),
            movable=True,
            rotatable=False,
        )
        self.gateRoi.addScaleHandle([1, 1], [0, 0])
        self.gateRoi.addScaleHandle([0, 0], [1, 1])
        self.gateRoi.addScaleHandle([1, 0], [0, 1])
        self.gateRoi.addScaleHandle([0, 1], [1, 0])
        if hasattr(self.gateRoi, "setBrush"):
            self.gateRoi.setBrush(pg.mkBrush(255, 64, 64, 70))
        self.gateRoi.setZValue(8)
        self.aScanPlot.addItem(self.gateRoi)

        # 底部缺陷列表表格。
        self.defectTableWidget = QTableWidget(0, 3, self)
        self.defectTableWidget.setHorizontalHeaderLabels(["编号", "深度(mm)", "波幅"])  # 需求字段
        self.defectTableWidget.verticalHeader().setVisible(False)
        self.defectTableWidget.setAlternatingRowColors(True)
        self.defectTableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.defectTableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.defectTableWidget.horizontalHeader().setStretchLastSection(True)

        splitter.addWidget(self.aScanPlot)
        splitter.addWidget(self.defectTableWidget)
        splitter.setSizes([560, 210])

        centralLayout.addWidget(splitter)
        self.setCentralWidget(centralWidget)

    def _buildControlDock(self) -> None:
        """构建右侧控制面板（DockWidget）。"""
        self.controlDockWidget = QDockWidget("检测控制面板", self)
        self.controlDockWidget.setAllowedAreas(Qt.RightDockWidgetArea)

        dockContainer = QWidget(self.controlDockWidget)
        dockLayout = QVBoxLayout(dockContainer)
        dockLayout.setContentsMargins(10, 10, 10, 10)
        dockLayout.setSpacing(12)

        # 增益控制：滑动条 + 微调框，范围 0~110 dB。
        gainContainer = QWidget(dockContainer)
        gainLayout = QHBoxLayout(gainContainer)
        gainLayout.setContentsMargins(0, 0, 0, 0)
        gainLayout.setSpacing(8)

        self.gainSlider = QSlider(Qt.Horizontal, gainContainer)
        self.gainSlider.setRange(0, 110)
        self.gainSlider.setValue(18)

        self.gainSpinBox = QDoubleSpinBox(gainContainer)
        self.gainSpinBox.setRange(0.0, 110.0)
        self.gainSpinBox.setDecimals(1)
        self.gainSpinBox.setValue(18.0)
        self.gainSpinBox.setSuffix(" dB")

        gainLayout.addWidget(self.gainSlider)
        gainLayout.addWidget(self.gainSpinBox)

        # 声程范围输入框，范围 0~500 mm。
        self.rangeSpinBox = QDoubleSpinBox(dockContainer)
        self.rangeSpinBox.setRange(0.0, 500.0)
        self.rangeSpinBox.setDecimals(1)
        self.rangeSpinBox.setValue(120.0)
        self.rangeSpinBox.setSuffix(" mm")

        # 声速设置：钢、铝、自定义。
        self.velocityComboBox = QComboBox(dockContainer)
        self.velocityComboBox.addItems(["钢 5900m/s", "铝 6300m/s", "自定义"])

        self.customVelocitySpinBox = QDoubleSpinBox(dockContainer)
        self.customVelocitySpinBox.setRange(500.0, 9000.0)
        self.customVelocitySpinBox.setDecimals(0)
        self.customVelocitySpinBox.setValue(5900.0)
        self.customVelocitySpinBox.setSuffix(" m/s")
        self.customVelocitySpinBox.setVisible(False)

        # 参数应用按钮。
        self.applyParametersButton = QPushButton("应用参数", dockContainer)

        formLayout = QFormLayout()
        formLayout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        formLayout.addRow("增益控制", gainContainer)
        formLayout.addRow("声程范围", self.rangeSpinBox)
        formLayout.addRow("声速设置", self.velocityComboBox)
        formLayout.addRow("自定义声速", self.customVelocitySpinBox)

        dockLayout.addLayout(formLayout)
        dockLayout.addWidget(self.applyParametersButton)

        # 右侧数据面板：实时显示定量计算结果。
        dataPanelGroup = QGroupBox("缺陷定量数据", dockContainer)
        dataPanelLayout = QFormLayout(dataPanelGroup)
        dataPanelLayout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.depthResultLabel = QLabel("-- mm")
        self.horizontalResultLabel = QLabel("-- mm")
        self.kValueLabel = QLabel("2.00")
        self.dbDifferenceLabel = QLabel("-- dB")
        self.peakPercentLabel = QLabel("-- %")

        dataPanelLayout.addRow("深度 d", self.depthResultLabel)
        dataPanelLayout.addRow("水平距离 l", self.horizontalResultLabel)
        dataPanelLayout.addRow("K 值", self.kValueLabel)
        dataPanelLayout.addRow("dB 差值", self.dbDifferenceLabel)
        dataPanelLayout.addRow("波高比例", self.peakPercentLabel)

        dockLayout.addWidget(dataPanelGroup)
        dockLayout.addStretch(1)

        self.controlDockWidget.setWidget(dockContainer)
        self.addDockWidget(Qt.RightDockWidgetArea, self.controlDockWidget)

    def _buildStatusBar(self) -> None:
        """
        构建底部状态栏。

        需显示三项：
        - 系统就绪；
        - 当前时间；
        - 探头连接状态（模拟模式）。
        """
        statusBar = QStatusBar(self)
        self.setStatusBar(statusBar)

        self.systemStatusLabel = QLabel("系统就绪")
        self.currentTimeLabel = QLabel("当前时间: --")
        self.probeStatusLabel = QLabel("探头连接状态：模拟模式")

        statusBar.addPermanentWidget(self.systemStatusLabel)
        statusBar.addPermanentWidget(self._buildStatusSeparator())
        statusBar.addPermanentWidget(self.currentTimeLabel)
        statusBar.addPermanentWidget(self._buildStatusSeparator())
        statusBar.addPermanentWidget(self.probeStatusLabel)

    def _connectInternalSignals(self) -> None:
        """连接界面事件与视图信号。"""
        # 菜单动作与工具栏动作复用同一逻辑。
        self.openAction.triggered.connect(self.openRequested.emit)
        self.saveAction.triggered.connect(self.saveRequested.emit)
        self.exitAction.triggered.connect(self.close)

        self.openToolAction.triggered.connect(self.openRequested.emit)
        self.saveToolAction.triggered.connect(self.saveRequested.emit)
        self.startDetectAction.triggered.connect(self.startRequested.emit)
        self.stopDetectAction.triggered.connect(self.stopRequested.emit)
        self.reportToolAction.triggered.connect(self.reportRequested.emit)

        # 参数联动：滑动条与微调框双向同步。
        self.gainSlider.valueChanged.connect(self._syncGainFromSlider)
        self.gainSpinBox.valueChanged.connect(self._syncGainFromSpinBox)

        self.velocityComboBox.currentIndexChanged.connect(self._onVelocityModeChanged)
        self.applyParametersButton.clicked.connect(self._emitParameters)

    def _syncGainFromSlider(self, sliderValue: int) -> None:
        """滑动条变化时同步更新增益输入框。"""
        if abs(self.gainSpinBox.value() - float(sliderValue)) > 1e-6:
            self.gainSpinBox.blockSignals(True)
            self.gainSpinBox.setValue(float(sliderValue))
            self.gainSpinBox.blockSignals(False)

    def _syncGainFromSpinBox(self, spinValue: float) -> None:
        """微调框变化时同步更新增益滑动条。"""
        roundedValue = int(round(spinValue))
        if self.gainSlider.value() != roundedValue:
            self.gainSlider.blockSignals(True)
            self.gainSlider.setValue(roundedValue)
            self.gainSlider.blockSignals(False)

    def _onVelocityModeChanged(self, currentIndex: int) -> None:
        """声速模式切换逻辑。"""
        isCustomMode = currentIndex == 2
        self.customVelocitySpinBox.setVisible(isCustomMode)

    def _emitParameters(self) -> None:
        """读取控制面板参数并发给控制器。"""
        self.parametersApplied.emit(self.collectParameters())

    def collectParameters(self) -> dict[str, float]:
        """
        从右侧控制面板收集参数。

        说明：
        - 该方法只组织数据，不做业务运算；
        - 返回字段与 Model 参数名保持一致，便于控制器直传。
        """
        velocityText = self.velocityComboBox.currentText()
        if velocityText.startswith("钢"):
            soundVelocity = 5900.0
        elif velocityText.startswith("铝"):
            soundVelocity = 6300.0
        else:
            soundVelocity = self.customVelocitySpinBox.value()

        scanDepth = self.rangeSpinBox.value()
        return {
            "gainDb": self.gainSpinBox.value(),
            "scanDepthMm": scanDepth,
            "soundVelocityMps": soundVelocity,
            # 使用全量声程作为默认检测门，便于示例工程快速观察效果。
            "gateStartMm": 0.0,
            "gateEndMm": max(1.0, scanDepth),
        }

    def loadParameters(self, parameters: dict[str, float]) -> None:
        """将模型参数回填到界面控件。"""
        if "gainDb" in parameters:
            self.gainSpinBox.setValue(float(parameters["gainDb"]))
        if "scanDepthMm" in parameters:
            self.rangeSpinBox.setValue(float(parameters["scanDepthMm"]))

        if "soundVelocityMps" in parameters:
            velocity = float(parameters["soundVelocityMps"])
            if abs(velocity - 5900.0) < 1e-6:
                self.velocityComboBox.setCurrentIndex(0)
            elif abs(velocity - 6300.0) < 1e-6:
                self.velocityComboBox.setCurrentIndex(1)
            else:
                self.velocityComboBox.setCurrentIndex(2)
                self.customVelocitySpinBox.setValue(velocity)

    def updateAScanPlot(
        self,
        timeAxisUs: np.ndarray,
        rawSignal: np.ndarray,
        envelopeSignal: np.ndarray,
        thresholdLevel: float,
        gateRangeUs: tuple[float, float],
        peakTimeUs: float,
        peakAmplitude: float,
        defectDetected: bool,
    ) -> None:
        """刷新 A-Scan 绘图数据。"""
        self.rawSignalCurve.setData(timeAxisUs, rawSignal)
        self.envelopeCurve.setData(timeAxisUs, envelopeSignal)
        self.thresholdLine.setValue(thresholdLevel)
        self.gateStartLine.setValue(gateRangeUs[0])
        self.gateEndLine.setValue(gateRangeUs[1])

        if defectDetected:
            self.peakMarker.setData([peakTimeUs], [peakAmplitude])
        else:
            self.peakMarker.setData([], [])

        if timeAxisUs.size > 1:
            xMinUs = float(timeAxisUs[0])
            xMaxUs = float(timeAxisUs[-1])
            self.aScanPlot.setXRange(xMinUs, xMaxUs, padding=0.01)
            self._ensureGateRoiInsideXAxis(xMinUs, xMaxUs)
            self.aScanPlot.setYRange(-0.2, 1.3, padding=0.02)

    def getGateBounds(self) -> tuple[float, float, float, float]:
        """
        获取闸门 ROI 的边界。

        返回：
        - xMinUs, xMaxUs: 时间范围（us）
        - yMin, yMax: 幅值范围
        """
        gatePos = self.gateRoi.pos()
        gateSize = self.gateRoi.size()

        x1 = float(gatePos.x())
        x2 = float(gatePos.x() + gateSize.x())
        y1 = float(gatePos.y())
        y2 = float(gatePos.y() + gateSize.y())

        xMinUs = min(x1, x2)
        xMaxUs = max(x1, x2)
        yMin = min(y1, y2)
        yMax = max(y1, y2)
        return xMinUs, xMaxUs, yMin, yMax

    def prepareGateForTimeAxis(self, timeAxisUs: np.ndarray) -> None:
        """在执行闸门检测前，按当前时间轴范围初始化/收敛 ROI。"""
        if timeAxisUs.size < 2:
            return
        self._ensureGateRoiInsideXAxis(float(timeAxisUs[0]), float(timeAxisUs[-1]))

    def _ensureGateRoiInsideXAxis(self, xMinUs: float, xMaxUs: float) -> None:
        """
        保证闸门 ROI 在当前时间轴可见范围内。

        当参数变化导致 X 轴跨度变化时，自动对 ROI 做一次初始化或边界收敛，
        防止闸门落在可见区外导致无法触发检测。
        """
        if xMaxUs <= xMinUs:
            return

        xSpanUs = xMaxUs - xMinUs
        if not self.gateRoiInitialized:
            defaultWidthUs = max(0.20 * xSpanUs, 0.8)
            defaultPosUs = xMinUs + 0.38 * xSpanUs
            self.gateRoi.setPos([defaultPosUs, 0.15], update=False)
            self.gateRoi.setSize([defaultWidthUs, 0.90], update=False)
            self.gateRoiInitialized = True
            return

        gateXMinUs, gateXMaxUs, gateYMin, gateYMax = self.getGateBounds()
        gateWidthUs = max(gateXMaxUs - gateXMinUs, 0.15)
        gateWidthUs = float(np.clip(gateWidthUs, 0.15, xSpanUs))

        clampedXMinUs = float(np.clip(gateXMinUs, xMinUs, xMaxUs - gateWidthUs))
        gateHeight = max(gateYMax - gateYMin, 0.08)
        self.gateRoi.setPos([clampedXMinUs, gateYMin], update=False)
        self.gateRoi.setSize([gateWidthUs, gateHeight], update=False)

    def updateBScanImage(self, bScanMatrix: np.ndarray) -> None:
        """
        B-Scan 更新接口占位。

        当前功能列表仅要求 A-Scan + 缺陷表格，此接口保留用于与既有控制器兼容，
        后续扩展到双图布局时可直接接入。
        """
        _ = bScanMatrix

    def updateStatusPanel(
        self,
        frameCounter: int,
        peakAmplitude: float,
        defectDistanceMm: Optional[float],
        confidence: float,
        pointCount: int,
        defectDetected: bool,
    ) -> None:
        """
        更新状态与缺陷表格。

        - 当检测状态由“未告警”变为“告警”时，向表格追加一条缺陷记录；
        - 保留方法签名，确保与控制器调用保持一致。
        """
        _ = frameCounter
        _ = confidence
        _ = pointCount

        # 若当前在红色报警显示期，暂不覆盖报警文本。
        if not self.isCriticalWarningActive:
            if defectDetected:
                self.systemStatusLabel.setText("检测告警")
            else:
                self.systemStatusLabel.setText("系统就绪")

        # 仅在告警上升沿记录一次，避免同一缺陷重复刷表。
        if defectDetected and not self.lastLoggedDefectState and defectDistanceMm is not None:
            self._appendDefectRow(defectDistanceMm, peakAmplitude)
        self.lastLoggedDefectState = defectDetected

    def updateQuantitativePanel(
        self,
        depthMm: Optional[float],
        horizontalDistanceMm: Optional[float],
        dbDifference: Optional[float],
        peakPercent: float,
        kValue: float,
    ) -> None:
        """
        更新右侧“缺陷定量数据”。

        - 深度与水平距离保留 2 位小数；
        - dB 差值显示正负号；
        - 波高按百分比显示。
        """
        self.kValueLabel.setText(f"{kValue:.2f}")

        if depthMm is None:
            self.depthResultLabel.setText("-- mm")
        else:
            self.depthResultLabel.setText(f"{depthMm:.2f} mm")

        if horizontalDistanceMm is None:
            self.horizontalResultLabel.setText("-- mm")
        else:
            self.horizontalResultLabel.setText(f"{horizontalDistanceMm:.2f} mm")

        if dbDifference is None:
            self.dbDifferenceLabel.setText("-- dB")
        else:
            self.dbDifferenceLabel.setText(f"{dbDifference:+.2f} dB")

        self.peakPercentLabel.setText(f"{peakPercent:.1f} %")

    def showStatusMessage(self, message: str, durationMs: int = 1800, isWarning: bool = False) -> None:
        """显示临时状态消息，可选红色告警样式。"""
        self.systemStatusLabel.setText(message)
        if isWarning:
            self.isCriticalWarningActive = True
            self.systemStatusLabel.setStyleSheet("color: #ff4d4f; font-weight: 700;")
        else:
            self.isCriticalWarningActive = False
            self.systemStatusLabel.setStyleSheet("")
        self.statusRestoreTimer.start(max(durationMs, 200))

    def _appendDefectRow(self, defectDepthMm: float, amplitude: float) -> None:
        """向缺陷列表中追加一条记录。"""
        self.defectCounter += 1
        rowIndex = self.defectTableWidget.rowCount()
        self.defectTableWidget.insertRow(rowIndex)

        self.defectTableWidget.setItem(rowIndex, 0, QTableWidgetItem(str(self.defectCounter)))
        self.defectTableWidget.setItem(rowIndex, 1, QTableWidgetItem(f"{defectDepthMm:.2f}"))
        self.defectTableWidget.setItem(rowIndex, 2, QTableWidgetItem(f"{amplitude:.3f}"))
        self.defectTableWidget.scrollToBottom()

    def _updateCurrentTime(self) -> None:
        """更新状态栏中的当前时间文本。"""
        nowText = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.currentTimeLabel.setText(f"当前时间: {nowText}")

    def _restoreReadyStatus(self) -> None:
        """恢复默认系统状态文本。"""
        self.isCriticalWarningActive = False
        self.systemStatusLabel.setStyleSheet("")
        if self.lastLoggedDefectState:
            self.systemStatusLabel.setText("检测告警")
        else:
            self.systemStatusLabel.setText("系统就绪")

    @staticmethod
    def _buildStatusSeparator() -> QLabel:
        """生成状态栏分隔符标签。"""
        separatorLabel = QLabel(" | ")
        separatorLabel.setStyleSheet("color: #7f8c99;")
        return separatorLabel

    def _standardIcon(self, iconStyle: QStyle.StandardPixmap) -> QIcon:
        """获取系统标准图标，避免资源文件依赖。"""
        return self.style().standardIcon(iconStyle)
