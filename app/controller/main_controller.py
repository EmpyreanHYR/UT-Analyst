"""超声检测系统控制器（Controller）。"""

from __future__ import annotations

import csv
import html
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from app.common.unit_converter import time_us_to_depth_mm
from app.common.report_generator import ReportGenerator, ReportConfig
from app.common.report_exporter import ReportExporter
from app.model.ultrasonic_model import UltrasonicSignalModel
from app.model.defect_analyzer import DefectAnalyzer, DefectRecord
from app.model.gate_analyzer import GateAnalyzer, GateConfig, GateResult
from app.model.scan_geometry import ScanGrid
from app.model.session_repository import FrameChunkStore, SessionRepository
from app.model.tcg import TcgPoint, TcgProfile
from app.view.main_window import MainWindow
from app.view.report_config_dialog import ReportConfigDialog
from app.view.report_preview_window import ReportPreviewWindow

logger = logging.getLogger("ut_analyst.controller")


class MainController(QObject):
    """
    主控制器。

    主要职责：
    1. 连接 View 的交互信号与 Model 的业务逻辑；
    2. 管理定时采样流程；
    3. 将 Model 计算结果更新到 View；
    4. 实现数据保存与检测报告导出流程。
    """

    def __init__(
        self,
        model: UltrasonicSignalModel,
        view: MainWindow,
        session_repository: SessionRepository | None = None,
        frame_chunk_store: FrameChunkStore | None = None,
        data_dir: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.view = view

        # 采样定时器：模拟在线实时采集（可后续替换为硬件回调）。
        self.acquisitionTimer = QTimer(self)
        self.acquisitionTimer.setInterval(120)

        # 记录告警状态变化，用于提示“首次告警”事件。
        self.lastDefectState = False
        self.kFactor = 2.0
        self.referenceScreenHeight = 0.80
        self.highAmplitudeScreenHeight = 1.00
        self.lastOverRangeState = False
        self.recordingEnabled = False
        self.freezeEnabled = False
        self.peakHoldEnabled = False
        self.triggerMode = "auto"
        self.referenceEnvelope: np.ndarray | None = None
        self.referenceRawSignal: np.ndarray | None = None
        self.referenceTimeAxisUs: np.ndarray | None = None
        self.peakHoldEnvelope: np.ndarray | None = None

        # 缓存最近一帧数据与定量结果，供导出与报告模块使用。
        self.lastFrameData: dict[str, Any] | None = None
        self.lastQuantitativeData: dict[str, Any] = {
            "depthMm": None,
            "horizontalDistanceMm": None,
            "dbDifference": None,
            "peakPercent": 0.0,
            "gateTriggered": False,
        }

        # 工件名称：可由用户自定义，用于报告导出。
        self.workpieceName: str = "工件-001"

        # 报告预览窗口与报告上下文缓存。
        self.reportPreviewWindow: ReportPreviewWindow | None = None
        self.currentReportHtmlTemplate = ""
        self.currentReportPixmap = QPixmap()
        self.currentReportImageDataUri = ""
        self.loggedDefectSnapshots: list[dict[str, Any]] = []

        # 增强功能模块。
        self.defectAnalyzer = DefectAnalyzer()
        self.reportGenerator = ReportGenerator()
        self.reportExporter = ReportExporter()
        self.reportConfig = ReportConfig()

        # 信号平均历史缓存。
        self.signalAverageEnabled = False
        self.signalAverageCount = 8
        self.signalAverageBuffer: list[np.ndarray] = []

        storage_root = Path(data_dir) if data_dir is not None else Path(__file__).resolve().parents[2] / "data"
        self.sessionRepository = session_repository or SessionRepository(
            storage_root / "ut_analyst.db"
        )
        self.frameChunkStore = frame_chunk_store or FrameChunkStore(
            storage_root / "sessions",
            self.sessionRepository,
        )
        self.activeSessionId: str | None = None
        self.lastSessionId: str | None = None
        self.replaySessionId: str | None = None
        self.replayFrames: list[dict[str, Any]] = []
        self.advancedGates: dict[str, GateConfig] = {
            "A": GateConfig("A", "闸门A", 25.0, 70.0, 0.55),
            "B": GateConfig("B", "闸门B", 40.0, 20.0, 0.60, enabled=False),
            "C": GateConfig("C", "闸门C", 70.0, 20.0, 0.65, enabled=False),
        }
        self.tcgEnabled = False
        self.tcgProfile = TcgProfile()
        self.scanGrid = ScanGrid(10, 10, 5.0, 5.0)
        self.cScanValues: dict[int, float] = {}

        self._bindSignals()
        self._initializeView()

    def _bindSignals(self) -> None:
        """绑定视图事件与控制器槽函数。"""
        self.view.startRequested.connect(self.startAcquisition)
        self.view.stopRequested.connect(self.stopAcquisition)
        self.view.singleShotRequested.connect(self.singleShotAcquisition)
        self.view.resetRequested.connect(self.resetSystem)
        self.view.freezeToggled.connect(self.setFreezeEnabled)
        self.view.peakHoldToggled.connect(self.setPeakHoldEnabled)
        self.view.referenceCaptureRequested.connect(self.captureReferenceTrace)
        self.view.referenceClearRequested.connect(self.clearReferenceTrace)
        self.view.triggerModeChanged.connect(self.setTriggerMode)
        self.view.unitModeChanged.connect(self.setDisplayUnitMode)
        self.view.recordStartRequested.connect(self.startRecording)
        self.view.recordStopRequested.connect(self.stopRecording)
        self.view.parametersApplied.connect(self.applyParameters)
        self.view.defectLogged.connect(self._onDefectLogged)
        self.view.defectRecordsDeleted.connect(self._onDefectRecordsDeleted)
        self.view.defectRecordsCleared.connect(self._onDefectRecordsCleared)
        self.view.velocityCalibrationRequested.connect(self.calibrateVelocity)
        self.view.zeroCalibrationRequested.connect(self.calibrateProbeDelay)
        self.view.saveCalibrationRequested.connect(self.saveCalibrationFile)
        self.view.loadCalibrationRequested.connect(self.loadCalibrationFile)

        # 功能列表 5：保存数据与报告生成。
        self.view.openRequested.connect(self.openDataFile)
        self.view.saveRequested.connect(self.saveWaveformData)
        self.view.reportRequested.connect(self.generateReport)

        # FFT频谱分析面板信号连接
        self.view.fftPanel.fftRequested.connect(self.computeFFT)
        self.view.fftPanel.filterApplied.connect(self.applyFilter)
        self.view.fftPanel.filterResetRequested.connect(self.resetFilter)
        self.view.fftPanel.signalAverageChanged.connect(self.setSignalAverage)
        self.view.signalFeaturesRequested.connect(self.showSignalFeatures)
        self.view.signalComparisonRequested.connect(self.compareWithReference)
        self.view.closing.connect(self.shutdown)
        self.view.replayPanel.refreshRequested.connect(self.refreshReplaySessions)
        self.view.replayPanel.sessionSelected.connect(self.loadReplaySession)
        self.view.replayPanel.frameChanged.connect(self.loadReplayFrame)
        self.view.advancedUTPanel.gateChanged.connect(self.updateAdvancedGate)
        self.view.advancedUTPanel.tcgChanged.connect(self.updateTcgProfile)

        # 统计分析面板信号连接
        self.view.statisticsPanel.refreshRequested.connect(self.refreshDefectStatistics)
        self.view.defectStatisticsRefreshRequested.connect(self.refreshDefectStatistics)

        self.acquisitionTimer.timeout.connect(self._refreshFrame)

    def _initializeView(self) -> None:
        """初始化界面显示并执行首次采样。"""
        self.view.loadParameters(self.model.getParameters())
        self.view.setAcquisitionIntervalMs(self.acquisitionTimer.interval())
        self.view.setFreezeState(False)
        self.view.setPeakHoldState(False)
        self.view.setTriggerMode(self.triggerMode)
        self.view.setDisplayUnitMode("us")
        self.view.setCalibrationState(
            soundVelocityMps=self.model.parameters["soundVelocityMps"],
            probeDelayUs=self.model.parameters.get("probeDelayUs", 0.0),
        )
        self.view.setRecordingState(False)
        self.view.showStatusMessage("参数初始化完成。")
        self._refreshFrame()
        self.refreshReplaySessions()

    def startAcquisition(self) -> None:
        """启动实时采集。"""
        if self.acquisitionTimer.isActive():
            self.view.showStatusMessage("采集已在运行。")
            return
        self._ensureActiveSession()
        if self.freezeEnabled:
            self.setFreezeEnabled(False)
        self.acquisitionTimer.start()
        logger.info("实时采集已启动，刷新间隔 %d ms", self.acquisitionTimer.interval())
        self.view.showStatusMessage("实时采集已启动。")

    def stopAcquisition(self) -> None:
        """停止实时采集。"""
        if not self.acquisitionTimer.isActive():
            if self.recordingEnabled:
                self.stopRecording(showMessage=False)
            self.view.showStatusMessage("采集已经停止。")
            return
        self.stopRecording(showMessage=False)
        self.acquisitionTimer.stop()
        self._finishActiveSession()
        logger.info("实时采集已停止")
        self.view.showStatusMessage("实时采集已停止。")

    def singleShotAcquisition(self) -> None:
        """执行一次单帧采样。"""
        session_started = self._ensureActiveSession()
        previousFreezeState = self.freezeEnabled
        if self.freezeEnabled:
            self.freezeEnabled = False
        self._refreshFrame()
        self.freezeEnabled = previousFreezeState
        if session_started and not self.acquisitionTimer.isActive():
            self._finishActiveSession()
        self.view.showStatusMessage("单次采样完成。")

    def resetSystem(self) -> None:
        """重置系统状态。"""
        self.stopAcquisition()
        self.stopRecording(showMessage=False)
        self.model.resetHistory()
        self.freezeEnabled = False
        self.peakHoldEnabled = False
        self.referenceEnvelope = None
        self.referenceTimeAxisUs = None
        self.peakHoldEnvelope = None
        self.view.setFreezeState(False)
        self.view.setPeakHoldState(False)
        self.view.clearDefectHistory()
        self.loggedDefectSnapshots.clear()
        self.lastDefectState = False
        self.lastOverRangeState = False
        self._refreshFrame()
        self.view.showStatusMessage("系统已重置。")

    def setFreezeEnabled(self, isEnabled: bool) -> None:
        """设置波形冻结状态。"""
        self.freezeEnabled = bool(isEnabled)
        self.view.setFreezeState(self.freezeEnabled)
        if self.freezeEnabled:
            self.view.showStatusMessage("波形已冻结。", 1400)
        else:
            self.view.showStatusMessage("波形刷新已恢复。", 1400)
            self._refreshFrame()

    def setPeakHoldEnabled(self, isEnabled: bool) -> None:
        """设置峰值保持状态。"""
        self.peakHoldEnabled = bool(isEnabled)
        self.view.setPeakHoldState(self.peakHoldEnabled)
        if not self.peakHoldEnabled:
            self.peakHoldEnvelope = None
            self.view.showStatusMessage("峰值保持已关闭。", 1400)
            self._refreshFrame()
        else:
            self.view.showStatusMessage("峰值保持已开启。", 1400)

    def captureReferenceTrace(self) -> None:
        """捕获当前包络为参考波形。"""
        if not self._ensureLatestFrameAvailable():
            self.view.showStatusMessage("当前无可用波形，无法捕获参考。", isWarning=True)
            return
        assert self.lastFrameData is not None
        self.referenceEnvelope = self.lastFrameData["envelopeSignal"].copy()
        self.referenceRawSignal = self.lastFrameData.get(
            "baseRawSignal",
            self.lastFrameData["rawSignal"],
        ).copy()
        self.referenceTimeAxisUs = self.lastFrameData["timeAxisUs"].copy()
        self.view.showStatusMessage("参考波形已捕获。", 1500)
        self._refreshFrame()

    def clearReferenceTrace(self) -> None:
        """清除参考波形。"""
        self.referenceEnvelope = None
        self.referenceRawSignal = None
        self.referenceTimeAxisUs = None
        self.view.showStatusMessage("参考波形已清除。", 1300)
        self._refreshFrame()

    def setTriggerMode(self, triggerModeText: str) -> None:
        """设置触发模式（自动/闸门触发）。"""
        normalizedMode = "gate" if "闸门" in triggerModeText.lower() or "gate" in triggerModeText.lower() else "auto"
        self.triggerMode = normalizedMode
        self.view.setTriggerMode(self.triggerMode)
        modeText = "闸门触发" if self.triggerMode == "gate" else "自动"
        self.view.showStatusMessage(f"触发模式：{modeText}", 1500)

    def setDisplayUnitMode(self, unitText: str) -> None:
        """设置界面显示单位。"""
        normalizedMode = "mm" if "mm" in unitText.lower() else "us"
        self.view.setDisplayUnitMode(normalizedMode)
        self.view.showStatusMessage(f"显示单位切换为：{normalizedMode}", 1300)

    def startRecording(self) -> None:
        """开启缺陷记录（仅对历史表格写入生效）。"""
        if not self.acquisitionTimer.isActive():
            self.view.showStatusMessage("请先开始检测，再开启记录。", durationMs=1800, isWarning=True)
            return
        if self.recordingEnabled:
            self.view.showStatusMessage("记录已开启。")
            return
        self.recordingEnabled = True
        self.view.setRecordingState(True)
        self.view.showStatusMessage("缺陷记录已开启。", 1600)

    def stopRecording(self, showMessage: bool = True) -> None:
        """停止缺陷记录。"""
        self.recordingEnabled = False
        self.view.setRecordingState(False)
        if showMessage:
            self.view.showStatusMessage("缺陷记录已停止。", 1500)

    def applyParameters(self, parameters: dict[str, float]) -> None:
        """应用用户在界面中设置的参数。"""
        parametersToApply = dict(parameters)
        refreshIntervalMs = int(
            np.clip(
                parametersToApply.pop("refreshIntervalMs", float(self.acquisitionTimer.interval())),
                30.0,
                2000.0,
            )
        )

        self.acquisitionTimer.setInterval(refreshIntervalMs)
        self.model.updateParameters(parametersToApply)
        self.view.loadParameters(self.model.getParameters())
        self.view.setAcquisitionIntervalMs(refreshIntervalMs)
        self.view.setCalibrationState(
            soundVelocityMps=self.model.parameters["soundVelocityMps"],
            probeDelayUs=self.model.parameters.get("probeDelayUs", 0.0),
        )
        self._refreshFrame()
        self.view.showStatusMessage(f"参数更新成功（刷新间隔 {refreshIntervalMs} ms）。")

    def _onDefectLogged(self, defectInfo: dict[str, Any]) -> None:
        """收到 View 新增缺陷记录事件后，抓取当前波形截图并缓存。"""
        recordUid = int(defectInfo.get("recordUid", 0))
        if recordUid <= 0:
            return

        capturePixmap = self.view.aScanPlot.grab()
        captureDataUri = self._pixmapToDataUri(capturePixmap)

        recordData = {
            "recordUid": recordUid,
            "displayId": int(defectInfo.get("displayId", 0)),
            "depthMm": float(defectInfo.get("depthMm", 0.0)),
            "amplitude": float(defectInfo.get("amplitude", 0.0)),
            "peakPercent": float(self.lastQuantitativeData.get("peakPercent", 0.0)),
            "detectedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "imageDataUri": captureDataUri,
        }

        # 若同一 UID 已存在，先移除旧记录，再追加最新截图。
        self.loggedDefectSnapshots = [
            existingRecord
            for existingRecord in self.loggedDefectSnapshots
            if int(existingRecord.get("recordUid", -1)) != recordUid
        ]
        self.loggedDefectSnapshots.append(recordData)
        if self.activeSessionId:
            self.sessionRepository.add_defect(
                session_id=self.activeSessionId,
                record_uid=recordUid,
                depth_mm=recordData["depthMm"],
                amplitude=recordData["amplitude"],
                timestamp=recordData["detectedAt"],
                snapshot_uri=captureDataUri,
            )

        # 自动刷新统计面板（如果可见）
        if self.view.statisticsDockWidget.isVisible():
            self.refreshDefectStatistics()

    def _onDefectRecordsDeleted(self, deletedUids: object) -> None:
        """同步删除被用户从表格中移除的缺陷截图记录。"""
        if not isinstance(deletedUids, list) or not deletedUids:
            return
        deletedSet = {int(uid) for uid in deletedUids}
        self.loggedDefectSnapshots = [
            existingRecord
            for existingRecord in self.loggedDefectSnapshots
            if int(existingRecord.get("recordUid", -1)) not in deletedSet
        ]

    def _onDefectRecordsCleared(self) -> None:
        """同步清空全部缺陷截图记录。"""
        self.loggedDefectSnapshots.clear()

    def calibrateVelocity(self) -> None:
        """根据已知厚度与实测传播时间校准声速。"""
        measuredTimeUs, isTimeConfirmed = QInputDialog.getDouble(
            self.view,
            "声速校准",
            "请输入实测往返时间(us):",
            20.0,
            0.01,
            999999.0,
            3,
        )
        if not isTimeConfirmed:
            return

        knownThicknessMm, isThicknessConfirmed = QInputDialog.getDouble(
            self.view,
            "声速校准",
            "请输入已知厚度(mm):",
            20.0,
            0.01,
            999999.0,
            3,
        )
        if not isThicknessConfirmed:
            return

        correctedTimeUs = max(float(measuredTimeUs) - self.model.parameters.get("probeDelayUs", 0.0), 0.01)
        calibratedVelocityMps = (2.0 * (float(knownThicknessMm) / 1000.0)) / (correctedTimeUs * 1e-6)
        self.model.updateParameters({"soundVelocityMps": calibratedVelocityMps})
        self.view.loadParameters(self.model.getParameters())
        self.view.setCalibrationState(
            soundVelocityMps=self.model.parameters["soundVelocityMps"],
            probeDelayUs=self.model.parameters.get("probeDelayUs", 0.0),
        )
        self._refreshFrame()
        self.view.showStatusMessage(f"声速校准完成：{self.model.parameters['soundVelocityMps']:.1f} m/s", 2200)
        logger.info("声速校准完成：%.1f m/s", self.model.parameters["soundVelocityMps"])

    def calibrateProbeDelay(self) -> None:
        """根据已知厚度与实测时间校准零点延迟。"""
        measuredTimeUs, isTimeConfirmed = QInputDialog.getDouble(
            self.view,
            "零点校准",
            "请输入实测往返时间(us):",
            20.0,
            0.01,
            999999.0,
            3,
        )
        if not isTimeConfirmed:
            return

        knownThicknessMm, isThicknessConfirmed = QInputDialog.getDouble(
            self.view,
            "零点校准",
            "请输入对应已知厚度(mm):",
            20.0,
            0.01,
            999999.0,
            3,
        )
        if not isThicknessConfirmed:
            return

        expectedTimeUs = (
            (2.0 * (float(knownThicknessMm) / 1000.0) / max(self.model.parameters["soundVelocityMps"], 1.0)) * 1e6
        )
        calibratedDelayUs = float(measuredTimeUs) - expectedTimeUs
        self.model.updateParameters({"probeDelayUs": calibratedDelayUs})
        self.view.loadParameters(self.model.getParameters())
        self.view.setCalibrationState(
            soundVelocityMps=self.model.parameters["soundVelocityMps"],
            probeDelayUs=self.model.parameters.get("probeDelayUs", 0.0),
        )
        self._refreshFrame()
        self.view.showStatusMessage(f"零点校准完成：{self.model.parameters.get('probeDelayUs', 0.0):.2f} us", 2200)
        logger.info("零点校准完成：%.2f us", self.model.parameters.get("probeDelayUs", 0.0))

    def saveCalibrationFile(self) -> None:
        """保存校准参数到 JSON 文件。"""
        defaultName = f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filePath, _ = QFileDialog.getSaveFileName(
            self.view,
            "保存校准参数",
            defaultName,
            "JSON 文件 (*.json)",
        )
        if not filePath:
            return

        outputPath = Path(filePath)
        if outputPath.suffix.lower() != ".json":
            outputPath = outputPath.with_suffix(".json")

        try:
            calibrationPayload = {
                "savedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "soundVelocityMps": self.model.parameters["soundVelocityMps"],
                "probeDelayUs": self.model.parameters.get("probeDelayUs", 0.0),
            }
            outputPath.write_text(json.dumps(calibrationPayload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.view.showStatusMessage(f"校准参数已保存：{outputPath.name}", 1800)
            logger.info("校准参数已保存：%s", outputPath)
        except Exception as error:  # pragma: no cover - GUI 场景下保底异常提示
            logger.error("保存校准失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"保存校准失败：{error}", durationMs=2600, isWarning=True)

    def loadCalibrationFile(self) -> None:
        """从 JSON 文件加载校准参数。"""
        filePath, _ = QFileDialog.getOpenFileName(
            self.view,
            "加载校准参数",
            "",
            "JSON 文件 (*.json)",
        )
        if not filePath:
            return

        try:
            calibrationContent = json.loads(Path(filePath).read_text(encoding="utf-8"))
            self.model.updateParameters(
                {
                    "soundVelocityMps": float(
                        calibrationContent.get("soundVelocityMps", self.model.parameters["soundVelocityMps"])
                    ),
                    "probeDelayUs": float(
                        calibrationContent.get("probeDelayUs", self.model.parameters.get("probeDelayUs", 0.0))
                    ),
                }
            )
            self.view.loadParameters(self.model.getParameters())
            self.view.setCalibrationState(
                soundVelocityMps=self.model.parameters["soundVelocityMps"],
                probeDelayUs=self.model.parameters.get("probeDelayUs", 0.0),
            )
            self._refreshFrame()
            self.view.showStatusMessage(f"校准参数已加载：{Path(filePath).name}", 1800)
            logger.info("校准参数已加载：%s", filePath)
        except Exception as error:  # pragma: no cover - GUI 场景下保底异常提示
            logger.error("加载校准失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"加载校准失败：{error}", durationMs=2600, isWarning=True)

    def openDataFile(self) -> None:
        """打开历史波形文件并回放到当前界面。"""
        filePath, _ = QFileDialog.getOpenFileName(
            self.view,
            "打开检测数据",
            "",
            "数据文件 (*.json *.csv)",
        )
        if not filePath:
            return
        inputPath = Path(filePath)
        try:
            if inputPath.suffix.lower() == ".csv":
                loadedParameters, timeAxisUs, rawSignal, envelopeSignal = self._loadWaveformFromCsv(inputPath)
            else:
                loadedParameters, timeAxisUs, rawSignal, envelopeSignal = self._loadWaveformFromJson(inputPath)

            if timeAxisUs.size < 2 or rawSignal.size != timeAxisUs.size or envelopeSignal.size != timeAxisUs.size:
                raise ValueError("波形数据维度无效，无法加载。")

            # 加载历史波形时暂停实时采集，避免下一帧立即覆盖。
            wasRunning = self.acquisitionTimer.isActive()
            if wasRunning:
                self.stopAcquisition()

            modelParameters = {
                key: float(value)
                for key, value in loadedParameters.items()
                if key in self.model.parameters
            }
            if modelParameters:
                self.model.updateParameters(modelParameters)

            refreshIntervalMs = loadedParameters.get("refreshIntervalMs")
            if refreshIntervalMs is not None:
                self.acquisitionTimer.setInterval(int(np.clip(float(refreshIntervalMs), 30.0, 2000.0)))

            # 同步模型缓存，使定量计算和导出逻辑与加载数据一致。
            self.model.pointCount = int(timeAxisUs.size)
            self.model.timeAxisUs = timeAxisUs.astype(np.float32)
            self.model.timeAxisSec = (self.model.timeAxisUs * 1e-6).astype(np.float32)
            historyRows = int(self.model.parameters["historyFrames"])
            self.model.bScanMatrix = np.zeros((historyRows, self.model.pointCount), dtype=np.float32)
            self.model.bScanMatrix[-1, :] = np.clip(envelopeSignal, 0.0, 1.2).astype(np.float32)

            frameData = {
                "timeAxisUs": self.model.timeAxisUs.copy(),
                "rawSignal": rawSignal.astype(np.float32),
                "envelopeSignal": envelopeSignal.astype(np.float32),
                "thresholdLevel": float(self.model.parameters["thresholdLevel"]),
                "gateRangeUs": (
                    float(self.model._depthMmToTimeSec(self.model.parameters["gateStartMm"]) * 1e6),
                    float(self.model._depthMmToTimeSec(self.model.parameters["gateEndMm"]) * 1e6),
                ),
                "peakAmplitude": 0.0,
                "peakTimeUs": 0.0,
                "defectDetected": False,
                "defectDistanceMm": None,
                "confidence": 0.0,
                "frameCounter": self.model.frameCounter,
                "bScanMatrix": self.model.bScanMatrix.copy(),
            }
            self.lastFrameData = frameData

            self.view.loadParameters(self.model.getParameters())
            self.view.setAcquisitionIntervalMs(self.acquisitionTimer.interval())
            self.view.setCalibrationState(
                soundVelocityMps=self.model.parameters["soundVelocityMps"],
                probeDelayUs=self.model.parameters.get("probeDelayUs", 0.0),
            )
            self._renderCurrentFrame(frameData)
            self.view.showStatusMessage(f"已加载波形文件：{inputPath.name}", 2000)
        except Exception as error:  # pragma: no cover - GUI 场景下保底异常提示
            logger.error("加载数据失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"加载数据失败：{error}", durationMs=3200, isWarning=True)

    def saveWaveformData(self) -> None:
        """
        保存当前波形数据。

        支持格式：
        - JSON：保存参数与完整数组；
        - CSV：保存参数段 + 波形明细列。
        """
        if not self._ensureLatestFrameAvailable():
            return

        defaultName = f"waveform_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filePath, selectedFilter = QFileDialog.getSaveFileName(
            self.view,
            "保存波形数据",
            defaultName,
            "JSON 文件 (*.json);;CSV 文件 (*.csv)",
        )
        if not filePath:
            return

        outputPath = Path(filePath)
        if outputPath.suffix.lower() not in {".json", ".csv"}:
            outputPath = outputPath.with_suffix(".csv" if "CSV" in selectedFilter else ".json")

        try:
            if outputPath.suffix.lower() == ".csv":
                self._saveWaveformAsCsv(outputPath)
            else:
                self._saveWaveformAsJson(outputPath)
            self.view.showStatusMessage(f"数据保存成功：{outputPath.name}")
            logger.info("波形数据已保存：%s", outputPath)
        except Exception as error:  # pragma: no cover - GUI 场景下保底异常提示
            logger.error("数据保存失败：%s", error, exc_info=True)
            self.view.showStatusMessage(
                f"数据保存失败：{error}",
                durationMs=3200,
                isWarning=True,
            )

    def generateReport(self) -> None:
        """
        生成检测报告。

        执行步骤：
        1. 抓取当前绘图区截图（grab）；
        2. 构造 HTML 模板字符串；
        3. 弹出预览窗口；
        4. 在预览窗口内点击“保存报告”后导出 HTML。
        """
        self.view.showStatusMessage("正在生成报告预览...", 1200)
        try:
            if not self._ensureLatestFrameAvailable():
                self.view.showStatusMessage("当前无可用波形数据，无法生成报告。", isWarning=True)
                return

            reportDialog = ReportConfigDialog(self.reportConfig, self.view)
            if reportDialog.exec_() != reportDialog.Accepted:
                return
            self.reportConfig = reportDialog.build_config()
            workpieceName = self.reportConfig.workpiece_name
            self.workpieceName = workpieceName

            waveformPixmap = self.view.aScanPlot.grab()
            overviewImageDataUri = self._pixmapToDataUri(waveformPixmap)
            defectRecords = sorted(
                self.loggedDefectSnapshots,
                key=lambda item: int(item.get("recordUid", 0)),
            )
            hasDefect = bool(defectRecords) or bool(self.lastQuantitativeData["gateTriggered"])
            if defectRecords:
                defectDepthMm = defectRecords[-1]["depthMm"]
            elif bool(self.lastQuantitativeData["gateTriggered"]):
                defectDepthMm = self.lastQuantitativeData["depthMm"]
            else:
                defectDepthMm = None
            decisionResult = "不合格" if hasDefect else "合格"
            detectionTimeText = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 使用增强的ReportGenerator生成报告
            self.currentReportHtmlTemplate = self.reportGenerator.generate_html_report(
                config=self.reportConfig,
                detection_time=detectionTimeText,
                decision_result=decisionResult,
                overview_image_data_uri=overviewImageDataUri,
                defect_records=[],
                defect_snapshots=defectRecords,
                parameters=self.model.getParameters() if self.lastFrameData else None,
            )
            self.currentReportPixmap = waveformPixmap
            self.currentReportImageDataUri = overviewImageDataUri

            # 弹出报告预览窗口。
            self.reportPreviewWindow = ReportPreviewWindow(
                waveformPixmap=waveformPixmap,
                reportHtml=self.currentReportHtmlTemplate,
                parent=self.view,
            )
            self.reportPreviewWindow.saveRequested.connect(self.saveCurrentReport)
            self.reportPreviewWindow.show()
            self.reportPreviewWindow.raise_()
            self.reportPreviewWindow.activateWindow()
            self.view.showStatusMessage("报告预览已打开。", 1800)
            logger.info("报告预览已生成")
        except Exception as error:  # pragma: no cover - GUI 场景下保底异常提示
            logger.error("生成报告失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"生成报告失败：{error}", durationMs=3500, isWarning=True)

    def saveCurrentReport(self) -> None:
        """将当前报告导出为 HTML。"""
        if not self.currentReportHtmlTemplate:
            self.view.showStatusMessage("报告内容为空，无法保存。", isWarning=True)
            return

        defaultName = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filePath, selectedFilter = QFileDialog.getSaveFileName(
            self.view,
            "保存检测报告",
            defaultName,
            "HTML 文件 (*.html);;PDF 文件 (*.pdf)",
        )
        if not filePath:
            return

        outputPath = Path(filePath)
        desired_suffix = ".pdf" if "PDF" in selectedFilter else ".html"
        if outputPath.suffix.lower() not in {".html", ".pdf"}:
            outputPath = outputPath.with_suffix(desired_suffix)

        try:
            if outputPath.suffix.lower() == ".pdf":
                report_hash = self.reportExporter.export_pdf(
                    self.currentReportHtmlTemplate,
                    outputPath,
                )
                report_format = "pdf"
            else:
                report_hash = self.reportExporter.export_html(
                    self.currentReportHtmlTemplate,
                    outputPath,
                )
                report_format = "html"

            session_id = self.activeSessionId or self.lastSessionId
            if session_id:
                self.sessionRepository.add_report(
                    session_id,
                    report_format,
                    outputPath,
                    report_hash,
                )

            self.view.showStatusMessage(f"报告保存成功：{outputPath.name}")
            logger.info("报告已保存：%s", outputPath)
        except Exception as error:  # pragma: no cover - GUI 场景下保底异常提示
            logger.error("报告保存失败：%s", error, exc_info=True)
            self.view.showStatusMessage(
                f"报告保存失败：{error}",
                durationMs=3200,
                isWarning=True,
            )

    def _refreshFrame(self) -> None:
        """
        采集并刷新一帧数据。

        处理流程：
        1. 从 Model 获取实时波形；
        2. 在 Gate A（Start/Width/Level）内执行峰值捕捉；
        3. 使用 Gate Level 作为触发阈值；
        4. 将结果更新到 View，并在超阈时红点标记。
        """
        if self.freezeEnabled and self.lastFrameData is not None:
            self._renderCurrentFrame(self.lastFrameData)
            return

        frameData = self.model.generateFrame()
        frameData["baseRawSignal"] = frameData["rawSignal"].copy()
        frameData["baseEnvelopeSignal"] = frameData["envelopeSignal"].copy()
        frameData["filterBaseRawSignal"] = frameData["rawSignal"].copy()
        frameData["filterBaseEnvelopeSignal"] = frameData["envelopeSignal"].copy()
        frameData["filterSettings"] = None
        frameData["tcgSignal"] = frameData["rawSignal"].copy()

        # 应用信号平均（如果启用）
        if self.signalAverageEnabled:
            averaged_signal = self._applySignalAverage(frameData["rawSignal"])
            frameData["baseRawSignal"] = averaged_signal.copy()
            frameData["rawSignal"] = averaged_signal
            frameData["envelopeSignal"] = self.model.compute_enhanced_envelope(averaged_signal)
            frameData["baseEnvelopeSignal"] = frameData["envelopeSignal"].copy()
            frameData["filterBaseRawSignal"] = averaged_signal.copy()
            frameData["filterBaseEnvelopeSignal"] = frameData["envelopeSignal"].copy()
            frameData["tcgSignal"] = averaged_signal.copy()

        if self.tcgEnabled:
            compensated = self.tcgProfile.apply(
                frameData["filterBaseRawSignal"],
                frameData["timeAxisUs"],
                self.model.parameters["soundVelocityMps"],
            ).astype(np.float32)
            frameData["tcgSignal"] = compensated
            frameData["rawSignal"] = compensated
            frameData["envelopeSignal"] = self.model.compute_enhanced_envelope(compensated)
            frameData["filterBaseEnvelopeSignal"] = frameData["envelopeSignal"].copy()
        self.view.prepareGateForTimeAxis(frameData["timeAxisUs"])
        gatePeakResult = self._captureGatePeak(
            timeAxisUs=frameData["timeAxisUs"],
            amplitudeArray=frameData["envelopeSignal"],
        )
        gateTriggered = bool(gatePeakResult["triggered"])

        # 触发模式：仅在闸门触发后更新显示，模拟硬件触发行为。
        if self.triggerMode == "gate" and (not gateTriggered) and self.lastFrameData is not None:
            self._renderCurrentFrame(self.lastFrameData)
            return

        self.lastFrameData = frameData
        self._record_frame(frameData)
        self._renderCurrentFrame(frameData, gatePeakResult=gatePeakResult)

    def _renderCurrentFrame(
        self,
        frameData: dict[str, Any],
        gatePeakResult: dict[str, float | bool | None] | None = None,
    ) -> None:
        """将当前帧数据渲染到界面并更新定量信息。"""
        if gatePeakResult is None:
            gatePeakResult = self._captureGatePeak(
                timeAxisUs=frameData["timeAxisUs"],
                amplitudeArray=frameData["envelopeSignal"],
            )

        gateXMinUs, gateXMaxUs, _, _ = self.view.getGateConfig()
        gateThresholdAmplitude = float(gatePeakResult["thresholdAmplitude"])
        peakTimeUs = gatePeakResult["peakTimeUs"]
        peakAmplitude = float(gatePeakResult["peakAmplitude"])
        gateTriggered = bool(gatePeakResult["triggered"])
        self._updateAdvancedAnalysis(frameData, peakAmplitude)

        if self.peakHoldEnabled:
            if self.peakHoldEnvelope is None or self.peakHoldEnvelope.size != frameData["envelopeSignal"].size:
                self.peakHoldEnvelope = frameData["envelopeSignal"].copy()
            else:
                self.peakHoldEnvelope = np.maximum(self.peakHoldEnvelope, frameData["envelopeSignal"])
        else:
            self.peakHoldEnvelope = None

        peakPercent = peakAmplitude * 100.0
        depthMm = self._timeUsToDepthMm(peakTimeUs) if peakTimeUs is not None else None
        horizontalDistanceMm = depthMm * self.kFactor if depthMm is not None else None
        dbDifference = self._calculateDbDifference(peakAmplitude, self.referenceScreenHeight)

        self.lastQuantitativeData = {
            "depthMm": depthMm,
            "horizontalDistanceMm": horizontalDistanceMm,
            "dbDifference": dbDifference,
            "peakPercent": peakPercent,
            "gateTriggered": gateTriggered,
            "peakAmplitude": peakAmplitude,
        }

        referenceEnvelope = None
        if (
            self.referenceEnvelope is not None
            and self.referenceTimeAxisUs is not None
            and self.referenceTimeAxisUs.size == frameData["timeAxisUs"].size
        ):
            referenceEnvelope = self.referenceEnvelope

        self.view.updateAScanPlot(
            timeAxisUs=frameData["timeAxisUs"],
            rawSignal=frameData["rawSignal"],
            envelopeSignal=frameData["envelopeSignal"],
            thresholdLevel=gateThresholdAmplitude,
            gateRangeUs=(gateXMinUs, gateXMaxUs),
            peakTimeUs=0.0 if peakTimeUs is None else float(peakTimeUs),
            peakAmplitude=peakAmplitude,
            defectDetected=gateTriggered,
            referenceEnvelope=referenceEnvelope,
            peakHoldEnvelope=self.peakHoldEnvelope,
        )
        self.view.updateBScanImage(frameData["bScanMatrix"])
        self.view.updateQuantitativePanel(
            depthMm=depthMm,
            horizontalDistanceMm=horizontalDistanceMm,
            dbDifference=dbDifference,
            peakPercent=peakPercent,
            kValue=self.kFactor,
        )

        defectDistanceMm = depthMm
        self.view.updateStatusPanel(
            frameCounter=frameData["frameCounter"],
            peakAmplitude=peakAmplitude,
            defectDistanceMm=defectDistanceMm,
            confidence=self._calculateGateConfidence(peakAmplitude, gateThresholdAmplitude),
            pointCount=self.model.pointCount,
            defectDetected=gateTriggered,
            allowLogging=self.recordingEnabled,
        )

        if gateTriggered and not self.lastDefectState:
            self.view.showStatusMessage(
                f"闸门捕捉到超阈值波峰：{peakAmplitude:.3f}",
                2600,
            )
        self.lastDefectState = gateTriggered

        overRange = peakAmplitude > self.highAmplitudeScreenHeight
        if overRange and not self.lastOverRangeState:
            self.view.showStatusMessage(
                "缺陷波幅过高！",
                durationMs=2400,
                isWarning=True,
            )
        self.lastOverRangeState = overRange

    def _captureGatePeak(self, timeAxisUs: np.ndarray, amplitudeArray: np.ndarray) -> dict[str, float | bool | None]:
        """
        智能捕捉算法：计算 Gate A（Start / Width / Level）内的最大波峰。

        规则说明：
        - Start/End 限定检测时间窗；
        - Level 为门限线（屏高）；
        - 在时间窗内优先搜索“超过门限”的最大峰；
        - 若无超限峰，返回时间窗内最大峰（triggered=False）。
        """
        gateStartUs, gateEndUs, _, thresholdAmplitude = self.view.getGateConfig()
        thresholdAmplitude = float(np.clip(thresholdAmplitude, 0.0, 1.5))
        if gateEndUs < gateStartUs:
            gateStartUs, gateEndUs = gateEndUs, gateStartUs

        if timeAxisUs.size == 0 or amplitudeArray.size == 0:
            return {
                "peakTimeUs": None,
                "peakAmplitude": 0.0,
                "thresholdAmplitude": float(thresholdAmplitude),
                "triggered": False,
            }

        timeWindowMask = (timeAxisUs >= gateStartUs) & (timeAxisUs <= gateEndUs)
        if not np.any(timeWindowMask):
            gateCenterUs = (gateStartUs + gateEndUs) * 0.5
            nearestIndex = int(np.argmin(np.abs(timeAxisUs - gateCenterUs)))
            peakAmplitude = float(amplitudeArray[nearestIndex])
            peakTimeUs = float(timeAxisUs[nearestIndex])
            return {
                "peakTimeUs": peakTimeUs,
                "peakAmplitude": peakAmplitude,
                "thresholdAmplitude": float(thresholdAmplitude),
                "triggered": False,
            }

        windowIndices = np.flatnonzero(timeWindowMask)
        windowAmplitudes = amplitudeArray[windowIndices]

        overThresholdMask = windowAmplitudes >= thresholdAmplitude
        if np.any(overThresholdMask):
            candidateIndices = windowIndices[np.flatnonzero(overThresholdMask)]
            candidateAmplitudes = amplitudeArray[candidateIndices]
            peakLocalOffset = int(np.argmax(candidateAmplitudes))
            peakIndex = int(candidateIndices[peakLocalOffset])
            isTriggered = True
        else:
            peakLocalOffset = int(np.argmax(windowAmplitudes))
            peakIndex = int(windowIndices[peakLocalOffset])
            isTriggered = False

        peakAmplitude = float(amplitudeArray[peakIndex])
        peakTimeUs = float(timeAxisUs[peakIndex])

        return {
            "peakTimeUs": peakTimeUs,
            "peakAmplitude": peakAmplitude,
            "thresholdAmplitude": float(thresholdAmplitude),
            "triggered": bool(isTriggered),
        }

    def _ensureLatestFrameAvailable(self) -> bool:
        """确保缓存中存在当前帧数据。"""
        if self.lastFrameData is not None:
            return True
        self._refreshFrame()
        return self.lastFrameData is not None

    def _saveWaveformAsJson(self, outputPath: Path) -> None:
        """将当前波形和参数保存为 JSON。"""
        assert self.lastFrameData is not None
        waveformPayload = {
            "savedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parameters": self.model.getParameters(),
            "waveform": {
                "timeUs": self.lastFrameData["timeAxisUs"].astype(float).tolist(),
                "rawSignal": self.lastFrameData["rawSignal"].astype(float).tolist(),
                "envelopeSignal": self.lastFrameData["envelopeSignal"].astype(float).tolist(),
            },
        }
        outputPath.write_text(
            json.dumps(waveformPayload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _loadWaveformFromJson(self, inputPath: Path) -> tuple[dict[str, float], np.ndarray, np.ndarray, np.ndarray]:
        """从 JSON 文件读取波形与参数。"""
        payload = json.loads(inputPath.read_text(encoding="utf-8"))
        waveformSection = payload.get("waveform", {})
        if not isinstance(waveformSection, dict):
            raise ValueError("JSON 格式无效：缺少 waveform 段。")

        parametersRaw = payload.get("parameters", {})
        parameters: dict[str, float] = {}
        if isinstance(parametersRaw, dict):
            for key, value in parametersRaw.items():
                try:
                    parameters[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue

        timeAxisUs = np.asarray(waveformSection.get("timeUs", []), dtype=np.float32)
        rawSignal = np.asarray(waveformSection.get("rawSignal", []), dtype=np.float32)
        envelopeSignal = np.asarray(waveformSection.get("envelopeSignal", []), dtype=np.float32)
        return parameters, timeAxisUs, rawSignal, envelopeSignal

    def _saveWaveformAsCsv(self, outputPath: Path) -> None:
        """将当前波形和参数保存为 CSV。"""
        assert self.lastFrameData is not None

        parameters = self.model.getParameters()
        timeArrayUs = self.lastFrameData["timeAxisUs"].astype(float)
        rawSignal = self.lastFrameData["rawSignal"].astype(float)
        envelopeSignal = self.lastFrameData["envelopeSignal"].astype(float)

        with outputPath.open("w", encoding="utf-8", newline="") as csvFile:
            csvWriter = csv.writer(csvFile)

            # 参数区：以 #PARAM 开头，方便后处理脚本识别。
            csvWriter.writerow(["#savedAt", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            for parameterName, parameterValue in parameters.items():
                csvWriter.writerow(["#PARAM", parameterName, parameterValue])

            csvWriter.writerow([])
            csvWriter.writerow(["time_us", "raw_signal", "envelope_signal"])
            for timeUs, rawValue, envelopeValue in zip(timeArrayUs, rawSignal, envelopeSignal):
                csvWriter.writerow([f"{timeUs:.6f}", f"{rawValue:.6f}", f"{envelopeValue:.6f}"])

    def _loadWaveformFromCsv(self, inputPath: Path) -> tuple[dict[str, float], np.ndarray, np.ndarray, np.ndarray]:
        """从 CSV 文件读取波形与参数。"""
        parameters: dict[str, float] = {}
        timeValues: list[float] = []
        rawValues: list[float] = []
        envelopeValues: list[float] = []
        dataSectionStarted = False

        with inputPath.open("r", encoding="utf-8", newline="") as csvFile:
            csvReader = csv.reader(csvFile)
            for row in csvReader:
                if not row:
                    continue
                headValue = str(row[0]).strip()
                if not dataSectionStarted:
                    if headValue == "#PARAM" and len(row) >= 3:
                        try:
                            parameters[str(row[1]).strip()] = float(row[2])
                        except (TypeError, ValueError):
                            continue
                        continue
                    if headValue.lower() == "time_us":
                        dataSectionStarted = True
                        continue
                    continue

                if len(row) < 3:
                    continue
                try:
                    timeValues.append(float(row[0]))
                    rawValues.append(float(row[1]))
                    envelopeValues.append(float(row[2]))
                except (TypeError, ValueError):
                    continue

        timeAxisUs = np.asarray(timeValues, dtype=np.float32)
        rawSignal = np.asarray(rawValues, dtype=np.float32)
        envelopeSignal = np.asarray(envelopeValues, dtype=np.float32)
        return parameters, timeAxisUs, rawSignal, envelopeSignal

    def _buildReportHtmlTemplate(
        self,
        detectionTimeText: str,
        workpieceName: str,
        defectDepthMm: float | None,
        decisionResult: str,
        overviewImageDataUri: str,
        defectRecords: list[dict[str, Any]],
    ) -> str:
        """
        构建检测报告 HTML 模板字符串。

        模板字段：
        - 检测时间
        - 工件名称
        - 缺陷深度
        - 判定结果（合格/不合格）
        """
        depthText = "--" if defectDepthMm is None else f"{defectDepthMm:.2f} mm"
        resultColor = "#2e8b57" if decisionResult == "合格" else "#d64045"
        safeWorkpieceName = html.escape(workpieceName)
        safeOverviewImage = overviewImageDataUri if overviewImageDataUri else ""

        if defectRecords:
            defectCards: list[str] = []
            for index, defectRecord in enumerate(defectRecords, start=1):
                detectedAtText = html.escape(str(defectRecord.get("detectedAt", "--")))
                depthValue = float(defectRecord.get("depthMm", 0.0))
                amplitudeValue = float(defectRecord.get("amplitude", 0.0))
                peakPercentValue = float(defectRecord.get("peakPercent", 0.0))
                imageDataUri = str(defectRecord.get("imageDataUri", "")) or safeOverviewImage
                defectCards.append(
                    f"""
    <div class="defect-card">
      <div><strong>缺陷 #{index}</strong></div>
      <div>检测时刻：{detectedAtText}</div>
      <div>深度：{depthValue:.2f} mm</div>
      <div>波幅：{amplitudeValue:.3f}（{peakPercentValue:.1f}%）</div>
      <img src="{imageDataUri}" alt="缺陷截图 {index}" />
    </div>
"""
                )
            defectSectionHtml = "".join(defectCards)
        else:
            defectSectionHtml = """
    <div class="empty-card">
      当前未记录到缺陷截图。
    </div>
"""

        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>超声检测报告</title>
  <style>
    body {{ font-family: 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', Arial, sans-serif; margin: 24px; color: #1a1f24; background: #ffffff; }}
    h1 {{ margin: 0 0 14px 0; font-size: 24px; }}
    .meta {{ margin-bottom: 18px; line-height: 1.9; font-size: 14px; }}
    .result {{ color: {resultColor}; font-weight: 700; }}
    .wave {{ margin-top: 14px; border: 1px solid #d6dee8; padding: 10px; border-radius: 6px; }}
    .wave img {{ width: 100%; max-width: 900px; border: 1px solid #bec9d6; }}
    .defect-list {{ margin-top: 18px; }}
    .defect-card {{ border: 1px solid #d9e3ee; border-radius: 8px; padding: 10px; margin-bottom: 12px; background: #fbfdff; line-height: 1.8; }}
    .defect-card img {{ width: 100%; max-width: 860px; border: 1px solid #bec9d6; margin-top: 8px; }}
    .empty-card {{ border: 1px dashed #bfd0e0; border-radius: 8px; padding: 12px; color: #4f6275; background: #f7fbff; }}
  </style>
</head>
<body>
  <h1>超声波智能辅助检测报告</h1>
  <div class="meta">
    <div><strong>检测时间：</strong>{detectionTimeText}</div>
    <div><strong>工件名称：</strong>{safeWorkpieceName}</div>
    <div><strong>缺陷数量：</strong>{len(defectRecords)}</div>
    <div><strong>缺陷深度：</strong>{depthText}</div>
    <div><strong>判定结果：</strong><span class="result">{decisionResult}</span></div>
  </div>
  <div class="wave">
    <div><strong>当前总览波形</strong></div>
    <img src="{safeOverviewImage}" alt="波形截图" />
  </div>
  <div class="defect-list">
    <h2>缺陷记录截图</h2>
{defectSectionHtml}
  </div>
</body>
</html>
"""

    @staticmethod
    def _injectReportImageSource(htmlTemplate: str, imageSource: str) -> str:
        """将报告模板中的截图占位符替换为实际图片路径。"""
        safeSource = imageSource if imageSource else ""
        return htmlTemplate.replace("__WAVEFORM_IMAGE_SRC__", safeSource)

    @staticmethod
    def _pixmapToDataUri(pixmap: QPixmap) -> str:
        """将 QPixmap 编码为可内嵌在 HTML 中的 base64 Data URI。"""
        if pixmap.isNull():
            return ""

        byteArray = QByteArray()
        buffer = QBuffer(byteArray)
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        encodedData = bytes(byteArray.toBase64()).decode("ascii")
        return f"data:image/png;base64,{encodedData}"

    def _timeUsToDepthMm(self, timeUs: float) -> float:
        """将传播时间（us）换算为声程深度（mm）。委托给统一换算模块。"""
        return time_us_to_depth_mm(
            timeUs,
            self.model.parameters["soundVelocityMps"],
            self.model.parameters.get("probeDelayUs", 0.0),
        )

    @staticmethod
    def _calculateDbDifference(peakAmplitude: float, referenceAmplitude: float) -> float | None:
        """
        计算波峰相对基准波高的 dB 差值。

        公式：
        - dB = 20 * log10(peak / reference)
        """
        if peakAmplitude <= 1e-9 or referenceAmplitude <= 1e-9:
            return None
        return float(20.0 * np.log10(peakAmplitude / referenceAmplitude))

    @staticmethod
    def _calculateGateConfidence(peakAmplitude: float, thresholdAmplitude: float) -> float:
        """
        计算闸门触发置信度（0~1）。

        设计思路：
        - 未达到阈值时返回较低值；
        - 超过阈值越多，置信度越高并趋近 1。
        """
        if thresholdAmplitude <= 1e-6:
            return 1.0 if peakAmplitude > 0.0 else 0.0

        if peakAmplitude <= thresholdAmplitude:
            return float(np.clip(0.5 * (peakAmplitude / thresholdAmplitude), 0.0, 0.5))

        exceedRatio = (peakAmplitude - thresholdAmplitude) / max(1.2 - thresholdAmplitude, 1e-6)
        return float(np.clip(0.5 + 0.5 * exceedRatio, 0.0, 1.0))

    def _ensureActiveSession(self) -> bool:
        """Create a detection session when one is not active."""
        if self.activeSessionId:
            return False
        self.activeSessionId = self.sessionRepository.start_session(
            parameters=self.model.getParameters(),
            workpiece=self.reportConfig.workpiece_name,
            standard_key=self.reportConfig.standard_key,
        )
        self.lastSessionId = self.activeSessionId
        return True

    def _finishActiveSession(self) -> None:
        """Flush and close the current detection session."""
        if not self.activeSessionId:
            return
        session_id = self.activeSessionId
        self.frameChunkStore.flush_session(session_id)
        decision = "不合格" if self.loggedDefectSnapshots else "合格"
        self.sessionRepository.finish_session(session_id, decision=decision)
        self.lastSessionId = session_id
        self.activeSessionId = None
        self.refreshReplaySessions()

    def _record_frame(self, frame_data: dict[str, Any]) -> None:
        """Persist the accepted frame into the active session."""
        if not self.activeSessionId:
            return
        self.frameChunkStore.append_frame(
            session_id=self.activeSessionId,
            sequence_id=int(frame_data.get("frameCounter", 0)),
            time_axis_us=frame_data["timeAxisUs"],
            raw_signal=frame_data.get("baseRawSignal", frame_data["rawSignal"]),
            envelope_signal=frame_data.get(
                "baseEnvelopeSignal",
                frame_data["envelopeSignal"],
            ),
            metadata={
                "sample_rate_hz": float(self.model.parameters["samplingRateHz"]),
                "filter_settings": frame_data.get("filterSettings"),
            },
        )

    def refreshReplaySessions(self) -> None:
        """Refresh the replay panel session list."""
        try:
            self.view.replayPanel.set_sessions(self.sessionRepository.list_sessions())
        except Exception as error:
            logger.error("刷新回放会话失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"刷新回放会话失败：{error}", isWarning=True)

    def loadReplaySession(self, session_id: str) -> None:
        """Load all frame indexes for a saved session."""
        try:
            if self.acquisitionTimer.isActive():
                self.stopAcquisition()
            self.replaySessionId = session_id
            self.replayFrames = list(
                self.sessionRepository.iter_frames(session_id, self.frameChunkStore)
            )
            self.view.replayPanel.set_frame_count(len(self.replayFrames))
            if self.replayFrames:
                self.loadReplayFrame(0)
            self.view.showStatusMessage(
                f"已加载回放会话，共 {len(self.replayFrames)} 帧。",
                1800,
            )
        except Exception as error:
            self.replayFrames = []
            logger.error("加载回放会话失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"加载回放失败：{error}", isWarning=True)

    def loadReplayFrame(self, frame_index: int) -> None:
        """Render one frame from the selected replay session."""
        if frame_index < 0 or frame_index >= len(self.replayFrames):
            return
        stored = self.replayFrames[frame_index]
        time_axis_us = np.asarray(stored["time_axis_us"], dtype=np.float32)
        raw_signal = np.asarray(stored["raw_signal"], dtype=np.float32)
        envelope_signal = np.asarray(stored["envelope_signal"], dtype=np.float32)
        frame_data = {
            "timeAxisUs": time_axis_us,
            "rawSignal": raw_signal.copy(),
            "envelopeSignal": envelope_signal.copy(),
            "baseRawSignal": raw_signal.copy(),
            "baseEnvelopeSignal": envelope_signal.copy(),
            "filterBaseRawSignal": raw_signal.copy(),
            "filterBaseEnvelopeSignal": envelope_signal.copy(),
            "tcgSignal": raw_signal.copy(),
            "filterSettings": None,
            "thresholdLevel": float(self.model.parameters["thresholdLevel"]),
            "gateRangeUs": (
                float(self.model._depthMmToTimeSec(self.model.parameters["gateStartMm"]) * 1e6),
                float(self.model._depthMmToTimeSec(self.model.parameters["gateEndMm"]) * 1e6),
            ),
            "peakAmplitude": 0.0,
            "peakTimeUs": 0.0,
            "defectDetected": False,
            "defectDistanceMm": None,
            "confidence": 0.0,
            "frameCounter": int(stored["sequence_id"]),
            "bScanMatrix": self.model.bScanMatrix.copy(),
        }
        self.lastFrameData = frame_data
        self.view.prepareGateForTimeAxis(time_axis_us)
        self._renderCurrentFrame(frame_data)

    def shutdown(self) -> None:
        """Finish active persistence state when the application closes."""
        self._finishActiveSession()
        self.sessionRepository.close()

    def updateAdvancedGate(self, gate_data: dict[str, Any]) -> None:
        """Update Gate B/C configuration from the advanced panel."""
        gate_id = str(gate_data.get("gate_id", "")).upper()
        if gate_id not in {"B", "C"}:
            return
        self.advancedGates[gate_id] = GateConfig(
            gate_id=gate_id,
            name=str(gate_data.get("name", f"闸门{gate_id}")),
            start_mm=float(gate_data.get("start_mm", 0.0)),
            width_mm=max(float(gate_data.get("width_mm", 0.0)), 0.01),
            level=float(gate_data.get("level", 0.5)),
            enabled=bool(gate_data.get("enabled", False)),
        )

    def updateTcgProfile(self, tcg_data: dict[str, Any]) -> None:
        """Replace the active TCG profile from the advanced panel."""
        points = [
            TcgPoint(
                depth_mm=float(point["depth_mm"]),
                gain_db=float(point["gain_db"]),
            )
            for point in tcg_data.get("points", [])
        ]
        self.tcgProfile = TcgProfile(points or [TcgPoint(0.0, 0.0)])
        self.tcgEnabled = bool(tcg_data.get("enabled", False))
        self.view.showStatusMessage(
            "TCG已启用。" if self.tcgEnabled else "TCG已关闭。",
            1400,
        )

    def _updateAdvancedAnalysis(
        self,
        frame_data: dict[str, Any],
        peak_amplitude: float,
    ) -> None:
        """Evaluate all gates and update B/C-scan imagery."""
        try:
            start_us, end_us, _, level = self.view.getGateConfig()
            start_depth_mm = self.model._timeSecToDepthMm(start_us * 1e-6)
            end_depth_mm = self.model._timeSecToDepthMm(end_us * 1e-6)
            self.advancedGates["A"] = GateConfig(
                gate_id="A",
                name="闸门A",
                start_mm=start_depth_mm,
                width_mm=max(end_depth_mm - start_depth_mm, 0.01),
                level=level,
                enabled=True,
            )
            results = GateAnalyzer.analyze(
                frame_data["timeAxisUs"],
                frame_data["envelopeSignal"],
                list(self.advancedGates.values()),
                lambda depth_mm: self.model._depthMmToTimeSec(depth_mm) * 1e6,
            )
            for gate_id, result in results.items():
                row = self.view.advancedUTPanel.gate_rows.get(gate_id)
                if row is not None:
                    row.set_result(result.triggered, result.peak_amplitude)

            self.view.scanPanel.update_b_scan(frame_data.get("bScanMatrix", np.zeros((1, 1))))
            scan_index = int(frame_data.get("frameCounter", 0)) % (
                self.scanGrid.rows * self.scanGrid.columns
            )
            self.cScanValues[scan_index] = max(
                self.cScanValues.get(scan_index, 0.0),
                float(peak_amplitude),
            )
            self.view.scanPanel.update_c_scan(
                self.scanGrid.build_c_scan(self.cScanValues.items())
            )
        except Exception as error:
            logger.warning("高级UT分析更新失败：%s", error)

    def computeFFT(self, settings: dict) -> None:
        """
        计算FFT频谱分析。

        参数：
        - settings: FFT分析设置，包含fft_size和window_type
        """
        if self.lastFrameData is None:
            self.view.showStatusMessage("当前无可用波形数据，无法进行FFT分析。", isWarning=True)
            return

        try:
            # 获取当前波形数据
            raw_signal = self.lastFrameData["rawSignal"]
            time_axis_us = self.lastFrameData["timeAxisUs"]

            # 计算FFT
            fft_size = settings.get("fft_size", 1024)
            window_type = settings.get("window_type", "汉宁窗")
            frequencies, magnitude = self.model.compute_fft(
                raw_signal,
                n_fft=fft_size,
                window=window_type,
            )

            # 找到峰值频率
            peak_index = np.argmax(magnitude)
            peak_freq = frequencies[peak_index]
            peak_magnitude = magnitude[peak_index]

            # 更新FFT面板显示
            self.view.fftPanel.update_fft_display(frequencies, magnitude, peak_freq, peak_magnitude)

            self.view.showStatusMessage(f"FFT分析完成，峰值频率: {peak_freq/1e6:.2f} MHz")
            logger.info("FFT分析完成，峰值频率: %f Hz", peak_freq)

        except Exception as error:
            logger.error("FFT分析失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"FFT分析失败：{error}", durationMs=3500, isWarning=True)

    def applyFilter(self, filter_settings: dict) -> None:
        """
        应用数字滤波器。

        参数：
        - filter_settings: 滤波器设置，包含滤波器类型、频率范围等
        """
        if self.lastFrameData is None:
            self.view.showStatusMessage("当前无可用波形数据，无法应用滤波器。", isWarning=True)
            return

        try:
            # 始终从未经滤波的基础波形计算，避免重复滤波叠加。
            raw_signal = self.lastFrameData.get(
                "filterBaseRawSignal",
                self.lastFrameData["rawSignal"],
            )

            # 应用滤波器
            filter_type = filter_settings.get('filter_type', '带通')
            low_freq_hz = filter_settings.get('low_freq_hz', 0.1e6)
            high_freq_hz = filter_settings.get('high_freq_hz', 10e6)
            order = filter_settings.get('order', 4)

            filtered_signal = self.model.apply_filter(
                raw_signal,
                filter_type,
                low_freq_hz if filter_type in {"带通", "高通"} else None,
                high_freq_hz if filter_type in {"带通", "低通"} else None,
                order,
            )

            # 更新波形显示
            self.lastFrameData["rawSignal"] = filtered_signal
            self.lastFrameData["envelopeSignal"] = self.model.compute_enhanced_envelope(filtered_signal)
            self.lastFrameData["filterSettings"] = filter_settings
            self._renderCurrentFrame(self.lastFrameData)

            self.view.showStatusMessage(f"{filter_type}滤波器应用完成")
            logger.info("%s滤波器应用完成", filter_type)

        except Exception as error:
            logger.error("滤波器应用失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"滤波器应用失败：{error}", durationMs=3500, isWarning=True)

    def resetFilter(self) -> None:
        """恢复最近一帧的未滤波波形。"""
        if self.lastFrameData is None:
            self.view.showStatusMessage("当前无可用波形数据。", isWarning=True)
            return
        raw_signal = self.lastFrameData.get("filterBaseRawSignal")
        envelope_signal = self.lastFrameData.get("filterBaseEnvelopeSignal")
        if raw_signal is None or envelope_signal is None:
            self.view.showStatusMessage("当前没有可复位的滤波结果。")
            return
        self.lastFrameData["rawSignal"] = raw_signal.copy()
        self.lastFrameData["envelopeSignal"] = envelope_signal.copy()
        self.lastFrameData["filterSettings"] = None
        self._renderCurrentFrame(self.lastFrameData)
        self.view.showStatusMessage("滤波器已复位。")

    def showSignalFeatures(self) -> None:
        """提取当前波形特征并通过对话框展示。"""
        features = self.extractCurrentSignalFeatures()
        if features is None:
            self.view.showStatusMessage("当前无可用波形数据，无法提取特征。", isWarning=True)
            return
        rows = [
            ("均值", f"{features['mean']:.6g}"),
            ("标准差", f"{features['std']:.6g}"),
            ("RMS", f"{features['rms']:.6g}"),
            ("峰峰值", f"{features['peak_to_peak']:.6g}"),
            ("过零率", f"{features['zero_crossing_rate']:.6f}"),
            ("能量", f"{features['energy']:.6g}"),
            ("峰值时间", f"{features['peak_time_us']:.3f} us"),
            ("峰值幅值", f"{features['peak_amplitude']:.6g}"),
        ]
        text = "\n".join(f"{label}: {value}" for label, value in rows)
        QMessageBox.information(self.view, "信号特征", text)

    def compareWithReference(self) -> None:
        """将当前波形与已捕获参考波形进行对比。"""
        if self.lastFrameData is None:
            self.view.showStatusMessage("当前无可用波形数据。", isWarning=True)
            return
        if self.referenceRawSignal is None:
            self.view.showStatusMessage("请先捕获参考波形，再执行对比。", isWarning=True)
            return
        current = self.lastFrameData.get("baseRawSignal", self.lastFrameData["rawSignal"])
        result = self.compareSignals(self.referenceRawSignal, current)
        if result is None:
            return
        text = (
            f"平均差异: {result['mean_difference']:.6g}\n"
            f"最大差异: {result['max_difference']:.6g}\n"
            f"RMS差异: {result['rms_difference']:.6g}\n"
            f"相关系数: {result['correlation']:.6f}\n"
            f"最大差异位置: {result['max_diff_time_us']:.3f} us"
        )
        QMessageBox.information(self.view, "波形对比", text)

    def getDefectStatistics(self) -> dict[str, Any]:
        """
        获取缺陷统计信息。

        返回：
        - 统计信息字典
        """
        # 同步缺陷记录到分析器
        self.defectAnalyzer.clear_records()
        for snap in self.loggedDefectSnapshots:
            record = DefectRecord(
                uid=snap.get("recordUid", 0),
                depth_mm=snap.get("depthMm", 0.0),
                amplitude=snap.get("amplitude", 0.0),
                timestamp=snap.get("timestamp", ""),
            )
            self.defectAnalyzer.add_record(record)

        stats = self.defectAnalyzer.get_statistics()
        return {
            "total_count": stats.total_count,
            "depth_min_mm": stats.depth_min_mm,
            "depth_max_mm": stats.depth_max_mm,
            "depth_mean_mm": stats.depth_mean_mm,
            "depth_std_mm": stats.depth_std_mm,
            "amplitude_mean": stats.amplitude_mean,
            "amplitude_std": stats.amplitude_std,
            "depth_distribution": stats.depth_distribution,
            "amplitude_distribution": stats.amplitude_distribution,
        }

    def setSignalAverage(self, enabled: bool, count: int = 8) -> None:
        """
        设置信号平均功能。

        参数：
        - enabled: 是否启用
        - count: 平均帧数
        """
        self.signalAverageEnabled = enabled
        self.signalAverageCount = max(2, min(64, count))
        self.signalAverageBuffer.clear()
        if enabled:
            self.view.showStatusMessage(f"信号平均已启用，平均 {self.signalAverageCount} 帧")
        else:
            self.view.showStatusMessage("信号平均已关闭")

    def _applySignalAverage(self, raw_signal: np.ndarray) -> np.ndarray:
        """
        对信号应用平均处理。

        参数：
        - raw_signal: 原始信号

        返回：
        - 平均后的信号
        """
        if not self.signalAverageEnabled:
            return raw_signal

        self.signalAverageBuffer.append(raw_signal.copy())

        # 保持缓冲区大小
        while len(self.signalAverageBuffer) > self.signalAverageCount:
            self.signalAverageBuffer.pop(0)

        if len(self.signalAverageBuffer) < 2:
            return raw_signal

        try:
            return self.model.compute_signal_average(self.signalAverageBuffer, method='mean')
        except Exception as error:
            logger.warning("信号平均失败：%s", error)
            return raw_signal

    def extractCurrentSignalFeatures(self) -> dict[str, Any] | None:
        """
        提取当前帧的信号特征。

        返回：
        - 特征字典，或None
        """
        if self.lastFrameData is None:
            return None

        try:
            features = self.model.extract_signal_features(
                self.lastFrameData["rawSignal"],
                self.lastFrameData["timeAxisUs"],
            )
            return features
        except Exception as error:
            logger.error("信号特征提取失败：%s", error)
            return None

    def refreshDefectStatistics(self) -> None:
        """刷新缺陷统计数据并更新统计面板。"""
        try:
            stats = self.getDefectStatistics()
            self.view.statisticsPanel.update_statistics(stats)

            # 更新DAC曲线
            if stats["total_count"] > 0:
                depths = np.array([r.depth_mm for r in self.defectAnalyzer.defect_records])
                amplitudes = np.array([r.amplitude for r in self.defectAnalyzer.defect_records])

                # 生成DAC曲线
                dac_depths, dac_amplitudes = self.defectAnalyzer.generate_dac_curve(
                    depth_range_mm=(0, max(depths.max() + 20, 150)),
                    reference_depth_mm=50.0,
                    reference_amplitude=1.0,
                )

                self.view.statisticsPanel.update_dac_curve(
                    dac_depths, dac_amplitudes,
                    defect_depths=depths.tolist(),
                    defect_amplitudes=amplitudes.tolist(),
                )
            else:
                # 没有缺陷记录时显示空DAC曲线
                dac_depths, dac_amplitudes = self.defectAnalyzer.generate_dac_curve()
                self.view.statisticsPanel.update_dac_curve(dac_depths, dac_amplitudes)

            self.view.showStatusMessage("缺陷统计数据已刷新")
        except Exception as error:
            logger.error("刷新缺陷统计失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"刷新缺陷统计失败：{error}", isWarning=True)

    def compareSignals(self, signal1: np.ndarray, signal2: np.ndarray) -> dict[str, Any] | None:
        """
        比较两个信号的差异。

        参数：
        - signal1: 第一个信号
        - signal2: 第二个信号

        返回：
        - 比较结果字典，或None
        """
        if self.lastFrameData is None:
            self.view.showStatusMessage("当前无可用波形数据，无法进行信号对比。", isWarning=True)
            return None

        try:
            result = self.model.compare_signals(
                signal1, signal2, self.lastFrameData["timeAxisUs"]
            )

            # 显示比较结果
            message = (
                f"信号对比结果：\n"
                f"平均差异: {result['mean_difference']:.4f}\n"
                f"最大差异: {result['max_difference']:.4f}\n"
                f"RMS差异: {result['rms_difference']:.4f}\n"
                f"相关系数: {result['correlation']:.4f}\n"
                f"最大差异位置: {result['max_diff_time_us']:.2f} μs"
            )
            self.view.showStatusMessage("信号对比完成")
            logger.info("信号对比完成: 相关系数=%.4f, 最大差异=%.4f",
                       result['correlation'], result['max_difference'])

            return result
        except Exception as error:
            logger.error("信号对比失败：%s", error, exc_info=True)
            self.view.showStatusMessage(f"信号对比失败：{error}", isWarning=True)
            return None
