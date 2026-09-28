"""Generate manual screenshots from the current Qt user interface."""

from __future__ import annotations

import tempfile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

from app.common.auth import AuthService, Role
from app.common.report_generator import ReportConfig, ReportGenerator
from app.common.theme import buildDarkIndustrialStyleSheet
from app.model.defect_analyzer import DefectAnalyzer, DefectRecord
from app.model.session_repository import FrameChunkStore, SessionRepository
from app.model.ultrasonic_model import UltrasonicSignalModel
from app.view.advanced_ut_panel import AdvancedUTPanel
from app.view.audit_dialog import AuditDialog
from app.view.login_dialog import LoginDialog
from app.view.main_window import MainWindow
from app.view.replay_panel import ReplayPanel
from app.view.report_config_dialog import ReportConfigDialog
from app.view.report_preview_window import ReportPreviewWindow
from app.view.scan_panel import ScanPanel
from app.view.statistics_panel import StatisticsPanel


IMAGE_DIR = PROJECT_ROOT / "Direction" / "image"


def capture(widget, filename: str) -> None:
    """Render and save a widget screenshot."""
    widget.show()
    for _ in range(4):
        QApplication.processEvents()
    widget.grab().save(str(IMAGE_DIR / filename))
    widget.hide()


def build_main_window() -> tuple[MainWindow, UltrasonicSignalModel]:
    """Create a populated main window without starting a persistent session."""
    model = UltrasonicSignalModel()
    model.updateParameters(
        {
            "gainDb": 22.0,
            "scanDepthMm": 120.0,
            "thresholdLevel": 0.55,
            "gateStartMm": 25.0,
            "gateEndMm": 95.0,
        }
    )
    window = MainWindow()
    window.resize(1600, 1000)

    frame = model.generateFrame()
    window.prepareGateForTimeAxis(frame["timeAxisUs"])
    window.updateAScanPlot(
        timeAxisUs=frame["timeAxisUs"],
        rawSignal=frame["rawSignal"],
        envelopeSignal=frame["envelopeSignal"],
        thresholdLevel=frame["thresholdLevel"],
        gateRangeUs=frame["gateRangeUs"],
        peakTimeUs=frame["peakTimeUs"],
        peakAmplitude=frame["peakAmplitude"],
        defectDetected=frame["defectDetected"],
    )
    window.updateBScanImage(frame["bScanMatrix"])
    window.updateStatusPanel(
        frameCounter=frame["frameCounter"],
        peakAmplitude=frame["peakAmplitude"],
        defectDistanceMm=frame["defectDistanceMm"] or 42.6,
        confidence=frame["confidence"],
        pointCount=model.pointCount,
        defectDetected=frame["defectDetected"],
    )
    window.updateQuantitativePanel(
        depthMm=frame["defectDistanceMm"] or 42.6,
        horizontalDistanceMm=(frame["defectDistanceMm"] or 42.6) * 2.0,
        dbDifference=4.8,
        peakPercent=frame["peakAmplitude"] * 100.0,
        kValue=2.0,
    )
    window._appendDefectRow(28.4, 0.72)
    window._appendDefectRow(54.0, 0.91)
    window._appendDefectRow(72.5, 0.64)
    return window, model


def generate_main_screenshots(app: QApplication):
    """Capture the main workspace and its principal controls."""
    window, model = build_main_window()
    capture(window, "ui_main.png")

    control_scroll = window.controlDockWidget.widget()
    if control_scroll is not None:
        control_content = control_scroll.widget()
        if control_content is not None:
            control_content.resize(control_content.sizeHint())
            control_content.show()
            for _ in range(4):
                QApplication.processEvents()
            source = control_content.grab()
            half_height = (source.height() + 1) // 2
            left = source.copy(0, 0, source.width(), half_height)
            right = source.copy(
                0,
                half_height,
                source.width(),
                source.height() - half_height,
            )
            gap = 20
            combined = QPixmap(source.width() * 2 + gap, half_height)
            combined.fill(Qt.transparent)
            painter = QPainter(combined)
            painter.drawPixmap(0, 0, left)
            painter.drawPixmap(source.width() + gap, 0, right)
            painter.end()
            combined.save(str(IMAGE_DIR / "control_panel.png"))
            control_content.hide()

    frame = model.generateFrame()
    frequencies, magnitude = model.compute_fft(
        frame["rawSignal"],
        n_fft=1024,
        window="汉宁窗",
    )
    window.fftPanel.update_fft_display(
        frequencies,
        magnitude,
        float(frequencies[int(np.argmax(magnitude))]),
        float(np.max(magnitude)),
    )
    capture(window.fftPanel, "fft_panel.png")

    records = [
        (28.5, 0.72),
        (54.0, 0.91),
        (72.5, 0.64),
        (95.0, 0.56),
    ]
    analyzer = DefectAnalyzer()
    for index, (depth, amplitude) in enumerate(records, start=1):
        analyzer.add_record(
            DefectRecord(index, depth, amplitude, f"2026-09-26 14:0{index}:00")
        )
    statistics = analyzer.get_statistics()
    statistics_data = {
        "total_count": statistics.total_count,
        "depth_min_mm": statistics.depth_min_mm,
        "depth_max_mm": statistics.depth_max_mm,
        "depth_mean_mm": statistics.depth_mean_mm,
        "amplitude_mean": statistics.amplitude_mean,
        "depth_distribution": statistics.depth_distribution,
        "amplitude_distribution": statistics.amplitude_distribution,
    }
    window.statisticsPanel.update_statistics(statistics_data)
    depths = np.asarray([item[0] for item in records])
    amplitudes = np.asarray([item[1] for item in records])
    dac_depths, dac_amplitudes = analyzer.generate_dac_curve(
        depth_range_mm=(0.0, 150.0),
        reference_depth_mm=50.0,
        reference_amplitude=1.0,
    )
    window.statisticsPanel.update_dac_curve(
        dac_depths,
        dac_amplitudes,
        defect_depths=depths.tolist(),
        defect_amplitudes=amplitudes.tolist(),
    )
    statistics_panel = StatisticsPanel()
    statistics_panel.resize(650, 900)
    statistics_panel.update_statistics(statistics_data)
    statistics_panel.update_dac_curve(
        dac_depths,
        dac_amplitudes,
        defect_depths=depths.tolist(),
        defect_amplitudes=amplitudes.tolist(),
    )
    capture(statistics_panel, "statistics_panel.png")

    window.toggleFFTAction.setChecked(True)
    window.toggleStatisticsAction.setChecked(True)
    capture(window, "workspace_analysis.png")

    advanced = window.advancedUTPanel
    advanced.gate_rows["B"].enabled_checkbox.setChecked(True)
    advanced.gate_rows["B"].set_result(True, 0.82)
    advanced.gate_rows["C"].enabled_checkbox.setChecked(True)
    advanced.gate_rows["C"].set_result(False, 0.48)
    advanced.tcg_enabled_checkbox.setChecked(True)
    capture(advanced, "advanced_ut_panel.png")

    scan_panel = ScanPanel()
    scan_panel.resize(1200, 650)
    b_scan = np.zeros((120, 1024), dtype=np.float32)
    for row, center in enumerate((220, 520, 760)):
        for r in range(120):
            width = 10.0 + r / 25.0
            b_scan[r] += np.exp(-0.5 * ((np.arange(1024) - center) / width) ** 2) * (
                0.5 + 0.25 * row
            )
    b_scan += np.linspace(0.04, 0.18, 120, dtype=np.float32)[:, None]
    c_scan = np.zeros((10, 10), dtype=np.float32)
    c_scan[3, 4] = 0.92
    c_scan[7, 7] = 0.68
    c_scan[5, 1] = 0.48
    scan_panel.update_b_scan(b_scan)
    scan_panel.update_c_scan(c_scan)
    window.scanPanel.update_b_scan(b_scan)
    window.scanPanel.update_c_scan(c_scan)
    scan_panel.tabs.setCurrentIndex(0)
    capture(scan_panel, "bscan_panel.png")
    scan_panel.tabs.setCurrentIndex(1)
    capture(scan_panel, "cscan_panel.png")

    window.toggleAdvancedUTAction.setChecked(True)
    window.toggleScanPanelAction.setChecked(True)

    window.replayPanel.set_sessions(
        [
            {
                "id": "session-demo",
                "workpiece": "钢板-试件A",
                "started_at": "2026-09-26T14:05:00",
            }
        ]
    )
    window.replayPanel.set_frame_count(80)
    window.replayPanel.frame_slider.setValue(37)
    window.toggleReplayAction.setChecked(True)
    capture(window.replayPanel, "replay_panel.png")
    waveform_pixmap = window.aScanPlot.grab()
    window.close()
    return waveform_pixmap


def generate_dialog_screenshots(app: QApplication, waveform_pixmap: QPixmap) -> None:
    """Capture dialogs that are not visible in the main workspace."""
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)

        auth = AuthService(root / "auth.db")
        login = LoginDialog(auth)
        login.username_edit.setText("admin")
        login.password_edit.setText("password-123")
        capture(login, "login_dialog.png")
        login.close()

        admin = auth.create_user("admin", "password-123", Role.ADMIN, bootstrap=True)
        for action, entity, details in (
            ("session.start", "session", {"workpiece": "钢板-试件A"}),
            ("defect.add", "defect", {"depth_mm": 54.0, "amplitude": 0.91}),
            ("report.sign", "report", {"format": "pdf"}),
        ):
            auth.record_audit(admin.id, action, entity, "demo-001", details)
        audit = AuditDialog(auth)
        audit.reload_events()
        audit.verify_chain()
        capture(audit, "audit_dialog.png")
        audit.close()

        config_dialog = ReportConfigDialog(
            ReportConfig(
                standard_key="NB/T 47013",
                workpiece_name="钢板-试件A",
                company_name="示例检测有限公司",
                project_name="压力容器定期检验",
                operator_name="张三",
                inspector_name="李四",
                test_location="检测实验室",
                notes="按工艺卡完成扫查，未见超标缺陷扩展。",
            )
        )
        capture(config_dialog, "report_config_dialog.png")
        config_dialog.close()

        generator = ReportGenerator()
        report_html = generator.generate_html_report(
            config=ReportConfig(
                standard_key="NB/T 47013",
                workpiece_name="钢板-试件A",
                company_name="示例检测有限公司",
                operator_name="张三",
                inspector_name="李四",
            ),
            detection_time="2026-09-26 14:20:00",
            decision_result="不合格",
            overview_image_data_uri="",
            defect_records=[],
            defect_snapshots=[
                {"depthMm": 28.4, "amplitude": 0.72, "imageDataUri": ""},
                {"depthMm": 54.0, "amplitude": 0.91, "imageDataUri": ""},
                {"depthMm": 72.5, "amplitude": 0.64, "imageDataUri": ""},
            ],
            parameters={
                "samplingRateHz": 20_000_000.0,
                "pulseFrequencyHz": 2_500_000.0,
                "gainDb": 22.0,
                "scanDepthMm": 120.0,
                "soundVelocityMps": 5900.0,
                "thresholdLevel": 0.55,
            },
            signed_by="张三",
            signed_at="2026-09-26 14:22:00",
        )
        preview = ReportPreviewWindow(
            waveformPixmap=waveform_pixmap,
            reportHtml=report_html,
        )
        capture(preview, "report_preview.png")
        preview.close()
        auth.close()


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyleSheet(buildDarkIndustrialStyleSheet())
    waveform_pixmap = generate_main_screenshots(app)
    generate_dialog_screenshots(app, waveform_pixmap)
    print(f"Screenshots written to {IMAGE_DIR}")


if __name__ == "__main__":
    main()
