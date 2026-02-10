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
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
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
    freezeToggled = pyqtSignal(bool)
    peakHoldToggled = pyqtSignal(bool)
    referenceCaptureRequested = pyqtSignal()
    referenceClearRequested = pyqtSignal()
    triggerModeChanged = pyqtSignal(str)
    unitModeChanged = pyqtSignal(str)
    recordStartRequested = pyqtSignal()
    recordStopRequested = pyqtSignal()
    parametersApplied = pyqtSignal(dict)
    defectLogged = pyqtSignal(dict)
    defectRecordsDeleted = pyqtSignal(object)
    defectRecordsCleared = pyqtSignal()
    velocityCalibrationRequested = pyqtSignal()
    zeroCalibrationRequested = pyqtSignal()
    saveCalibrationRequested = pyqtSignal()
    loadCalibrationRequested = pyqtSignal()

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
        self.defectUidCounter = 0
        self.lastLoggedDefectState = False
        self.currentDefectDetected = False
        self.isCriticalWarningActive = False
        self.realtimeRowInitialized = False
        self.gateUiSyncLocked = False
        self.gateLinesInitialized = False
        self.gateTimeMinUs = 0.0
        self.gateTimeMaxUs = 100.0
        self.gateMinWidthUs = 0.04
        self.gridVisible = True
        self.displayUnitMode = "us"
        self.currentSoundVelocityMps = 5900.0
        self.currentProbeDelayUs = 0.0
        self.lastTimeAxisUs = np.array([], dtype=np.float32)

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
        self.reportAction = QAction("生成报告", self)
        self.startScanAction = QAction("开始检测", self)
        self.stopScanAction = QAction("停止检测", self)
        self.freezeAction = QAction("冻结波形", self)
        self.freezeAction.setCheckable(True)
        self.singleShotAction = QAction("单次采样", self)
        self.captureReferenceAction = QAction("捕获参考波形", self)
        self.clearReferenceAction = QAction("清除参考波形", self)
        self.peakHoldAction = QAction("峰值保持", self)
        self.peakHoldAction.setCheckable(True)
        self.startRecordAction = QAction("开始记录", self)
        self.stopRecordAction = QAction("停止记录", self)
        self.deleteRecordAction = QAction("删除选中记录", self)
        self.clearRecordAction = QAction("清空历史记录", self)
        self.exitAction = QAction("退出", self)
        self.deleteRecordAction.setShortcut("Delete")

        self.fileMenu.addAction(self.openAction)
        self.fileMenu.addAction(self.saveAction)
        self.fileMenu.addAction(self.reportAction)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.startScanAction)
        self.fileMenu.addAction(self.stopScanAction)
        self.fileMenu.addAction(self.freezeAction)
        self.fileMenu.addAction(self.singleShotAction)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.captureReferenceAction)
        self.fileMenu.addAction(self.clearReferenceAction)
        self.fileMenu.addAction(self.peakHoldAction)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.startRecordAction)
        self.fileMenu.addAction(self.stopRecordAction)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.deleteRecordAction)
        self.fileMenu.addAction(self.clearRecordAction)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.exitAction)

        self.applyParametersAction = QAction("应用当前参数", self)
        self.resetGateAction = QAction("闸门复位", self)
        self.velocityCalibrationAction = QAction("声速校准", self)
        self.zeroCalibrationAction = QAction("零点校准", self)
        self.saveCalibrationAction = QAction("保存校准", self)
        self.loadCalibrationAction = QAction("加载校准", self)
        self.settingsMenu.addAction(self.applyParametersAction)
        self.settingsMenu.addAction(self.resetGateAction)
        self.settingsMenu.addSeparator()
        self.settingsMenu.addAction(self.velocityCalibrationAction)
        self.settingsMenu.addAction(self.zeroCalibrationAction)
        self.settingsMenu.addAction(self.saveCalibrationAction)
        self.settingsMenu.addAction(self.loadCalibrationAction)

        self.autoScaleAction = QAction("自动缩放波形", self)
        self.toggleGridAction = QAction("显示网格", self)
        self.toggleGridAction.setCheckable(True)
        self.toggleGridAction.setChecked(True)
        self.clearPeakAction = QAction("清除峰值标记", self)
        self.viewMenu.addAction(self.autoScaleAction)
        self.viewMenu.addAction(self.toggleGridAction)
        self.viewMenu.addAction(self.clearPeakAction)

        self.aboutAction = QAction("关于本系统", self)
        self.helpMenu.addAction(self.aboutAction)

    def _buildToolBar(self) -> None:
        """构建工具栏和核心动作按钮。"""
        toolBar = QToolBar("主工具栏", self)
        toolBar.setMovable(False)
        toolBar.setIconSize(QSize(24, 24))
        toolBar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolBar.setStyleSheet(
            "QToolButton { color: #dfe8f2; font-weight: 600; padding: 4px 10px; }"
            "QToolButton:hover { background-color: rgba(90, 120, 148, 80); border-radius: 5px; }"
        )
        self.addToolBar(Qt.TopToolBarArea, toolBar)

        # 使用系统标准图标，保证跨平台可用。
        self.openToolAction = QAction(self._standardIcon(QStyle.SP_DialogOpenButton), "打开", self)
        self.saveToolAction = QAction(self._standardIcon(QStyle.SP_DialogSaveButton), "保存", self)
        self.startDetectAction = QAction(self._standardIcon(QStyle.SP_MediaPlay), "开始检测", self)
        self.stopDetectAction = QAction(self._standardIcon(QStyle.SP_MediaStop), "停止检测", self)
        self.freezeToolAction = QAction(self._standardIcon(QStyle.SP_MediaPause), "冻结", self)
        self.freezeToolAction.setCheckable(True)
        self.singleShotToolAction = QAction(self._standardIcon(QStyle.SP_MediaSkipForward), "单次", self)
        self.reportToolAction = QAction(self._standardIcon(QStyle.SP_FileDialogDetailedView), "生成报告", self)

        self.openToolAction.setStatusTip("打开检测数据文件")
        self.saveToolAction.setStatusTip("保存当前波形数据")
        self.startDetectAction.setStatusTip("开始实时检测")
        self.stopDetectAction.setStatusTip("停止实时检测")
        self.freezeToolAction.setStatusTip("冻结/恢复波形刷新")
        self.singleShotToolAction.setStatusTip("执行单次采样")
        self.reportToolAction.setStatusTip("生成检测报告")

        toolBar.addAction(self.openToolAction)
        toolBar.addAction(self.saveToolAction)
        toolBar.addSeparator()
        toolBar.addAction(self.startDetectAction)
        toolBar.addAction(self.stopDetectAction)
        toolBar.addAction(self.freezeToolAction)
        toolBar.addAction(self.singleShotToolAction)
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
        self.aScanPlot.getPlotItem().getViewBox().setMenuEnabled(False)
        self.aScanPlot.getPlotItem().hideButtons()
        self.aScanPlot.setContextMenuPolicy(Qt.CustomContextMenu)

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
        self.referenceEnvelopeCurve = self.aScanPlot.plot(
            pen=pg.mkPen(color="#c084fc", width=1.4, style=Qt.DashLine),
            name="参考包络",
        )
        self.peakHoldCurve = self.aScanPlot.plot(
            pen=pg.mkPen(color="#7ae582", width=1.2),
            name="峰值保持",
        )

        self.thresholdLine = pg.InfiniteLine(
            pos=0.80,
            angle=0,
            pen=pg.mkPen("#ff5252", width=1.6, style=Qt.DashLine),
            movable=True,
        )
        self.gateStartLine = pg.InfiniteLine(
            pos=8.0,
            angle=90,
            pen=pg.mkPen("#ff7a7a", width=1.4, style=Qt.SolidLine),
            movable=True,
        )
        self.gateEndLine = pg.InfiniteLine(
            pos=18.0,
            angle=90,
            pen=pg.mkPen("#ff7a7a", width=1.4, style=Qt.SolidLine),
            movable=True,
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

        # 双游标：用于读数差值（时间差/深度差）。
        self.cursorLineA = pg.InfiniteLine(
            pos=5.0,
            angle=90,
            pen=pg.mkPen("#66b3ff", width=1.2),
            movable=True,
        )
        self.cursorLineB = pg.InfiniteLine(
            pos=12.0,
            angle=90,
            pen=pg.mkPen("#ffb86b", width=1.2),
            movable=True,
        )
        self.aScanPlot.addItem(self.cursorLineA)
        self.aScanPlot.addItem(self.cursorLineB)
        self.cursorLabelA = pg.TextItem(
            text="A",
            color="#66b3ff",
            anchor=(0.5, 1.0),
            fill=pg.mkBrush(8, 12, 18, 170),
            border=pg.mkPen("#66b3ff", width=0.8),
        )
        self.cursorLabelB = pg.TextItem(
            text="B",
            color="#ffb86b",
            anchor=(0.5, 1.0),
            fill=pg.mkBrush(18, 12, 8, 170),
            border=pg.mkPen("#ffb86b", width=0.8),
        )
        self.aScanPlot.addItem(self.cursorLabelA)
        self.aScanPlot.addItem(self.cursorLabelB)

        # 底部缺陷列表表格。
        self.defectTableWidget = QTableWidget(0, 3, self)
        self.defectTableWidget.setHorizontalHeaderLabels(["编号", "深度(mm)", "波幅"])  # 需求字段
        self.defectTableWidget.verticalHeader().setVisible(False)
        self.defectTableWidget.setAlternatingRowColors(True)
        self.defectTableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.defectTableWidget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.defectTableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.defectTableWidget.horizontalHeader().setStretchLastSection(True)
        self.defectTableWidget.setContextMenuPolicy(Qt.CustomContextMenu)

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

        # 探头中心频率（MHz）：用于控制仿真波形周期快慢。
        self.pulseFrequencyMhzSpinBox = QDoubleSpinBox(dockContainer)
        self.pulseFrequencyMhzSpinBox.setRange(0.50, 10.00)
        self.pulseFrequencyMhzSpinBox.setDecimals(2)
        self.pulseFrequencyMhzSpinBox.setValue(2.50)
        self.pulseFrequencyMhzSpinBox.setSuffix(" MHz")

        # 刷新间隔（ms）：用于控制画面刷新速度，便于肉眼观察。
        self.refreshIntervalMsSpinBox = QDoubleSpinBox(dockContainer)
        self.refreshIntervalMsSpinBox.setRange(30.0, 2000.0)
        self.refreshIntervalMsSpinBox.setDecimals(0)
        self.refreshIntervalMsSpinBox.setSingleStep(10.0)
        self.refreshIntervalMsSpinBox.setValue(120.0)
        self.refreshIntervalMsSpinBox.setSuffix(" ms")

        # 参数应用按钮。
        self.applyParametersButton = QPushButton("应用参数", dockContainer)

        formLayout = QFormLayout()
        formLayout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        formLayout.addRow("增益控制", gainContainer)
        formLayout.addRow("声程范围", self.rangeSpinBox)
        formLayout.addRow("探头频率", self.pulseFrequencyMhzSpinBox)
        formLayout.addRow("刷新间隔", self.refreshIntervalMsSpinBox)
        formLayout.addRow("声速设置", self.velocityComboBox)
        formLayout.addRow("自定义声速", self.customVelocitySpinBox)

        dockLayout.addLayout(formLayout)
        dockLayout.addWidget(self.applyParametersButton)

        # 记录控制：与检测启动解耦，防止“点击即写入”。
        recordGroup = QGroupBox("记录控制", dockContainer)
        recordLayout = QVBoxLayout(recordGroup)
        recordLayout.setContentsMargins(8, 8, 8, 8)
        recordLayout.setSpacing(6)
        self.recordStateLabel = QLabel("记录状态：关闭", recordGroup)
        self.startRecordButton = QPushButton("开始记录", recordGroup)
        self.stopRecordButton = QPushButton("停止记录", recordGroup)
        self.stopRecordButton.setEnabled(False)
        recordLayout.addWidget(self.recordStateLabel)
        recordLayout.addWidget(self.startRecordButton)
        recordLayout.addWidget(self.stopRecordButton)
        dockLayout.addWidget(recordGroup)

        # 采集控制：冻结、单次、触发模式、峰值保持、参考波形。
        acquisitionGroup = QGroupBox("采集控制", dockContainer)
        acquisitionLayout = QFormLayout(acquisitionGroup)
        acquisitionLayout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.triggerModeComboBox = QComboBox(acquisitionGroup)
        self.triggerModeComboBox.addItems(["自动", "闸门触发"])
        self.unitModeComboBox = QComboBox(acquisitionGroup)
        self.unitModeComboBox.addItems(["时间(us)", "深度(mm)"])

        acquisitionButtonRow = QWidget(acquisitionGroup)
        acquisitionButtonLayout = QHBoxLayout(acquisitionButtonRow)
        acquisitionButtonLayout.setContentsMargins(0, 0, 0, 0)
        acquisitionButtonLayout.setSpacing(6)
        self.freezeButton = QPushButton("冻结", acquisitionButtonRow)
        self.freezeButton.setCheckable(True)
        self.singleShotButton = QPushButton("单次采样", acquisitionButtonRow)
        acquisitionButtonLayout.addWidget(self.freezeButton)
        acquisitionButtonLayout.addWidget(self.singleShotButton)

        self.peakHoldCheckBox = QCheckBox("峰值保持", acquisitionGroup)

        referenceButtonRow = QWidget(acquisitionGroup)
        referenceButtonLayout = QHBoxLayout(referenceButtonRow)
        referenceButtonLayout.setContentsMargins(0, 0, 0, 0)
        referenceButtonLayout.setSpacing(6)
        self.captureReferenceButton = QPushButton("捕获参考", referenceButtonRow)
        self.clearReferenceButton = QPushButton("清除参考", referenceButtonRow)
        referenceButtonLayout.addWidget(self.captureReferenceButton)
        referenceButtonLayout.addWidget(self.clearReferenceButton)

        acquisitionLayout.addRow("触发模式", self.triggerModeComboBox)
        acquisitionLayout.addRow("显示单位", self.unitModeComboBox)
        acquisitionLayout.addRow("采样操作", acquisitionButtonRow)
        acquisitionLayout.addRow("", self.peakHoldCheckBox)
        acquisitionLayout.addRow("参考波形", referenceButtonRow)

        dockLayout.addWidget(acquisitionGroup)

        # 闸门设置：对齐主流工业 UT 界面，采用 Start / Width / Level 三参数。
        gatePanelGroup = QGroupBox("闸门设置 (Gate A)", dockContainer)
        gatePanelLayout = QFormLayout(gatePanelGroup)
        gatePanelLayout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.gateStartUsSpinBox = QDoubleSpinBox(gatePanelGroup)
        self.gateStartUsSpinBox.setRange(0.0, 99999.0)
        self.gateStartUsSpinBox.setDecimals(2)
        self.gateStartUsSpinBox.setValue(8.0)
        self.gateStartUsSpinBox.setSuffix(" us")

        self.gateWidthUsSpinBox = QDoubleSpinBox(gatePanelGroup)
        self.gateWidthUsSpinBox.setRange(0.04, 99999.0)
        self.gateWidthUsSpinBox.setDecimals(2)
        self.gateWidthUsSpinBox.setValue(10.0)
        self.gateWidthUsSpinBox.setSuffix(" us")

        self.gateLevelSpinBox = QDoubleSpinBox(gatePanelGroup)
        self.gateLevelSpinBox.setRange(-0.20, 1.50)
        self.gateLevelSpinBox.setDecimals(3)
        self.gateLevelSpinBox.setSingleStep(0.01)
        self.gateLevelSpinBox.setValue(0.80)

        gatePanelLayout.addRow("起点 Start", self.gateStartUsSpinBox)
        gatePanelLayout.addRow("宽度 Width", self.gateWidthUsSpinBox)
        gatePanelLayout.addRow("门限 Level", self.gateLevelSpinBox)
        self._refreshGateSpinBoxSuffix()

        dockLayout.addWidget(gatePanelGroup)

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

        # 游标读数面板：显示双游标时间差与深度差。
        cursorPanelGroup = QGroupBox("游标读数", dockContainer)
        cursorPanelLayout = QFormLayout(cursorPanelGroup)
        cursorPanelLayout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.cursorAValueLabel = QLabel("--")
        self.cursorBValueLabel = QLabel("--")
        self.cursorDeltaValueLabel = QLabel("--")
        self.cursorDepthDeltaLabel = QLabel("--")

        cursorPanelLayout.addRow("游标 A", self.cursorAValueLabel)
        cursorPanelLayout.addRow("游标 B", self.cursorBValueLabel)
        cursorPanelLayout.addRow("差值 Δ", self.cursorDeltaValueLabel)
        cursorPanelLayout.addRow("深度差 Δd", self.cursorDepthDeltaLabel)
        dockLayout.addWidget(cursorPanelGroup)

        # 校准结果面板：显示当前声速与零点延迟。
        calibrationPanelGroup = QGroupBox("校准参数", dockContainer)
        calibrationPanelLayout = QFormLayout(calibrationPanelGroup)
        calibrationPanelLayout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.calibratedVelocityLabel = QLabel("5900 m/s")
        self.calibratedDelayLabel = QLabel("0.00 us")
        calibrationPanelLayout.addRow("声速", self.calibratedVelocityLabel)
        calibrationPanelLayout.addRow("零点延迟", self.calibratedDelayLabel)
        dockLayout.addWidget(calibrationPanelGroup)
        dockLayout.addStretch(1)

        # 右侧面板使用滚动区域包装，窗口高度不足时自动显示垂直滚动条。
        controlScrollArea = QScrollArea(self.controlDockWidget)
        controlScrollArea.setWidgetResizable(True)
        controlScrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        controlScrollArea.setWidget(dockContainer)

        self.controlDockWidget.setWidget(controlScrollArea)
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
        self.reportAction.triggered.connect(self.reportRequested.emit)
        self.startScanAction.triggered.connect(self.startRequested.emit)
        self.stopScanAction.triggered.connect(self.stopRequested.emit)
        self.freezeAction.toggled.connect(self.freezeToggled.emit)
        self.singleShotAction.triggered.connect(self.singleShotRequested.emit)
        self.captureReferenceAction.triggered.connect(self.referenceCaptureRequested.emit)
        self.clearReferenceAction.triggered.connect(self.referenceClearRequested.emit)
        self.peakHoldAction.toggled.connect(self.peakHoldToggled.emit)
        self.startRecordAction.triggered.connect(self.recordStartRequested.emit)
        self.stopRecordAction.triggered.connect(self.recordStopRequested.emit)
        self.deleteRecordAction.triggered.connect(self.deleteSelectedDefectRows)
        self.clearRecordAction.triggered.connect(self.clearDefectHistory)
        self.exitAction.triggered.connect(self.close)

        self.openToolAction.triggered.connect(self.openRequested.emit)
        self.saveToolAction.triggered.connect(self.saveRequested.emit)
        self.startDetectAction.triggered.connect(self.startRequested.emit)
        self.stopDetectAction.triggered.connect(self.stopRequested.emit)
        self.freezeToolAction.toggled.connect(self.freezeToggled.emit)
        self.singleShotToolAction.triggered.connect(self.singleShotRequested.emit)
        self.reportToolAction.triggered.connect(self.reportRequested.emit)

        # 参数联动：滑动条与微调框双向同步。
        self.gainSlider.valueChanged.connect(self._syncGainFromSlider)
        self.gainSpinBox.valueChanged.connect(self._syncGainFromSpinBox)

        self.velocityComboBox.currentIndexChanged.connect(self._onVelocityModeChanged)
        self.applyParametersButton.clicked.connect(self._emitParameters)
        self.applyParametersAction.triggered.connect(self._emitParameters)
        self.startRecordButton.clicked.connect(self.recordStartRequested.emit)
        self.stopRecordButton.clicked.connect(self.recordStopRequested.emit)
        self.freezeButton.toggled.connect(self.freezeToggled.emit)
        self.singleShotButton.clicked.connect(self.singleShotRequested.emit)
        self.peakHoldCheckBox.toggled.connect(self.peakHoldToggled.emit)
        self.captureReferenceButton.clicked.connect(self.referenceCaptureRequested.emit)
        self.clearReferenceButton.clicked.connect(self.referenceClearRequested.emit)
        self.triggerModeComboBox.currentTextChanged.connect(self.triggerModeChanged.emit)
        self.unitModeComboBox.currentTextChanged.connect(self.unitModeChanged.emit)

        self.autoScaleAction.triggered.connect(self._autoScalePlot)
        self.toggleGridAction.toggled.connect(self._toggleGridVisibility)
        self.clearPeakAction.triggered.connect(self._clearPeakMarker)
        self.resetGateAction.triggered.connect(self._resetGateLinesToDefault)
        self.velocityCalibrationAction.triggered.connect(self.velocityCalibrationRequested.emit)
        self.zeroCalibrationAction.triggered.connect(self.zeroCalibrationRequested.emit)
        self.saveCalibrationAction.triggered.connect(self.saveCalibrationRequested.emit)
        self.loadCalibrationAction.triggered.connect(self.loadCalibrationRequested.emit)
        self.aboutAction.triggered.connect(self._showAboutDialog)

        self.aScanPlot.customContextMenuRequested.connect(self._showPlotContextMenu)
        self.defectTableWidget.customContextMenuRequested.connect(self._showDefectTableContextMenu)

        # 闸门线与数值输入双向同步。
        self.gateStartLine.sigPositionChanged.connect(self._syncGateInputsFromLines)
        self.gateEndLine.sigPositionChanged.connect(self._syncGateInputsFromLines)
        self.thresholdLine.sigPositionChanged.connect(self._syncGateInputsFromLines)
        self.gateStartUsSpinBox.valueChanged.connect(self._syncGateLinesFromInputs)
        self.gateWidthUsSpinBox.valueChanged.connect(self._syncGateLinesFromInputs)
        self.gateLevelSpinBox.valueChanged.connect(self._syncGateLinesFromInputs)
        self.cursorLineA.sigPositionChanged.connect(self._updateCursorReadout)
        self.cursorLineB.sigPositionChanged.connect(self._updateCursorReadout)

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

    def _toDepthMm(self, timeUs: float) -> float:
        """将传播时间(us)转换为等效深度(mm)。"""
        effectiveTimeUs = max(timeUs - self.currentProbeDelayUs, 0.0)
        depthMeter = (effectiveTimeUs * 1e-6 * self.currentSoundVelocityMps) / 2.0
        return depthMeter * 1000.0

    def _toTimeUs(self, depthMm: float) -> float:
        """将等效深度(mm)转换为传播时间(us)。"""
        depthMeter = max(depthMm, 0.0) / 1000.0
        return self.currentProbeDelayUs + (2.0 * depthMeter / max(self.currentSoundVelocityMps, 1.0)) * 1e6

    def _unitToDisplay(self, timeUs: float) -> float:
        """按当前单位模式转换显示值。"""
        if self.displayUnitMode == "mm":
            return self._toDepthMm(timeUs)
        return timeUs

    def _displayToUnitUs(self, displayValue: float) -> float:
        """将当前单位显示值转换为时间(us)。"""
        if self.displayUnitMode == "mm":
            return self._toTimeUs(displayValue)
        return displayValue

    def _refreshGateSpinBoxSuffix(self) -> None:
        """根据单位模式刷新闸门输入框后缀。"""
        if self.displayUnitMode == "mm":
            self.gateStartUsSpinBox.setSuffix(" mm")
            self.gateWidthUsSpinBox.setSuffix(" mm")
        else:
            self.gateStartUsSpinBox.setSuffix(" us")
            self.gateWidthUsSpinBox.setSuffix(" us")

    def _syncGateInputsFromLines(self) -> None:
        """闸门线拖拽后，回填 Start/Width/Level 输入框。"""
        if self.gateUiSyncLocked:
            return
        self.gateUiSyncLocked = True
        try:
            startUs = min(float(self.gateStartLine.value()), float(self.gateEndLine.value()))
            endUs = max(float(self.gateStartLine.value()), float(self.gateEndLine.value()))
            widthUs = max(endUs - startUs, self.gateMinWidthUs)
            level = float(self.thresholdLine.value())

            startDisplay = self._unitToDisplay(startUs)
            endDisplay = self._unitToDisplay(endUs)
            widthDisplay = max(endDisplay - startDisplay, 0.001)

            self.gateStartUsSpinBox.setValue(startDisplay)
            self.gateWidthUsSpinBox.setValue(widthDisplay)
            self.gateLevelSpinBox.setValue(level)
        finally:
            self.gateUiSyncLocked = False
        self._updateCursorReadout()

    def _syncGateLinesFromInputs(self) -> None:
        """Start/Width/Level 输入变化后，同步更新闸门线。"""
        if self.gateUiSyncLocked:
            return

        self.gateUiSyncLocked = True
        try:
            startDisplay = float(self.gateStartUsSpinBox.value())
            widthDisplay = max(float(self.gateWidthUsSpinBox.value()), 0.001)
            endDisplay = startDisplay + widthDisplay

            startUs = self._displayToUnitUs(startDisplay)
            endUs = self._displayToUnitUs(endDisplay)
            if endUs < startUs:
                startUs, endUs = endUs, startUs

            widthUs = max(endUs - startUs, self.gateMinWidthUs)
            endUs = startUs + widthUs
            level = float(self.gateLevelSpinBox.value())

            # 对齐当前时间窗边界，防止闸门跑到可视区域外。
            if endUs > self.gateTimeMaxUs:
                endUs = self.gateTimeMaxUs
                startUs = max(self.gateTimeMinUs, endUs - widthUs)
            if startUs < self.gateTimeMinUs:
                startUs = self.gateTimeMinUs
                endUs = min(self.gateTimeMaxUs, startUs + widthUs)

            self.gateStartLine.setValue(startUs)
            self.gateEndLine.setValue(endUs)
            self.thresholdLine.setValue(level)
        finally:
            self.gateUiSyncLocked = False
        self._syncGateInputsFromLines()

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
            "pulseFrequencyHz": self.pulseFrequencyMhzSpinBox.value() * 1_000_000.0,
            "soundVelocityMps": soundVelocity,
            "refreshIntervalMs": self.refreshIntervalMsSpinBox.value(),
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
        if "pulseFrequencyHz" in parameters:
            self.pulseFrequencyMhzSpinBox.setValue(float(parameters["pulseFrequencyHz"]) / 1_000_000.0)

        if "soundVelocityMps" in parameters:
            velocity = float(parameters["soundVelocityMps"])
            if abs(velocity - 5900.0) < 1e-6:
                self.velocityComboBox.setCurrentIndex(0)
            elif abs(velocity - 6300.0) < 1e-6:
                self.velocityComboBox.setCurrentIndex(1)
            else:
                self.velocityComboBox.setCurrentIndex(2)
                self.customVelocitySpinBox.setValue(velocity)

        probeDelayUs = float(parameters.get("probeDelayUs", self.currentProbeDelayUs))
        self.setCalibrationState(
            soundVelocityMps=float(parameters.get("soundVelocityMps", self.currentSoundVelocityMps)),
            probeDelayUs=probeDelayUs,
        )

    def setAcquisitionIntervalMs(self, intervalMs: int) -> None:
        """同步显示控制器的采样刷新间隔。"""
        self.refreshIntervalMsSpinBox.setValue(float(intervalMs))

    def setFreezeState(self, isFrozen: bool) -> None:
        """同步冻结按钮与动作状态。"""
        self.freezeAction.blockSignals(True)
        self.freezeToolAction.blockSignals(True)
        self.freezeButton.blockSignals(True)
        self.freezeAction.setChecked(isFrozen)
        self.freezeToolAction.setChecked(isFrozen)
        self.freezeButton.setChecked(isFrozen)
        self.freezeAction.blockSignals(False)
        self.freezeToolAction.blockSignals(False)
        self.freezeButton.blockSignals(False)

    def setPeakHoldState(self, isEnabled: bool) -> None:
        """同步峰值保持按钮状态。"""
        self.peakHoldAction.blockSignals(True)
        self.peakHoldCheckBox.blockSignals(True)
        self.peakHoldAction.setChecked(isEnabled)
        self.peakHoldCheckBox.setChecked(isEnabled)
        self.peakHoldAction.blockSignals(False)
        self.peakHoldCheckBox.blockSignals(False)

    def setTriggerMode(self, triggerMode: str) -> None:
        """同步触发模式下拉框。"""
        textValue = "闸门触发" if triggerMode.lower().startswith("gate") else "自动"
        self.triggerModeComboBox.blockSignals(True)
        self.triggerModeComboBox.setCurrentText(textValue)
        self.triggerModeComboBox.blockSignals(False)

    def setDisplayUnitMode(self, unitMode: str) -> None:
        """设置显示单位模式（us/mm）。"""
        normalizedMode = "mm" if unitMode.lower().startswith("mm") else "us"
        if self.displayUnitMode == normalizedMode:
            return
        self.displayUnitMode = normalizedMode

        self.unitModeComboBox.blockSignals(True)
        self.unitModeComboBox.setCurrentText("深度(mm)" if normalizedMode == "mm" else "时间(us)")
        self.unitModeComboBox.blockSignals(False)
        self.aScanPlot.setLabel("bottom", "时间(us) / 等效深度(mm)")
        self._refreshGateSpinBoxSuffix()
        if self.lastTimeAxisUs.size > 1:
            self.prepareGateForTimeAxis(self.lastTimeAxisUs)
        self._syncGateInputsFromLines()

    def setCalibrationState(self, soundVelocityMps: float, probeDelayUs: float) -> None:
        """同步校准参数显示。"""
        self.currentSoundVelocityMps = float(soundVelocityMps)
        self.currentProbeDelayUs = float(probeDelayUs)
        self.calibratedVelocityLabel.setText(f"{self.currentSoundVelocityMps:.1f} m/s")
        self.calibratedDelayLabel.setText(f"{self.currentProbeDelayUs:.2f} us")
        self._syncGateInputsFromLines()

    def _updateCursorReadout(self) -> None:
        """刷新双游标读数（时间/深度差）。"""
        cursorAUs = float(self.cursorLineA.value())
        cursorBUs = float(self.cursorLineB.value())
        deltaUs = abs(cursorBUs - cursorAUs)
        deltaDepthMm = abs(self._toDepthMm(cursorBUs) - self._toDepthMm(cursorAUs))

        if self.displayUnitMode == "mm":
            cursorADisplay = self._toDepthMm(cursorAUs)
            cursorBDisplay = self._toDepthMm(cursorBUs)
            deltaDisplay = abs(cursorBDisplay - cursorADisplay)
            self.cursorAValueLabel.setText(f"{cursorADisplay:.2f} mm")
            self.cursorBValueLabel.setText(f"{cursorBDisplay:.2f} mm")
            self.cursorDeltaValueLabel.setText(f"{deltaDisplay:.2f} mm")
        else:
            self.cursorAValueLabel.setText(f"{cursorAUs:.2f} us")
            self.cursorBValueLabel.setText(f"{cursorBUs:.2f} us")
            self.cursorDeltaValueLabel.setText(f"{deltaUs:.2f} us")

        self.cursorDepthDeltaLabel.setText(f"{deltaDepthMm:.2f} mm")

        viewRange = self.aScanPlot.getPlotItem().viewRange()
        yMin, yMax = viewRange[1]
        ySpan = max(yMax - yMin, 1e-6)
        yLabel = yMax - ySpan * 0.02
        self.cursorLabelA.setPos(cursorAUs, yLabel)
        self.cursorLabelB.setPos(cursorBUs, yLabel)
        if self.displayUnitMode == "mm":
            self.cursorLabelA.setText(f"A {self._toDepthMm(cursorAUs):.2f}mm", color="#66b3ff")
            self.cursorLabelB.setText(f"B {self._toDepthMm(cursorBUs):.2f}mm", color="#ffb86b")
        else:
            self.cursorLabelA.setText(f"A {cursorAUs:.2f}us", color="#66b3ff")
            self.cursorLabelB.setText(f"B {cursorBUs:.2f}us", color="#ffb86b")

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
        referenceEnvelope: Optional[np.ndarray] = None,
        peakHoldEnvelope: Optional[np.ndarray] = None,
    ) -> None:
        """刷新 A-Scan 绘图数据。"""
        self.prepareGateForTimeAxis(timeAxisUs)
        self.lastTimeAxisUs = np.asarray(timeAxisUs, dtype=np.float32)

        self.rawSignalCurve.setData(timeAxisUs, rawSignal)
        self.envelopeCurve.setData(timeAxisUs, envelopeSignal)
        if referenceEnvelope is not None and referenceEnvelope.size == timeAxisUs.size:
            self.referenceEnvelopeCurve.setData(timeAxisUs, referenceEnvelope)
        else:
            self.referenceEnvelopeCurve.setData([], [])
        if peakHoldEnvelope is not None and peakHoldEnvelope.size == timeAxisUs.size:
            self.peakHoldCurve.setData(timeAxisUs, peakHoldEnvelope)
        else:
            self.peakHoldCurve.setData([], [])

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
            self.aScanPlot.setYRange(-0.2, 1.3, padding=0.02)
            self.cursorLineA.setBounds((xMinUs, xMaxUs))
            self.cursorLineB.setBounds((xMinUs, xMaxUs))
            self._updateCursorReadout()

    def getGateConfig(self) -> tuple[float, float, float, float]:
        """
        获取闸门配置（Start/End/Width/Level）。

        说明：
        - Start/End 由两条可拖拽竖线定义；
        - Level 由横线阈值定义；
        - Width 由 End - Start 计算得到。
        """
        startUs = min(float(self.gateStartLine.value()), float(self.gateEndLine.value()))
        endUs = max(float(self.gateStartLine.value()), float(self.gateEndLine.value()))
        widthUs = max(endUs - startUs, self.gateMinWidthUs)
        level = float(self.thresholdLine.value())
        return startUs, endUs, widthUs, level

    def prepareGateForTimeAxis(self, timeAxisUs: np.ndarray) -> None:
        """根据时间轴范围初始化/约束闸门范围。"""
        if timeAxisUs.size < 2:
            return

        xMinUs = float(timeAxisUs[0])
        xMaxUs = float(timeAxisUs[-1])
        if xMaxUs <= xMinUs:
            return

        self.gateTimeMinUs = xMinUs
        self.gateTimeMaxUs = xMaxUs
        xSpanUs = xMaxUs - xMinUs
        self.gateMinWidthUs = max(xSpanUs * 0.01, 0.04)

        # 更新数值输入范围。
        self.gateUiSyncLocked = True
        try:
            startMin = self._unitToDisplay(xMinUs)
            startMax = self._unitToDisplay(xMaxUs - self.gateMinWidthUs)
            widthMin = max(self._unitToDisplay(xMinUs + self.gateMinWidthUs) - self._unitToDisplay(xMinUs), 0.001)
            widthMax = max(self._unitToDisplay(xMaxUs) - self._unitToDisplay(xMinUs), widthMin)
            self.gateStartUsSpinBox.setRange(min(startMin, startMax), max(startMin, startMax))
            self.gateWidthUsSpinBox.setRange(min(widthMin, widthMax), max(widthMin, widthMax))
        finally:
            self.gateUiSyncLocked = False

        # 更新线条可拖拽边界。
        self.gateStartLine.setBounds((xMinUs, xMaxUs))
        self.gateEndLine.setBounds((xMinUs, xMaxUs))
        self.thresholdLine.setBounds((-0.20, 1.50))
        self.cursorLineA.setBounds((xMinUs, xMaxUs))
        self.cursorLineB.setBounds((xMinUs, xMaxUs))

        if not self.gateLinesInitialized:
            defaultStartUs = xMinUs + xSpanUs * 0.25
            defaultWidthUs = xSpanUs * 0.30
            self.gateUiSyncLocked = True
            try:
                self.gateStartLine.setValue(defaultStartUs)
                self.gateEndLine.setValue(defaultStartUs + defaultWidthUs)
                self.thresholdLine.setValue(0.80)
            finally:
                self.gateUiSyncLocked = False
            self.gateLinesInitialized = True

        # 二次约束：防止拖拽或参数缩放后超边界。
        startUs, endUs, widthUs, level = self.getGateConfig()
        if endUs > xMaxUs:
            endUs = xMaxUs
            startUs = max(xMinUs, endUs - widthUs)
        if startUs < xMinUs:
            startUs = xMinUs
            endUs = min(xMaxUs, startUs + widthUs)

        self.gateUiSyncLocked = True
        try:
            self.gateStartLine.setValue(startUs)
            self.gateEndLine.setValue(endUs)
            self.thresholdLine.setValue(level)
            cursorAUs = float(np.clip(self.cursorLineA.value(), xMinUs, xMaxUs))
            cursorBUs = float(np.clip(self.cursorLineB.value(), xMinUs, xMaxUs))
            self.cursorLineA.setValue(cursorAUs)
            self.cursorLineB.setValue(cursorBUs)
        finally:
            self.gateUiSyncLocked = False

        self._syncGateInputsFromLines()

    def _resetGateLinesToDefault(self) -> None:
        """将闸门线恢复到默认比例位置（Start=25%，Width=30%，Level=80%）。"""
        spanUs = self.gateTimeMaxUs - self.gateTimeMinUs
        if spanUs <= 0.0:
            return

        startUs = self.gateTimeMinUs + spanUs * 0.25
        widthUs = max(spanUs * 0.30, self.gateMinWidthUs)
        endUs = min(self.gateTimeMaxUs, startUs + widthUs)
        if (endUs - startUs) < self.gateMinWidthUs:
            startUs = max(self.gateTimeMinUs, endUs - self.gateMinWidthUs)

        self.gateUiSyncLocked = True
        try:
            self.gateStartLine.setValue(startUs)
            self.gateEndLine.setValue(endUs)
            self.thresholdLine.setValue(0.80)
        finally:
            self.gateUiSyncLocked = False
        self._syncGateInputsFromLines()
        self.showStatusMessage("闸门已恢复默认。", 1200)

    def _autoScalePlot(self) -> None:
        """执行波形自动缩放。"""
        self.aScanPlot.enableAutoRange(axis="xy", enable=True)
        self.showStatusMessage("波形已自动缩放。", 1200)

    def _toggleGridVisibility(self, isVisible: bool) -> None:
        """切换绘图区网格显示状态。"""
        self.gridVisible = bool(isVisible)
        gridAlpha = 0.35 if self.gridVisible else 0.0
        self.aScanPlot.showGrid(x=self.gridVisible, y=self.gridVisible, alpha=gridAlpha)

    def _clearPeakMarker(self) -> None:
        """清除当前红色峰值标记。"""
        self.peakMarker.setData([], [])
        self.showStatusMessage("峰值标记已清除。", 1200)

    def _showPlotContextMenu(self, localPos) -> None:
        """绘图区右键菜单（中文）。"""
        globalPos = self.aScanPlot.mapToGlobal(localPos)
        menu = QMenu(self)

        autoScaleAction = menu.addAction("自动缩放波形")
        resetGateAction = menu.addAction("闸门复位")
        clearPeakAction = menu.addAction("清除峰值标记")
        menu.addSeparator()
        toggleGridAction = menu.addAction("显示网格")
        toggleGridAction.setCheckable(True)
        toggleGridAction.setChecked(self.gridVisible)

        selectedAction = menu.exec_(globalPos)
        if selectedAction is None:
            return
        if selectedAction == autoScaleAction:
            self._autoScalePlot()
        elif selectedAction == resetGateAction:
            self._resetGateLinesToDefault()
        elif selectedAction == clearPeakAction:
            self._clearPeakMarker()
        elif selectedAction == toggleGridAction:
            self._toggleGridVisibility(toggleGridAction.isChecked())
            self.toggleGridAction.setChecked(toggleGridAction.isChecked())

    def _showDefectTableContextMenu(self, localPos) -> None:
        """缺陷表格右键菜单（中文）。"""
        globalPos = self.defectTableWidget.viewport().mapToGlobal(localPos)
        menu = QMenu(self)

        deleteAction = menu.addAction("删除选中记录")
        clearAction = menu.addAction("清空历史记录")

        selectedAction = menu.exec_(globalPos)
        if selectedAction is None:
            return
        if selectedAction == deleteAction:
            self.deleteSelectedDefectRows()
        elif selectedAction == clearAction:
            self.clearDefectHistory()

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
        allowLogging: bool = False,
    ) -> bool:
        """
        更新状态与缺陷表格。

        - 当检测状态由“未告警”变为“告警”时，向表格追加一条缺陷记录；
        - 保留方法签名，确保与控制器调用保持一致。
        """
        _ = frameCounter
        _ = confidence
        _ = pointCount
        self.currentDefectDetected = defectDetected
        newDefectLogged = False

        # 若当前在红色报警显示期，暂不覆盖报警文本。
        if not self.isCriticalWarningActive:
            if defectDetected:
                self.systemStatusLabel.setText("检测告警")
            else:
                self.systemStatusLabel.setText("系统就绪")

        # 下方表格第 1 行固定展示实时波形数值，保证监看时有连续反馈。
        self._updateRealtimeWaveRow(defectDistanceMm, peakAmplitude)

        # 仅在记录开启且告警上升沿时写入，避免“未开始记录就入表”。
        if allowLogging and defectDetected and not self.lastLoggedDefectState and defectDistanceMm is not None:
            self._appendDefectRow(defectDistanceMm, peakAmplitude)
            newDefectLogged = True
        if allowLogging:
            self.lastLoggedDefectState = defectDetected
        else:
            self.lastLoggedDefectState = False
        return newDefectLogged

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
        self.defectUidCounter += 1
        recordUid = self.defectUidCounter
        rowIndex = self.defectTableWidget.rowCount()
        self.defectTableWidget.insertRow(rowIndex)

        indexItem = QTableWidgetItem(str(self.defectCounter))
        indexItem.setData(Qt.UserRole, recordUid)
        self.defectTableWidget.setItem(rowIndex, 0, indexItem)
        self.defectTableWidget.setItem(rowIndex, 1, QTableWidgetItem(f"{defectDepthMm:.2f}"))
        self.defectTableWidget.setItem(rowIndex, 2, QTableWidgetItem(f"{amplitude:.3f}"))
        self.defectTableWidget.scrollToBottom()
        self.defectLogged.emit(
            {
                "recordUid": recordUid,
                "displayId": self.defectCounter,
                "depthMm": float(defectDepthMm),
                "amplitude": float(amplitude),
            }
        )

    def deleteSelectedDefectRows(self) -> int:
        """
        删除当前选中的缺陷历史记录。

        返回值：
        - 实际删除的行数。
        """
        selectedRows = sorted({index.row() for index in self.defectTableWidget.selectedIndexes()}, reverse=True)
        deletedCount = 0
        deletedUids: list[int] = []
        for rowIndex in selectedRows:
            # 第 0 行是“实时”行，禁止删除。
            if rowIndex <= 0:
                continue
            uidItem = self.defectTableWidget.item(rowIndex, 0)
            if uidItem is not None:
                uidValue = uidItem.data(Qt.UserRole)
                if uidValue is not None:
                    deletedUids.append(int(uidValue))
            self.defectTableWidget.removeRow(rowIndex)
            deletedCount += 1

        if deletedCount > 0:
            self.defectRecordsDeleted.emit(deletedUids)
            self._renumberDefectRows()
            self.showStatusMessage(f"已删除 {deletedCount} 条记录。", 1500)
        else:
            self.showStatusMessage("未选择可删除的历史记录。", 1500)
        return deletedCount

    def clearDefectHistory(self) -> int:
        """
        清空全部历史缺陷记录（保留第 0 行“实时”）。

        返回值：
        - 清除的记录条数。
        """
        totalRows = self.defectTableWidget.rowCount()
        if totalRows <= 1:
            self.showStatusMessage("当前没有历史记录可清空。", 1500)
            return 0

        # 从后向前删除，避免索引错位。
        deletedUids: list[int] = []
        deletedCount = totalRows - 1
        for rowIndex in range(totalRows - 1, 0, -1):
            uidItem = self.defectTableWidget.item(rowIndex, 0)
            if uidItem is not None:
                uidValue = uidItem.data(Qt.UserRole)
                if uidValue is not None:
                    deletedUids.append(int(uidValue))
            self.defectTableWidget.removeRow(rowIndex)

        self.defectRecordsDeleted.emit(deletedUids)
        self.defectRecordsCleared.emit()
        self.defectCounter = 0
        self.lastLoggedDefectState = False
        self.showStatusMessage("历史记录已清空。", 1500)
        return deletedCount

    def _renumberDefectRows(self) -> None:
        """重排缺陷编号，保证删除后编号连续。"""
        historyIndex = 0
        for rowIndex in range(1, self.defectTableWidget.rowCount()):
            historyIndex += 1
            indexItem = self.defectTableWidget.item(rowIndex, 0)
            if indexItem is None:
                indexItem = QTableWidgetItem("")
                self.defectTableWidget.setItem(rowIndex, 0, indexItem)
            uidValue = indexItem.data(Qt.UserRole)
            indexItem.setText(str(historyIndex))
            indexItem.setData(Qt.UserRole, uidValue)
        self.defectCounter = historyIndex

    def _updateRealtimeWaveRow(self, depthMm: Optional[float], amplitude: float) -> None:
        """
        更新“实时”行数据。

        该行固定在表格第 0 行，不参与缺陷编号计数。
        """
        if not self.realtimeRowInitialized:
            self.defectTableWidget.insertRow(0)
            self.realtimeRowInitialized = True

        self.defectTableWidget.setItem(0, 0, QTableWidgetItem("实时"))
        if depthMm is None:
            self.defectTableWidget.setItem(0, 1, QTableWidgetItem("--"))
        else:
            self.defectTableWidget.setItem(0, 1, QTableWidgetItem(f"{depthMm:.2f}"))
        self.defectTableWidget.setItem(0, 2, QTableWidgetItem(f"{amplitude:.3f}"))

    def setRecordingState(self, isRecording: bool) -> None:
        """更新记录状态显示，不改变控制器业务状态。"""
        if isRecording:
            self.recordStateLabel.setText("记录状态：开启")
            self.recordStateLabel.setStyleSheet("color: #7fe7b2; font-weight: 700;")
            self.startRecordButton.setEnabled(False)
            self.stopRecordButton.setEnabled(True)
        else:
            self.recordStateLabel.setText("记录状态：关闭")
            self.recordStateLabel.setStyleSheet("color: #cfd8e3; font-weight: 600;")
            self.startRecordButton.setEnabled(True)
            self.stopRecordButton.setEnabled(False)
            self.lastLoggedDefectState = False

    def _updateCurrentTime(self) -> None:
        """更新状态栏中的当前时间文本。"""
        nowText = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.currentTimeLabel.setText(f"当前时间: {nowText}")

    def _restoreReadyStatus(self) -> None:
        """恢复默认系统状态文本。"""
        self.isCriticalWarningActive = False
        self.systemStatusLabel.setStyleSheet("")
        if self.currentDefectDetected:
            self.systemStatusLabel.setText("检测告警")
        else:
            self.systemStatusLabel.setText("系统就绪")

    def _showAboutDialog(self) -> None:
        """显示系统说明对话框。"""
        QMessageBox.information(
            self,
            "关于",
            "超声波智能辅助检测系统 V1.0\n"
            "A-Scan 实时仿真 + 线性闸门检测 + 缺陷定量分析。",
        )

    @staticmethod
    def _buildStatusSeparator() -> QLabel:
        """生成状态栏分隔符标签。"""
        separatorLabel = QLabel(" | ")
        separatorLabel.setStyleSheet("color: #7f8c99;")
        return separatorLabel

    def _standardIcon(self, iconStyle: QStyle.StandardPixmap) -> QIcon:
        """获取系统标准图标，避免资源文件依赖。"""
        return self.style().standardIcon(iconStyle)
