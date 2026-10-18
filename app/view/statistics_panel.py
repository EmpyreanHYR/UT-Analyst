"""缺陷统计分析面板（View）。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.common.plot_style import create_plot_widget
from app.common.theme import ACCENT_COLOR, BACKGROUND_COLOR


class StatisticsPanel(QWidget):
    """
    缺陷统计分析面板。

    功能：
    1. 显示缺陷统计信息（总数、深度分布、波幅分布）
    2. 显示深度趋势图
    3. 显示DAC曲线
    """

    # 信号定义
    refreshRequested = pyqtSignal()  # 请求刷新统计数据

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("缺陷统计分析")

        # 初始化UI
        self._build_ui()

    def _build_ui(self) -> None:
        """构建UI布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # 统计信息显示
        stats_group = QGroupBox("缺陷统计")
        stats_layout = QFormLayout(stats_group)

        self.total_count_label = QLabel("0")
        self.depth_range_label = QLabel("-- ~ -- mm")
        self.depth_mean_label = QLabel("-- mm")
        self.amplitude_mean_label = QLabel("-- %")
        self.criteria_label = QLabel("--")
        self.verdict_label = QLabel("--")

        # 统计值属于关键读数，统一挂上样式名，由主题用橙色加粗显示；
        # 判定结论单独按合格/不合格着色，不参与这里的统一配色。
        for value_label in (
            self.total_count_label,
            self.depth_range_label,
            self.depth_mean_label,
            self.amplitude_mean_label,
            self.criteria_label,
        ):
            value_label.setObjectName("keyValueLabel")

        stats_layout.addRow("缺陷总数:", self.total_count_label)
        stats_layout.addRow("深度范围:", self.depth_range_label)
        stats_layout.addRow("平均深度:", self.depth_mean_label)
        stats_layout.addRow("平均波幅:", self.amplitude_mean_label)
        stats_layout.addRow("验收标准:", self.criteria_label)
        stats_layout.addRow("判定结论:", self.verdict_label)

        layout.addWidget(stats_group)

        # 验收判定明细
        verdict_group = QGroupBox("验收判定明细")
        verdict_layout = QVBoxLayout(verdict_group)

        self.evaluation_detail_label = QLabel("尚无判定明细。")
        self.evaluation_detail_label.setWordWrap(True)
        self.evaluation_detail_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        # 明细行数随缺陷条数、类型提示长度变化；放进滚动区后，面板被压矮时只出现
        # 滚动条，不会把文字裁掉（换行后的实际高度取决于宽度，普通布局算不准）。
        self.evaluation_detail_scroll = QScrollArea()
        self.evaluation_detail_scroll.setWidgetResizable(True)
        self.evaluation_detail_scroll.setFrameShape(QFrame.NoFrame)
        self.evaluation_detail_scroll.setMinimumHeight(88)
        self.evaluation_detail_scroll.setWidget(self.evaluation_detail_label)
        verdict_layout.addWidget(self.evaluation_detail_scroll)
        layout.addWidget(verdict_group)

        # 深度分布图
        depth_group = QGroupBox("深度分布")
        depth_layout = QVBoxLayout(depth_group)

        self.depth_plot_widget = create_plot_widget("缺陷深度分布")
        self.depth_plot_widget.setLabel('left', '数量')
        self.depth_plot_widget.setLabel('bottom', '深度 (mm)')
        self.depth_plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.depth_plot_widget.setBackground(BACKGROUND_COLOR)
        self.depth_plot_widget.setMinimumHeight(150)

        # 深度分布柱状图
        self.depth_bargraph = pg.BarGraphItem(x=[], height=[], width=8, brush='g')
        self.depth_plot_widget.addItem(self.depth_bargraph)

        depth_layout.addWidget(self.depth_plot_widget)
        layout.addWidget(depth_group)

        # 波幅分布图
        amp_group = QGroupBox("波幅分布")
        amp_layout = QVBoxLayout(amp_group)

        self.amp_plot_widget = create_plot_widget("缺陷波幅分布")
        self.amp_plot_widget.setLabel('left', '数量')
        self.amp_plot_widget.setLabel('bottom', '波幅 (%)')
        self.amp_plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.amp_plot_widget.setBackground(BACKGROUND_COLOR)
        self.amp_plot_widget.setMinimumHeight(150)

        # 波幅分布柱状图
        self.amp_bargraph = pg.BarGraphItem(x=[], height=[], width=8, brush='b')
        self.amp_plot_widget.addItem(self.amp_bargraph)

        amp_layout.addWidget(self.amp_plot_widget)
        layout.addWidget(amp_group)

        # DAC曲线图
        dac_group = QGroupBox("DAC曲线")
        dac_layout = QVBoxLayout(dac_group)

        self.dac_plot_widget = create_plot_widget("距离-波幅校正曲线")
        self.dac_plot_widget.setLabel('left', '波幅')
        self.dac_plot_widget.setLabel('bottom', '深度 (mm)')
        self.dac_plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.dac_plot_widget.setBackground(BACKGROUND_COLOR)
        self.dac_plot_widget.setMinimumHeight(150)

        # DAC曲线
        self.dac_curve = self.dac_plot_widget.plot(pen='y', width=2, name="DAC曲线")

        # 缺陷点
        self.defect_scatter = pg.ScatterPlotItem(size=8, pen='r', brush='r')
        self.dac_plot_widget.addItem(self.defect_scatter)

        dac_layout.addWidget(self.dac_plot_widget)
        layout.addWidget(dac_group)

        # 刷新按钮
        button_layout = QHBoxLayout()
        self.refresh_button = QPushButton("刷新统计")
        self.refresh_button.clicked.connect(self.refreshRequested.emit)
        button_layout.addWidget(self.refresh_button)
        layout.addLayout(button_layout)

    def update_statistics(self, stats: dict[str, Any]) -> None:
        """
        更新统计显示。

        参数：
        - stats: 统计信息字典
        """
        self.total_count_label.setText(str(stats.get("total_count", 0)))

        depth_min = stats.get("depth_min_mm", 0.0)
        depth_max = stats.get("depth_max_mm", 0.0)
        self.depth_range_label.setText(f"{depth_min:.1f} ~ {depth_max:.1f} mm")

        depth_mean = stats.get("depth_mean_mm", 0.0)
        self.depth_mean_label.setText(f"{depth_mean:.1f} mm")

        amp_mean = stats.get("amplitude_mean", 0.0)
        self.amplitude_mean_label.setText(f"{amp_mean * 100:.1f} %")

        self._update_acceptance(stats.get("acceptance"))

        # 更新深度分布图
        depth_dist = stats.get("depth_distribution", {})
        if depth_dist:
            x_values = list(range(len(depth_dist)))
            y_values = list(depth_dist.values())
            self.depth_bargraph.setOpts(x=x_values, height=y_values, width=0.8)

            # 设置x轴标签
            labels = list(depth_dist.keys())
            axis = self.depth_plot_widget.getAxis('bottom')
            ticks = [(i, label) for i, label in enumerate(labels)]
            axis.setTicks([ticks])
        else:
            self.depth_bargraph.setOpts(x=[], height=[], width=0.8)
            self.depth_plot_widget.getAxis("bottom").setTicks([])

        # 更新波幅分布图
        amp_dist = stats.get("amplitude_distribution", {})
        if amp_dist:
            x_values = list(range(len(amp_dist)))
            y_values = list(amp_dist.values())
            self.amp_bargraph.setOpts(x=x_values, height=y_values, width=0.8)

            # 设置x轴标签
            labels = list(amp_dist.keys())
            axis = self.amp_plot_widget.getAxis('bottom')
            ticks = [(i, label) for i, label in enumerate(labels)]
            axis.setTicks([ticks])
        else:
            self.amp_bargraph.setOpts(x=[], height=[], width=0.8)
            self.amp_plot_widget.getAxis("bottom").setTicks([])

    def _update_acceptance(self, acceptance: dict[str, Any] | None) -> None:
        """刷新验收标准、整体结论与逐条判定明细。"""
        if not acceptance:
            self.criteria_label.setText("--")
            self.verdict_label.setText("--")
            self.verdict_label.setStyleSheet("")
            self.evaluation_detail_label.setText("尚无判定明细。")
            return

        profile_name = str(acceptance.get("profile_name", "--"))
        level = str(acceptance.get("acceptance_level", ""))
        self.criteria_label.setText(f"{profile_name} / {level}级" if level else profile_name)

        overall = str(acceptance.get("overall_verdict", "--"))
        # 合格/不合格沿用告警语义色；「待定」等需要人工确认的结论用强调色提示。
        color = {"合格": "#7fe7b2", "不合格": "#ff4d4f"}.get(overall, ACCENT_COLOR)
        self.verdict_label.setText(overall)
        self.verdict_label.setStyleSheet(f"color: {color}; font-weight: 700;")

        lines: list[str] = []
        for item in acceptance.get("evaluations", []):
            uid = item.get("uid", 0)
            level_text = item.get("level", "--")
            verdict = item.get("verdict", "--")
            zone = item.get("amplitude_zone", "--")
            db = item.get("db_above_dac")
            db_text = "--" if db is None else f"{float(db):+.1f} dB"
            lines.append(f"#{uid}: {level_text}级（{zone}区 {db_text}）→ {verdict}")
            type_hint = item.get("type_hint")
            if type_hint:
                lines[-1] += f"｜{type_hint}"
        for note in acceptance.get("notes", []):
            lines.append(f"注：{note}")
        self.evaluation_detail_label.setText("\n".join(lines) if lines else "尚无判定明细。")

    def update_dac_curve(self, depths: np.ndarray, amplitudes: np.ndarray,
                         defect_depths: list[float] | None = None,
                         defect_amplitudes: list[float] | None = None) -> None:
        """
        更新DAC曲线显示。

        参数：
        - depths: DAC曲线深度数组
        - amplitudes: DAC曲线波幅数组
        - defect_depths: 缺陷深度列表
        - defect_amplitudes: 缺陷波幅列表
        """
        self.dac_curve.setData(depths, amplitudes)

        if defect_depths and defect_amplitudes:
            self.defect_scatter.setData(defect_depths, defect_amplitudes)
        else:
            self.defect_scatter.setData([], [])
