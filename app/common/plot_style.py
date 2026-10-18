"""绘图控件的统一风格。

pyqtgraph 的绘图标题默认是灰白色，在深色背景上不够醒目；
这里统一把标题改成主题的橙色强调色，与分组标题、面板标题保持一致的层级感。
"""

from __future__ import annotations

import pyqtgraph as pg

from app.common.theme import ACCENT_COLOR


def create_plot_widget(title: str, title_size: str = "11pt") -> pg.PlotWidget:
    """
    创建标题使用强调色的绘图控件。

    参数：
    - title: 绘图标题；
    - title_size: 标题字号，主波形区等需要更醒目的位置可适当放大。
    """
    widget = pg.PlotWidget()
    widget.setTitle(title, color=ACCENT_COLOR, size=title_size, bold=True)
    return widget
