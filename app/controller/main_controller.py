"""超声检测系统控制器（Controller）。"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtGui import QPixmap, QTextDocument
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtWidgets import QFileDialog, QInputDialog

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
        self.acquisitionTimer.setInterval(50)

        # 记录告警状态变化，用于提示“首次告警”事件。
        self.lastDefectState = False
        self.gateThresholdRatio = 0.80
        self.kFactor = 2.0
        self.referenceScreenHeight = 0.80
        self.highAmplitudeScreenHeight = 1.00
        self.lastOverRangeState = False

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

        self._bindSignals()
        self._initializeView()

    def _bindSignals(self) -> None:
        """绑定视图事件与控制器槽函数。"""
        self.view.startRequested.connect(self.startAcquisition)
        self.view.stopRequested.connect(self.stopAcquisition)
        self.view.singleShotRequested.connect(self.singleShotAcquisition)
        self.view.resetRequested.connect(self.resetSystem)
        self.view.parametersApplied.connect(self.applyParameters)

        # 功能列表 5：保存数据与报告生成。
        self.view.openRequested.connect(self.openDataFile)
        self.view.saveRequested.connect(self.saveWaveformData)
        self.view.reportRequested.connect(self.generateReport)

        self.acquisitionTimer.timeout.connect(self._refreshFrame)

    def _initializeView(self) -> None:
        """初始化界面显示并执行首次采样。"""
        self.view.loadParameters(self.model.getParameters())
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
            self.view.showStatusMessage("采集已经停止。")
            return
        self.acquisitionTimer.stop()
        self.view.showStatusMessage("实时采集已停止。")

    def singleShotAcquisition(self) -> None:
        """执行一次单帧采样。"""
        self._refreshFrame()
        self.view.showStatusMessage("单次采样完成。")

    def resetSystem(self) -> None:
        """重置系统状态。"""
        self.stopAcquisition()
        self.model.resetHistory()
        self.lastDefectState = False
        self.lastOverRangeState = False
        self._refreshFrame()
        self.view.showStatusMessage("系统已重置。")

    def applyParameters(self, parameters: dict[str, float]) -> None:
        """应用用户在界面中设置的参数。"""
        self.model.updateParameters(parameters)
        self.view.loadParameters(self.model.getParameters())
        self._refreshFrame()
        self.view.showStatusMessage("参数更新成功。")

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
        4. 在预览窗口内点击“保存报告”后导出 HTML/PDF。
        """
        if not self._ensureLatestFrameAvailable():
            return

        workpieceName, isConfirmed = QInputDialog.getText(
            self.view,
            "工件名称",
            "请输入工件名称：",
            text="工件-001",
        )
        if not isConfirmed:
            return
        workpieceName = workpieceName.strip() or "工件-001"

        waveformPixmap = self.view.aScanPlot.grab()
        defectDepthMm = self.lastQuantitativeData["depthMm"]
        decisionResult = "不合格" if self.lastQuantitativeData["gateTriggered"] else "合格"
        detectionTimeText = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.currentReportHtmlTemplate = self._buildReportHtmlTemplate(
            detectionTimeText=detectionTimeText,
            workpieceName=workpieceName,
            defectDepthMm=defectDepthMm,
            decisionResult=decisionResult,
        )
        self.currentReportPixmap = waveformPixmap

        # 弹出报告预览窗口。
        self.reportPreviewWindow = ReportPreviewWindow(
            waveformPixmap=waveformPixmap,
            reportHtml=self._injectReportImageSource(self.currentReportHtmlTemplate, ""),
            parent=self.view,
        )
        self.reportPreviewWindow.saveRequested.connect(self.saveCurrentReport)
        self.reportPreviewWindow.show()
        self.reportPreviewWindow.raise_()
        self.reportPreviewWindow.activateWindow()

    def saveCurrentReport(self) -> None:
        """将当前报告导出为 HTML 或 PDF。"""
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
        if outputPath.suffix.lower() not in {".html", ".pdf"}:
            outputPath = outputPath.with_suffix(".pdf" if "PDF" in selectedFilter else ".html")

        try:
            # 报告截图与报告文件同目录保存，便于归档追踪。
            screenshotPath = outputPath.with_name(f"{outputPath.stem}_waveform.png")
            self.currentReportPixmap.save(str(screenshotPath), "PNG")

            if outputPath.suffix.lower() == ".html":
                htmlContent = self._injectReportImageSource(self.currentReportHtmlTemplate, screenshotPath.name)
                outputPath.write_text(htmlContent, encoding="utf-8")
            else:
                htmlContent = self._injectReportImageSource(
                    self.currentReportHtmlTemplate,
                    screenshotPath.resolve().as_uri(),
                )
                self._saveHtmlAsPdf(htmlContent, outputPath)

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
        2. 在 Gate ROI 内执行峰值捕捉；
        3. 使用“闸门高度 80%”作为触发阈值；
        4. 将结果更新到 View，并在超阈时红点标记。
        """
        frameData = self.model.generateFrame()
        self.lastFrameData = frameData
        self.view.prepareGateForTimeAxis(frameData["timeAxisUs"])

        gatePeakResult = self._captureGatePeak(
            timeAxisUs=frameData["timeAxisUs"],
            amplitudeArray=frameData["envelopeSignal"],
        )
        gateXMinUs, gateXMaxUs, _, _ = self.view.getGateBounds()
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

        defectDistanceMm = depthMm if gateTriggered else None
        self.view.updateStatusPanel(
            frameCounter=frameData["frameCounter"],
            peakAmplitude=peakAmplitude,
            defectDistanceMm=defectDistanceMm,
            confidence=self._calculateGateConfidence(peakAmplitude, gateThresholdAmplitude),
            pointCount=self.model.pointCount,
            defectDetected=gateTriggered,
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
        智能捕捉算法：计算闸门区域内最大波峰。

        规则说明：
        - ROI 矩形给定时间范围和幅值范围；
        - 仅在矩形内搜索峰值；
        - 当峰值 >= 闸门高度 80% 时，判定为触发。
        """
        gateXMinUs, gateXMaxUs, gateYMin, gateYMax = self.view.getGateBounds()
        gateHeight = max(gateYMax - gateYMin, 1e-6)
        thresholdAmplitude = gateYMin + gateHeight * self.gateThresholdRatio

        if gateXMaxUs <= gateXMinUs:
            return {
                "peakTimeUs": None,
                "peakAmplitude": 0.0,
                "thresholdAmplitude": float(thresholdAmplitude),
                "triggered": False,
            }

        timeMask = (timeAxisUs >= gateXMinUs) & (timeAxisUs <= gateXMaxUs)
        amplitudeMask = (amplitudeArray >= gateYMin) & (amplitudeArray <= gateYMax)
        gateMask = timeMask & amplitudeMask
        if not np.any(gateMask):
            return {
                "peakTimeUs": None,
                "peakAmplitude": 0.0,
                "thresholdAmplitude": float(thresholdAmplitude),
                "triggered": False,
            }

        gateIndices = np.flatnonzero(gateMask)
        gateAmplitudes = amplitudeArray[gateIndices]
        peakLocalOffset = int(np.argmax(gateAmplitudes))
        peakIndex = int(gateIndices[peakLocalOffset])

        peakAmplitude = float(amplitudeArray[peakIndex])
        peakTimeUs = float(timeAxisUs[peakIndex])
        isTriggered = peakAmplitude >= thresholdAmplitude

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

        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>超声检测报告</title>
  <style>
    body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 24px; color: #1a1f24; }}
    h1 {{ margin: 0 0 14px 0; font-size: 24px; }}
    .meta {{ margin-bottom: 18px; line-height: 1.9; font-size: 14px; }}
    .result {{ color: {resultColor}; font-weight: 700; }}
    .wave {{ margin-top: 14px; border: 1px solid #d6dee8; padding: 10px; border-radius: 6px; }}
    .wave img {{ width: 100%; max-width: 900px; border: 1px solid #bec9d6; }}
  </style>
</head>
<body>
  <h1>超声波智能辅助检测报告</h1>
  <div class="meta">
    <div><strong>检测时间：</strong>{detectionTimeText}</div>
    <div><strong>工件名称：</strong>{workpieceName}</div>
    <div><strong>缺陷深度：</strong>{depthText}</div>
    <div><strong>判定结果：</strong><span class="result">{decisionResult}</span></div>
  </div>
  <div class="wave">
    <div><strong>当前波形截图</strong></div>
    <img src="{{WAVEFORM_IMAGE_SRC}}" alt="波形截图" />
  </div>
</body>
</html>
"""

    @staticmethod
    def _injectReportImageSource(htmlTemplate: str, imageSource: str) -> str:
        """将报告模板中的截图占位符替换为实际图片路径。"""
        safeSource = imageSource if imageSource else ""
        return htmlTemplate.replace("{WAVEFORM_IMAGE_SRC}", safeSource)

    @staticmethod
    def _saveHtmlAsPdf(htmlContent: str, outputPath: Path) -> None:
        """将 HTML 报告渲染并输出为 PDF。"""
        textDocument = QTextDocument()
        textDocument.setHtml(htmlContent)

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(outputPath))

        textDocument.print_(printer)

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
