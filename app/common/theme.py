"""应用主题样式定义。"""

from __future__ import annotations


def buildDarkIndustrialStyleSheet() -> str:
    """
    构建深色工业风样式表。

    视觉策略：
    - 主背景采用冷灰深色，降低长时间监看疲劳；
    - 关键操作按钮和告警颜色高对比，提升信息识别效率；
    - 输入控件边框统一细线风格，强调工业软件的秩序感。
    """
    return """
    QMainWindow {
        background-color: #0f141a;
    }

    QWidget {
        background-color: #0f141a;
        color: #d0d7de;
        font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif;
        font-size: 13px;
    }

    QStatusBar {
        background-color: #121a22;
        color: #9fb2c3;
        border-top: 1px solid #2a3744;
    }

    QFrame#controlPanel {
        background-color: #171e27;
        border: 1px solid #2c3b4a;
        border-radius: 10px;
    }

    QGroupBox {
        margin-top: 12px;
        padding: 10px 10px 12px 10px;
        border: 1px solid #2c3a48;
        border-radius: 8px;
        background-color: #131a22;
        font-weight: 600;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: #9cc9e8;
    }

    QLabel {
        color: #cfd8e3;
    }

    QLabel#alarmLabel {
        border-radius: 5px;
        padding: 3px 8px;
        font-weight: 600;
    }

    QLabel#alarmLabel[alarmState="normal"] {
        color: #7ee0bb;
        background-color: rgba(34, 86, 74, 120);
        border: 1px solid #2f6e61;
    }

    QLabel#alarmLabel[alarmState="alert"] {
        color: #ff9b8d;
        background-color: rgba(97, 39, 31, 130);
        border: 1px solid #a75446;
    }

    QPushButton {
        border: 1px solid #355064;
        background-color: #1d2a36;
        border-radius: 6px;
        min-height: 30px;
        padding: 6px 10px;
        color: #d2dbe4;
        font-weight: 500;
    }

    QPushButton:hover {
        background-color: #253848;
        border-color: #46708d;
    }

    QPushButton:pressed {
        background-color: #17222c;
        border-color: #2f4f65;
    }

    QPushButton#primaryActionButton {
        background-color: #205f78;
        border-color: #2f92b4;
        color: #f3fbff;
        font-weight: 700;
    }

    QPushButton#primaryActionButton:hover {
        background-color: #287797;
    }

    QPushButton#primaryActionButton:pressed {
        background-color: #194c61;
    }

    QDoubleSpinBox {
        background-color: #111720;
        border: 1px solid #314252;
        border-radius: 5px;
        padding: 4px 6px;
        min-height: 26px;
        color: #d6dee8;
        selection-background-color: #2f6d8a;
    }

    QDoubleSpinBox:hover {
        border-color: #476479;
    }

    QDoubleSpinBox:focus {
        border: 1px solid #4ca3c5;
        background-color: #121c27;
    }

    QSplitter::handle {
        background-color: #283543;
        height: 4px;
    }
    """
