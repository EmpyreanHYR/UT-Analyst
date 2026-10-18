"""Generate manual screenshots from the current Qt user interface."""

from __future__ import annotations

import math
import tempfile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from PyQt5.QtCore import QLineF, QPoint, QPointF, QRect, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PyQt5.QtWidgets import QApplication, QGroupBox, QMenu

from app.common.auth import AuthService, Role
from app.common.report_generator import ReportConfig, ReportGenerator
from app.common.theme import buildDarkIndustrialStyleSheet
from app.model import acceptance_criteria as acceptance
from app.model.defect_analyzer import DefectAnalyzer, DefectRecord
from app.model.defect_classifier import DefectFeatures, classify_defect
from app.model.defect_tracker import track_defects
from app.model.session_repository import FrameChunkStore, SessionRepository
from app.model.ultrasonic_model import UltrasonicSignalModel
from app.view.acceptance_dialog import AcceptanceCriteriaDialog
from app.view.advanced_ut_panel import AdvancedUTPanel
from app.view.audit_dialog import AuditDialog
from app.view.login_dialog import LoginDialog
from app.view.main_window import MainWindow
from app.view.replay_panel import ReplayPanel
from app.view.report_config_dialog import ReportConfigDialog
from app.view.report_preview_window import ReportPreviewWindow
from app.view.scan_panel import ScanPanel
from app.view.statistics_panel import StatisticsPanel
from app.view.tracking_dialog import TrackingDialog


IMAGE_DIR = PROJECT_ROOT / "Direction" / "image"

# 演示用的缺陷快照与工件壁厚，供验收判定与类型提示截图使用。
DEMO_WALL_THICKNESS_MM = 100.0
DEMO_DEFECT_SNAPSHOTS = [
    {
        "recordUid": 1,
        "depthMm": 28.4,
        "amplitude": 0.72,
        "dbAboveDac": -1.2,
        "indicationLengthMm": 4.0,
        "indicationHeightMm": 3.0,
    },
    {
        "recordUid": 2,
        "depthMm": 54.0,
        "amplitude": 0.91,
        "dbAboveDac": 4.6,
        "indicationLengthMm": 14.0,
        "indicationHeightMm": 4.0,
    },
    {
        "recordUid": 3,
        "depthMm": 72.5,
        "amplitude": 0.64,
        "dbAboveDac": 0.8,
        "indicationLengthMm": 22.0,
        "indicationHeightMm": 2.0,
    },
    {
        "recordUid": 4,
        "depthMm": 95.0,
        "amplitude": 0.56,
        "dbAboveDac": None,
        "indicationLengthMm": None,
        "indicationHeightMm": None,
    },
]

# 演示用的跨会话记录：同一深度在两次检测中重复出现，波幅与指示长度都有变化。
DEMO_TRACKING_RECORDS = [
    {
        "session_id": "session-a",
        "session_started_at": "2026-03-12T09:10:00",
        "record_uid": 11,
        "detected_at": "2026-03-12 09:24:00",
        "depth_mm": 28.6,
        "amplitude": 0.66,
        "indication_length_mm": 3.0,
    },
    {
        "session_id": "session-a",
        "session_started_at": "2026-03-12T09:10:00",
        "record_uid": 12,
        "detected_at": "2026-03-12 09:41:00",
        "depth_mm": 54.2,
        "amplitude": 0.78,
        "indication_length_mm": 11.0,
    },
    {
        "session_id": "session-b",
        "session_started_at": "2026-09-26T14:05:00",
        "record_uid": 21,
        "detected_at": "2026-09-26 14:21:00",
        "depth_mm": 28.4,
        "amplitude": 0.72,
        "indication_length_mm": 4.0,
    },
    {
        "session_id": "session-b",
        "session_started_at": "2026-09-26T14:05:00",
        "record_uid": 22,
        "detected_at": "2026-09-26 14:33:00",
        "depth_mm": 54.0,
        "amplitude": 0.91,
        "indication_length_mm": 14.0,
    },
    {
        "session_id": "session-b",
        "session_started_at": "2026-09-26T14:05:00",
        "record_uid": 23,
        "detected_at": "2026-09-26 14:52:00",
        "depth_mm": 95.0,
        "amplitude": 0.56,
        "indication_length_mm": None,
    },
]


def build_demo_report_snapshots() -> list[dict]:
    """把演示缺陷快照换成报告生成器需要的字段名。"""
    return [
        {
            "depthMm": snapshot["depthMm"],
            "amplitude": snapshot["amplitude"],
            "indicationLengthMm": snapshot.get("indicationLengthMm"),
            "indicationHeightMm": snapshot.get("indicationHeightMm"),
            "imageDataUri": "",
        }
        for snapshot in DEMO_DEFECT_SNAPSHOTS
    ]


def build_demo_acceptance(snapshots) -> dict:
    """用真实的规则引擎算出演示用的验收判定汇总，并附上类型提示。"""
    profile = acceptance.get_profile("GB/T 11345")
    inputs = [
        acceptance.DefectEvaluationInput(
            uid=int(snapshot["recordUid"]),
            depth_mm=float(snapshot["depthMm"]),
            amplitude=float(snapshot["amplitude"]),
            db_above_dac=(
                None if snapshot.get("dbAboveDac") is None else float(snapshot["dbAboveDac"])
            ),
            indication_length_mm=snapshot.get("indicationLengthMm"),
            wall_thickness_mm=DEMO_WALL_THICKNESS_MM,
        )
        for snapshot in snapshots
    ]
    payload = acceptance.evaluate_records(inputs, profile).to_dict()
    for evaluation, snapshot in zip(payload["evaluations"], snapshots):
        hint = classify_defect(
            DefectFeatures(
                depth_mm=float(snapshot["depthMm"]),
                amplitude=float(snapshot["amplitude"]),
                indication_length_mm=snapshot.get("indicationLengthMm"),
                indication_height_mm=snapshot.get("indicationHeightMm"),
                wall_thickness_mm=DEMO_WALL_THICKNESS_MM,
            )
        )
        evaluation["type_hint"] = hint.short_text()
    return payload


def fill_demo_defect_table(window: MainWindow) -> None:
    """按示例缺陷的深度匹配判定结果，填入缺陷表的“判定”列。

    表格里的历史行由 `build_main_window` 追加，这里只回填判定文字，使插图与
    当前四列缺陷表一致；“实时”行没有记录 UID，保持界面自己的 `--`。
    """
    table = window.defectTableWidget
    evaluations = build_demo_acceptance(DEMO_DEFECT_SNAPSHOTS)["evaluations"]
    by_depth = {
        round(float(snapshot["depthMm"]), 2): item
        for snapshot, item in zip(DEMO_DEFECT_SNAPSHOTS, evaluations)
    }

    judgements: dict[int, str] = {}
    for row in range(table.rowCount()):
        index_item = table.item(row, 0)
        depth_item = table.item(row, 1)
        if index_item is None or depth_item is None:
            continue
        uid = index_item.data(Qt.UserRole)
        if uid is None:
            continue
        try:
            depth = round(float(depth_item.text()), 2)
        except ValueError:
            continue
        item = by_depth.get(depth)
        if item is None:
            continue
        judgements[int(uid)] = f"{item['level']}级 · {item['verdict']}"
    window.updateDefectJudgements(judgements)


def capture_defect_table(window: MainWindow) -> None:
    """把缺陷表与右键菜单合成一张插图，保持与旧插图相同的构图。"""
    table_pixmap = window.defectTableWidget.grab()

    menu = QMenu(window)
    menu.addAction("删除选中记录")
    menu.addAction("清空历史记录")
    menu.setAttribute(Qt.WA_DontShowOnScreen, True)
    menu.show()
    for _ in range(4):
        QApplication.processEvents()
    menu_pixmap = menu.grab()
    menu.hide()

    combined = QPixmap(table_pixmap.size())
    combined.fill(Qt.transparent)
    painter = QPainter(combined)
    painter.drawPixmap(0, 0, table_pixmap)
    # 菜单压在“波幅”列上，让末列“判定”的值保持可见。
    painter.drawPixmap(
        int(table_pixmap.width() * 0.28),
        int(table_pixmap.height() * 0.25),
        menu_pixmap,
    )
    painter.end()
    combined.save(str(IMAGE_DIR / "defect.png"))


def capture(widget, filename: str) -> None:
    """Render and save a widget screenshot."""
    widget.show()
    for _ in range(4):
        QApplication.processEvents()
    widget.grab().save(str(IMAGE_DIR / filename))
    widget.hide()


def capture_top_region(widget, filename: str, height: int) -> None:
    """Render a widget and save only its top strip, for close-up figures."""
    widget.show()
    for _ in range(4):
        QApplication.processEvents()
    pixmap = widget.grab()
    widget.hide()
    band = min(height, pixmap.height())
    pixmap.copy(0, 0, pixmap.width(), band).save(str(IMAGE_DIR / filename))


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
    window._appendDefectRow(95.0, 0.56)
    return window, model


def generate_main_screenshots(app: QApplication):
    """Capture the main workspace and its principal controls."""
    window, model = build_main_window()
    fill_demo_defect_table(window)
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
        (28.4, 0.72),
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
        "acceptance": build_demo_acceptance(DEMO_DEFECT_SNAPSHOTS),
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
    capture_defect_table(window)

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
            defect_snapshots=build_demo_report_snapshots(),
            acceptance_summary=build_demo_acceptance(DEMO_DEFECT_SNAPSHOTS),
            tracking_summary=track_defects(DEMO_TRACKING_RECORDS).to_dict(),
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


def generate_feature_screenshots(app: QApplication) -> None:
    """Capture the acceptance criteria, statistics detail and tracking views."""
    dialog = AcceptanceCriteriaDialog("GB/T 11345", "Ⅱ", DEMO_WALL_THICKNESS_MM, 2.0)
    dialog.adjustSize()
    capture(dialog, "acceptance_dialog.png")
    dialog.close()

    panel = StatisticsPanel()
    panel.update_statistics(
        {
            "total_count": len(DEMO_DEFECT_SNAPSHOTS),
            "depth_min_mm": 28.4,
            "depth_max_mm": 95.0,
            "depth_mean_mm": 62.5,
            "amplitude_mean": 0.71,
            "depth_distribution": {"20-30": 1, "50-60": 1, "70-80": 1, "90-100": 1},
            "amplitude_distribution": {"50-60": 1, "60-70": 1, "70-80": 1, "90-100": 1},
            "acceptance": build_demo_acceptance(DEMO_DEFECT_SNAPSHOTS),
        }
    )
    # 先刷新数据再定尺寸，否则判定明细行数增加后布局还会按旧文字算高度。
    panel.resize(650, 900)
    capture_top_region(panel, "acceptance_detail.png", 340)
    panel.close()

    tracking = TrackingDialog(track_defects(DEMO_TRACKING_RECORDS).to_dict())
    tracking.resize(840, 260)
    capture(tracking, "tracking_dialog.png")
    tracking.close()


_ANNOTATION_COLOR = QColor(255, 255, 255)
_ANNOTATION_LABEL_COLOR = QColor(10, 14, 20, 200)


def find_group_box(window: MainWindow, title: str):
    """按标题找到控制面板里的分组框。"""
    for box in window.findChildren(QGroupBox):
        if box.title() == title:
            return box
    return None


def plot_area(window: MainWindow) -> QRect:
    """A-Scan 绘图区在主窗口内的像素范围。"""
    plot = window.aScanPlot
    scene_rect = plot.getViewBox().sceneBoundingRect()
    top_left = plot.mapTo(window, plot.mapFromScene(scene_rect.topLeft().toPoint()))
    bottom_right = plot.mapTo(window, plot.mapFromScene(scene_rect.bottomRight().toPoint()))
    return QRect(top_left, bottom_right).normalized()


def window_point(window: MainWindow, x_value: float, y_value: float) -> QPoint:
    """把 A-Scan 数据坐标换算成主窗口内的像素坐标。"""
    plot = window.aScanPlot
    scene_point = plot.getViewBox().mapViewToScene(QPointF(x_value, y_value))
    return plot.mapTo(window, plot.mapFromScene(scene_point.toPoint()))


def draw_arrow(painter: QPainter, start: QPoint, end: QPoint, head: int = 13) -> None:
    """画一条白色粗箭头，箭头尖落在 end 处。"""
    if start == end:
        return
    painter.setPen(QPen(_ANNOTATION_COLOR, 3, Qt.SolidLine, Qt.FlatCap))
    painter.setBrush(Qt.NoBrush)
    painter.drawLine(start, end)
    angle = math.radians(QLineF(start, end).angle())
    points = [QPointF(end)]
    for delta in (math.radians(150.0), math.radians(-150.0)):
        points.append(
            QPointF(
                end.x() + head * math.cos(angle + delta),
                end.y() - head * math.sin(angle + delta),
            )
        )
    painter.setPen(Qt.NoPen)
    painter.setBrush(_ANNOTATION_COLOR)
    painter.drawPolygon(QPolygonF(points))


def draw_callout(painter: QPainter, center: QPoint, text: str) -> QRect:
    """画一个深底白字的小标签，返回标签矩形，便于在边缘接箭头。"""
    font = QFont(painter.font())
    font.setPointSize(12)
    font.setBold(True)
    painter.setFont(font)
    rect = painter.fontMetrics().boundingRect(text).adjusted(-9, -4, 9, 4)
    rect.moveCenter(center)
    painter.setPen(Qt.NoPen)
    painter.setBrush(_ANNOTATION_LABEL_COLOR)
    painter.drawRoundedRect(rect, 5, 5)
    painter.setPen(_ANNOTATION_COLOR)
    painter.drawText(rect, Qt.AlignCenter, text)
    return rect


def build_offscreen_window() -> MainWindow:
    """建一个离屏显示的主窗口，用于带标注的示意图。"""
    window, _model = build_main_window()
    fill_demo_defect_table(window)
    window.setAttribute(Qt.WA_DontShowOnScreen, True)
    window.show()
    for _ in range(4):
        QApplication.processEvents()
    return window


def prepare_control_dock(window: MainWindow, group_title: str, width: int = 330) -> None:
    """把右侧控制面板调宽并滚到指定分组，便于插图和实际参数对照。"""
    window.resizeDocks([window.controlDockWidget], [width], Qt.Horizontal)
    for _ in range(3):
        QApplication.processEvents()
    scroll = window.controlDockWidget.widget()
    box = find_group_box(window, group_title)
    if scroll is None or box is None:
        return
    bar = scroll.verticalScrollBar()
    bar.setValue(max(0, min(box.y() - 30, bar.maximum())))
    for _ in range(3):
        QApplication.processEvents()


def annotate_gate_figure() -> None:
    """闸门起点、宽度、门限位置示意图。"""
    window = build_offscreen_window()
    prepare_control_dock(window, "闸门设置 (Gate A)")
    area = plot_area(window)
    start_x = window_point(window, float(window.gateStartLine.value()), 0.0).x()
    end_x = window_point(window, float(window.gateEndLine.value()), 0.0).x()
    level_y = window_point(window, 0.0, float(window.thresholdLine.value())).y()
    gate_rect = QRect(
        QPoint(min(start_x, end_x), area.top() + int(area.height() * 0.08)),
        QPoint(max(start_x, end_x), level_y + 28),
    ).normalized()

    pixmap = window.grab()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(_ANNOTATION_COLOR, 3))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(gate_rect)

    level_center = QPoint(max(area.left() + 100, gate_rect.left() - 140), level_y - 80)
    level_label = draw_callout(painter, level_center, "门限")
    draw_arrow(
        painter,
        QPoint(level_center.x(), level_label.bottom() + 8),
        QPoint(level_center.x(), level_y - 8),
    )

    width_y = (gate_rect.top() + level_y) // 2
    width_center = QPoint(min(area.right() - 80, gate_rect.right() + 115), width_y)
    width_label = draw_callout(painter, width_center, "宽度")
    draw_arrow(
        painter,
        QPoint(width_label.left() - 8, width_y),
        QPoint(gate_rect.right() + 10, width_y),
    )

    start_y = area.bottom() - 70
    start_center = QPoint(gate_rect.left() + 190, start_y)
    start_label = draw_callout(painter, start_center, "起点")
    draw_arrow(
        painter,
        QPoint(start_label.left() - 8, start_y),
        QPoint(gate_rect.left() + 10, start_y),
    )
    painter.end()
    pixmap.save(str(IMAGE_DIR / "gate_lines.png"))
    window.hide()


def annotate_cursor_figure() -> None:
    """A/B 游标线与差值读数对应关系示意图。"""
    window = build_offscreen_window()
    prepare_control_dock(window, "游标读数")
    for _ in range(3):
        QApplication.processEvents()

    x_values, y_values = window.envelopeCurve.getData()
    if x_values is None or len(x_values) == 0:
        x_values, y_values = window.rawSignalCurve.getData()
    magnitude = np.abs(np.asarray(y_values, dtype=float))
    head = max(4, int(len(magnitude) * 0.2))
    tail = int(len(magnitude) * 0.3)
    index_a = int(np.argmax(magnitude[:head]))
    index_b = tail + int(np.argmax(magnitude[tail:]))
    window.cursorLineA.setValue(float(x_values[index_a]))
    window.cursorLineB.setValue(float(x_values[index_b]))
    for _ in range(3):
        QApplication.processEvents()

    area = plot_area(window)
    pixmap = window.grab()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    cursor_y = area.top() + int(area.height() * 0.62)
    a_x = window_point(window, float(x_values[index_a]), 0.0).x()
    b_x = window_point(window, float(x_values[index_b]), 0.0).x()
    right_limit = area.right() - 85
    label_a = draw_callout(painter, QPoint(min(a_x + 130, right_limit), cursor_y), "游标 A")
    draw_arrow(painter, QPoint(label_a.left() - 8, cursor_y), QPoint(a_x + 10, cursor_y))
    label_b = draw_callout(painter, QPoint(min(b_x + 130, right_limit), cursor_y), "游标 B")
    draw_arrow(painter, QPoint(label_b.left() - 8, cursor_y), QPoint(b_x + 10, cursor_y))

    box = find_group_box(window, "游标读数")
    if box is not None:
        rect = QRect(box.mapTo(window, QPoint(0, 0)), box.size()).adjusted(-6, -6, 6, 6)
        if window.rect().contains(rect):
            painter.setPen(QPen(_ANNOTATION_COLOR, 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 8, 8)
    painter.end()
    pixmap.save(str(IMAGE_DIR / "cursor_ab.png"))
    window.hide()


def generate_annotation_screenshots() -> None:
    """重出两张带说明标注的 A-Scan 示意图。"""
    annotate_gate_figure()
    annotate_cursor_figure()


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyleSheet(buildDarkIndustrialStyleSheet())
    waveform_pixmap = generate_main_screenshots(app)
    generate_dialog_screenshots(app, waveform_pixmap)
    generate_feature_screenshots(app)
    generate_annotation_screenshots()
    print(f"Screenshots written to {IMAGE_DIR}")


if __name__ == "__main__":
    main()
