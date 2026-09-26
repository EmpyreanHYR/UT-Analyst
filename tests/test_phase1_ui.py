"""Phase 1 UI behavior tests."""

from __future__ import annotations

import numpy as np

from app.view.fft_panel import FFTPanel
from app.view.report_config_dialog import ReportConfigDialog
from app.view.statistics_panel import StatisticsPanel


def test_fft_panel_emits_selected_window_and_average_settings(qapp) -> None:
    panel = FFTPanel()
    requested: list[dict] = []
    average: list[tuple[bool, int]] = []
    panel.fftRequested.connect(requested.append)
    panel.signalAverageChanged.connect(lambda enabled, count: average.append((enabled, count)))

    panel.window_combo.setCurrentText("布莱克曼窗")
    panel.fft_size_spinbox.setValue(2048)
    panel.signal_average_checkbox.setChecked(True)
    panel.signal_average_count_spinbox.setValue(16)
    panel.compute_fft_button.click()

    assert requested[-1]["window_type"] == "布莱克曼窗"
    assert requested[-1]["fft_size"] == 2048
    assert average[-1] == (True, 16)


def test_fft_panel_emits_filter_reset(qapp) -> None:
    panel = FFTPanel()
    reset_calls: list[bool] = []
    panel.filterResetRequested.connect(lambda: reset_calls.append(True))

    panel.reset_filter_button.click()

    assert reset_calls == [True]


def test_statistics_panel_clears_stale_plots(qapp) -> None:
    panel = StatisticsPanel()
    panel.update_statistics(
        {
            "total_count": 2,
            "depth_min_mm": 10.0,
            "depth_max_mm": 30.0,
            "depth_mean_mm": 20.0,
            "amplitude_mean": 0.7,
            "depth_distribution": {"0-10mm": 1, "10-20mm": 1},
            "amplitude_distribution": {"0-10%": 1, "10-20%": 1},
        }
    )
    panel.update_statistics(
        {
            "total_count": 0,
            "depth_min_mm": 0.0,
            "depth_max_mm": 0.0,
            "depth_mean_mm": 0.0,
            "amplitude_mean": 0.0,
            "depth_distribution": {},
            "amplitude_distribution": {},
        }
    )

    assert panel.depth_bargraph.opts["height"] == []
    assert panel.amp_bargraph.opts["height"] == []
    assert panel.total_count_label.text() == "0"
    assert panel.depth_range_label.text() == "0.0 ~ 0.0 mm"


def test_report_config_dialog_returns_complete_values(qapp) -> None:
    dialog = ReportConfigDialog()
    dialog.standard_combo.setCurrentText("NB/T 47013")
    dialog.workpiece_edit.setText("焊缝-01")
    dialog.company_edit.setText("示例公司")
    dialog.project_edit.setText("项目-A")
    dialog.operator_edit.setText("张三")
    dialog.inspector_edit.setText("李四")
    dialog.location_edit.setText("上海")
    dialog.notes_edit.setPlainText("复检")

    config = dialog.build_config()

    assert config.standard_key == "NB/T 47013"
    assert config.workpiece_name == "焊缝-01"
    assert config.company_name == "示例公司"
    assert config.project_name == "项目-A"
    assert config.operator_name == "张三"
    assert config.inspector_name == "李四"
    assert config.test_location == "上海"
    assert config.notes == "复检"
