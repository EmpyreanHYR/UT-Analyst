"""频谱分析面板（View）。"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.common.plot_style import create_plot_widget
from app.common.theme import BACKGROUND_COLOR


class FFTPanel(QWidget):
    """
    频谱分析面板。

    功能：
    1. 显示FFT频谱图
    2. 提供频谱分析参数控制
    3. 支持频谱测量（峰值频率、幅值等）
    """

    # 信号定义
    fftRequested = pyqtSignal(dict)  # 请求计算FFT，参数为分析设置
    filterApplied = pyqtSignal(dict)  # 应用滤波器，参数为滤波器设置
    filterResetRequested = pyqtSignal()
    signalAverageChanged = pyqtSignal(bool, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("频谱分析")

        # 初始化UI
        self._build_ui()

        # 连接信号
        self._connect_signals()

    def _build_ui(self) -> None:
        """构建UI布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # 频谱图显示区域
        self.fft_plot_widget = create_plot_widget("频谱分析")
        self.fft_plot_widget.setLabel('left', '幅值', units='dB')
        self.fft_plot_widget.setLabel('bottom', '频率', units='Hz')
        self.fft_plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.fft_plot_widget.setBackground(BACKGROUND_COLOR)

        # 频谱曲线
        self.fft_curve = self.fft_plot_widget.plot(pen='g', width=2)

        # 峰值标记
        self.peak_scatter = pg.ScatterPlotItem(size=10, pen='r', brush='r')
        self.fft_plot_widget.addItem(self.peak_scatter)

        layout.addWidget(self.fft_plot_widget)

        # 控制面板
        control_group = QGroupBox("频谱分析参数")
        control_layout = QFormLayout(control_group)

        # FFT点数选择
        self.fft_size_spinbox = QSpinBox()
        self.fft_size_spinbox.setRange(256, 8192)
        self.fft_size_spinbox.setValue(1024)
        self.fft_size_spinbox.setSingleStep(256)
        control_layout.addRow("FFT点数:", self.fft_size_spinbox)

        # 窗函数选择
        self.window_combo = QComboBox()
        self.window_combo.addItems(["矩形窗", "汉宁窗", "汉明窗", "布莱克曼窗"])
        control_layout.addRow("窗函数:", self.window_combo)

        # 频率范围显示
        self.freq_range_label = QLabel("0 - 0 Hz")
        control_layout.addRow("频率范围:", self.freq_range_label)

        # 峰值频率显示
        self.peak_freq_label = QLabel("0 Hz")
        control_layout.addRow("峰值频率:", self.peak_freq_label)

        # 峰值幅值显示
        self.peak_magnitude_label = QLabel("0 dB")
        control_layout.addRow("峰值幅值:", self.peak_magnitude_label)

        # 按钮区域
        button_layout = QHBoxLayout()

        self.compute_fft_button = QPushButton("计算FFT")
        self.clear_fft_button = QPushButton("清除")

        button_layout.addWidget(self.compute_fft_button)
        button_layout.addWidget(self.clear_fft_button)

        control_layout.addRow(button_layout)

        layout.addWidget(control_group)

        # 滤波器控制
        filter_group = QGroupBox("数字滤波器")
        filter_layout = QFormLayout(filter_group)

        # 滤波器类型
        self.filter_type_combo = QComboBox()
        self.filter_type_combo.addItems(["带通", "低通", "高通"])
        filter_layout.addRow("滤波器类型:", self.filter_type_combo)

        # 低频截止
        self.low_freq_spinbox = QDoubleSpinBox()
        self.low_freq_spinbox.setRange(0.001, 50.0)
        self.low_freq_spinbox.setValue(0.1)
        self.low_freq_spinbox.setSingleStep(0.1)
        self.low_freq_spinbox.setSuffix(" MHz")
        filter_layout.addRow("低频截止:", self.low_freq_spinbox)

        # 高频截止
        self.high_freq_spinbox = QDoubleSpinBox()
        self.high_freq_spinbox.setRange(0.001, 50.0)
        self.high_freq_spinbox.setValue(10.0)
        self.high_freq_spinbox.setSingleStep(0.1)
        self.high_freq_spinbox.setSuffix(" MHz")
        filter_layout.addRow("高频截止:", self.high_freq_spinbox)

        # 滤波器阶数
        self.filter_order_spinbox = QSpinBox()
        self.filter_order_spinbox.setRange(1, 10)
        self.filter_order_spinbox.setValue(4)
        filter_layout.addRow("滤波器阶数:", self.filter_order_spinbox)

        # 应用滤波器按钮
        self.apply_filter_button = QPushButton("应用滤波器")
        self.reset_filter_button = QPushButton("复位滤波")
        filter_layout.addRow(self.apply_filter_button)
        filter_layout.addRow(self.reset_filter_button)

        layout.addWidget(filter_group)

        average_group = QGroupBox("信号平均")
        average_layout = QFormLayout(average_group)
        self.signal_average_checkbox = QCheckBox("启用")
        self.signal_average_count_spinbox = QSpinBox()
        self.signal_average_count_spinbox.setRange(2, 64)
        self.signal_average_count_spinbox.setValue(8)
        average_layout.addRow(self.signal_average_checkbox)
        average_layout.addRow("平均帧数:", self.signal_average_count_spinbox)
        layout.addWidget(average_group)

    def _connect_signals(self) -> None:
        """连接信号和槽函数。"""
        self.compute_fft_button.clicked.connect(self._on_compute_fft)
        self.clear_fft_button.clicked.connect(self._on_clear_fft)
        self.apply_filter_button.clicked.connect(self._on_apply_filter)
        self.reset_filter_button.clicked.connect(self.filterResetRequested.emit)
        self.signal_average_checkbox.toggled.connect(self._emit_signal_average)
        self.signal_average_count_spinbox.valueChanged.connect(self._emit_signal_average)

    def _emit_signal_average(self, _value: object = None) -> None:
        """Emit the current signal-average configuration."""
        self.signalAverageChanged.emit(
            self.signal_average_checkbox.isChecked(),
            self.signal_average_count_spinbox.value(),
        )

    def _on_compute_fft(self) -> None:
        """计算FFT按钮点击处理。"""
        settings = {
            'fft_size': self.fft_size_spinbox.value(),
            'window_type': self.window_combo.currentText(),
        }
        self.fftRequested.emit(settings)

    def _on_clear_fft(self) -> None:
        """清除FFT显示。"""
        self.fft_curve.setData([], [])
        self.peak_scatter.setData([], [])
        self.peak_freq_label.setText("0 Hz")
        self.peak_magnitude_label.setText("0 dB")

    def _on_apply_filter(self) -> None:
        """应用滤波器按钮点击处理。"""
        filter_settings = {
            'filter_type': self.filter_type_combo.currentText(),
            'low_freq_hz': self.low_freq_spinbox.value() * 1e6,  # 转换为Hz
            'high_freq_hz': self.high_freq_spinbox.value() * 1e6,  # 转换为Hz
            'order': self.filter_order_spinbox.value(),
        }
        self.filterApplied.emit(filter_settings)

    def update_fft_display(self, frequencies: np.ndarray, magnitude: np.ndarray,
                           peak_freq: float, peak_magnitude: float) -> None:
        """
        更新FFT显示。

        参数：
        - frequencies: 频率数组（Hz）
        - magnitude: 幅值数组
        - peak_freq: 峰值频率（Hz）
        - peak_magnitude: 峰值幅值（dB）
        """
        # 转换为dB刻度
        magnitude_db = 20 * np.log10(magnitude + 1e-10)

        # 更新频谱曲线
        self.fft_curve.setData(frequencies, magnitude_db)

        # 更新峰值标记
        self.peak_scatter.setData([peak_freq], [20 * np.log10(peak_magnitude + 1e-10)])

        # 更新标签
        self.peak_freq_label.setText(f"{peak_freq/1e6:.2f} MHz")
        self.peak_magnitude_label.setText(f"{20 * np.log10(peak_magnitude + 1e-10):.1f} dB")

        # 更新频率范围
        if len(frequencies) > 0:
            self.freq_range_label.setText(f"{frequencies[0]/1e6:.2f} - {frequencies[-1]/1e6:.2f} MHz")
