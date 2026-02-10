"""超声检测系统控制器（Controller）。"""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog

from app.model.ultrasonic_model import UltrasonicSignalModel
from app.view.main_window import MainWindow
from app.view.report_preview_window import ReportPreviewWindow


class MainController(QObject):
    """
    主控制器。

    主要职责：
    1. 连接 View 的交互信号与 Model 的业务逻辑；
    2. 管理定时采样流程；
    3. 将 Model 计算结果更新到 View；
    4. 实现数据保存与检测报告导出流程。
    """

    def __init__(self, model: UltrasonicSignalModel, view: MainWindow) -> None:
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

        # 缓存最近一帧数据与定量结果，供导出与报告模块使用。
        self.lastFrameData: dict[str, Any] | None = None
        self.lastQuantitativeData: dict[str, Any] = {
            "depthMm": None,
            "horizontalDistanceMm": None,
            "dbDifference": None,
            "peakPercent": 0.0,
            "gateTriggered": False,
        }

        # 报告预览窗口与报告上下文缓存。
        self.reportPreviewWindow: ReportPreviewWindow | None = None
        self.currentReportHtmlTemplate = ""
        self.currentReportPixmap = QPixmap()
        self.currentReportImageDataUri = ""
        self.loggedDefectSnapshots: list[dict[str, Any]] = []

        self._bindSignals()
        self._initializeView()

    def _bindSignals(self) -> None:
        """绑定视图事件与控制器槽函数。"""
        self.view.startRequested.connect(self.startAcquisition)
        self.view.stopRequested.connect(self.stopAcquisition)
        self.view.singleShotRequested.connect(self.singleShotAcquisition)
        self.view.resetRequested.connect(self.resetSystem)
        self.view.recordStartRequested.connect(self.startRecording)
        self.view.recordStopRequested.connect(self.stopRecording)
        self.view.parametersApplied.connect(self.applyParameters)
        self.view.defectLogged.connect(self._onDefectLogged)
        self.view.defectRecordsDeleted.connect(self._onDefectRecordsDeleted)
        self.view.defectRecordsCleared.connect(self._onDefectRecordsCleared)

        # 功能列表 5：保存数据与报告生成。
        self.view.openRequested.connect(self.openDataFile)
        self.view.saveRequested.connect(self.saveWaveformData)
        self.view.reportRequested.connect(self.generateReport)

        self.acquisitionTimer.timeout.connect(self._refreshFrame)

    def _initializeView(self) -> None:
        """初始化界面显示并执行首次采样。"""
        self.view.loadParameters(self.model.getParameters())
        self.view.setAcquisitionIntervalMs(self.acquisitionTimer.interval())
        self.view.setRecordingState(False)
        self.view.showStatusMessage("参数初始化完成。")
        self._refreshFrame()

    def startAcquisition(self) -> None:
        """启动实时采集。"""
        if self.acquisitionTimer.isActive():
            self.view.showStatusMessage("采集已在运行。")
            return
        self.acquisitionTimer.start()
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
        self.view.showStatusMessage("实时采集已停止。")

    def singleShotAcquisition(self) -> None:
        """执行一次单帧采样。"""
        self._refreshFrame()
        self.view.showStatusMessage("单次采样完成。")

    def resetSystem(self) -> None:
        """重置系统状态。"""
        self.stopAcquisition()
        self.stopRecording(showMessage=False)
        self.model.resetHistory()
        self.view.clearDefectHistory()
        self.loggedDefectSnapshots.clear()
        self.lastDefectState = False
        self.lastOverRangeState = False
        self._refreshFrame()
        self.view.showStatusMessage("系统已重置。")

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

    def openDataFile(self) -> None:
        """打开历史文件（当前版本仅提供文件选择与提示）。"""
        filePath, _ = QFileDialog.getOpenFileName(
            self.view,
            "打开检测数据",
            "",
            "数据文件 (*.json *.csv)",
        )
        if not filePath:
            return
        self.view.showStatusMessage(f"已选择文件：{Path(filePath).name}")

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
        except Exception as error:  # pragma: no cover - GUI 场景下保底异常提示
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

            # 为避免阻塞式对话框造成“点击无反应”体验，先使用默认工件名。
            workpieceName = "工件-001"

            waveformPixmap = self.view.aScanPlot.grab()
            overviewImageDataUri = self._pixmapToDataUri(waveformPixmap)
            defectRecords = sorted(
                self.loggedDefectSnapshots,
                key=lambda item: int(item.get("recordUid", 0)),
            )
            hasDefect = bool(defectRecords) or bool(self.lastQuantitativeData["gateTriggered"])
            defectDepthMm = defectRecords[-1]["depthMm"] if defectRecords else self.lastQuantitativeData["depthMm"]
            decisionResult = "不合格" if hasDefect else "合格"
            detectionTimeText = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.currentReportHtmlTemplate = self._buildReportHtmlTemplate(
                detectionTimeText=detectionTimeText,
                workpieceName=workpieceName,
                defectDepthMm=defectDepthMm,
                decisionResult=decisionResult,
                overviewImageDataUri=overviewImageDataUri,
                defectRecords=defectRecords,
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
        except Exception as error:  # pragma: no cover - GUI 场景下保底异常提示
            self.view.showStatusMessage(f"生成报告失败：{error}", durationMs=3500, isWarning=True)

    def saveCurrentReport(self) -> None:
        """将当前报告导出为 HTML。"""
        if not self.currentReportHtmlTemplate:
            self.view.showStatusMessage("报告内容为空，无法保存。", isWarning=True)
            return

        defaultName = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filePath, _ = QFileDialog.getSaveFileName(
            self.view,
            "保存检测报告",
            defaultName,
            "HTML 文件 (*.html)",
        )
        if not filePath:
            return

        outputPath = Path(filePath)
        if outputPath.suffix.lower() != ".html":
            outputPath = outputPath.with_suffix(".html")

        try:
            outputPath.write_text(self.currentReportHtmlTemplate, encoding="utf-8")

            self.view.showStatusMessage(f"报告保存成功：{outputPath.name}")
        except Exception as error:  # pragma: no cover - GUI 场景下保底异常提示
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
        frameData = self.model.generateFrame()
        self.lastFrameData = frameData
        self.view.prepareGateForTimeAxis(frameData["timeAxisUs"])

        gatePeakResult = self._captureGatePeak(
            timeAxisUs=frameData["timeAxisUs"],
            amplitudeArray=frameData["envelopeSignal"],
        )
        gateXMinUs, gateXMaxUs, _, _ = self.view.getGateConfig()
        gateThresholdAmplitude = gatePeakResult["thresholdAmplitude"]
        peakTimeUs = gatePeakResult["peakTimeUs"]
        peakAmplitude = gatePeakResult["peakAmplitude"]
        gateTriggered = gatePeakResult["triggered"]

        # 功能列表 4：定量计算。
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

        self.view.updateAScanPlot(
            timeAxisUs=frameData["timeAxisUs"],
            rawSignal=frameData["rawSignal"],
            envelopeSignal=frameData["envelopeSignal"],
            thresholdLevel=gateThresholdAmplitude,
            gateRangeUs=(gateXMinUs, gateXMaxUs),
            peakTimeUs=0.0 if peakTimeUs is None else peakTimeUs,
            peakAmplitude=peakAmplitude,
            defectDetected=gateTriggered,
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

        # 仅在“正常 -> 告警”跃迁时提示，避免每帧重复弹状态。
        if gateTriggered and not self.lastDefectState:
            self.view.showStatusMessage(
                f"闸门捕捉到超阈值波峰：{peakAmplitude:.3f}",
                2600,
            )
        self.lastDefectState = gateTriggered

        # 自动报警：波峰超过 100% 屏高时，状态栏红色警告提示。
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
        thresholdAmplitude = float(np.clip(thresholdAmplitude, -0.2, 1.5))
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
        """将传播时间（us）换算为声程深度（mm）。"""
        soundVelocityMps = self.model.parameters["soundVelocityMps"]
        timeSec = timeUs * 1e-6
        depthMeter = (timeSec * soundVelocityMps) / 2.0
        return depthMeter * 1000.0

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
