"""应用主题样式定义。

配色约定（深色工业风）：

- 背景：冷灰深色，降低长时间监看带来的视觉疲劳；
- 正文：偏亮的灰白，保证暗底上的可读性；
- 强调：橙色，用于分组标题、面板标题、菜单高亮与关键读数，
  让一屏之内的重要信息先被看到，正文本身保持中性、不抢眼；
- 语义色：合格/不合格等结论仍用绿、红表示，橙色只承担「提示」含义，
  不替代告警色，避免混淆。

样式表里通过 $BACKGROUND / $TEXT / $MUTED / $ACCENT / $TABLE_ROW 引用下面的颜色常量，
调整配色只需要修改这一处；界面代码需要单独取色时也从本模块导入。
"""

from __future__ import annotations

from string import Template

# 主背景色
BACKGROUND_COLOR = "#0f141a"

# 正文字色：比纯白柔和，但明显亮于早期的灰蓝色，暗底上更清楚
TEXT_COLOR = "#e6edf5"

# 次要文字色（状态栏、分隔符、提示语等）
TEXT_MUTED_COLOR = "#a8b7c6"

# 强调色（橙色）：分组标题、面板标题、菜单高亮与关键读数
ACCENT_COLOR = "#ffa657"

# 表格隔行底色：比主背景略亮，避免默认的浅色隔行底色在深色主题下把文字吃掉
TABLE_ROW_COLOR = "#151d26"

_STYLE_SHEET = Template("""
    QMainWindow {
        background-color: $BACKGROUND;
    }

    QWidget {
        background-color: $BACKGROUND;
        color: $TEXT;
        font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif;
        font-size: 13px;
    }

    QStatusBar {
        background-color: #121a22;
        color: $MUTED;
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
        color: $ACCENT;
        font-weight: 700;
    }

    QLabel {
        color: $TEXT;
    }

    /* 关键读数：定量数据、游标读数、统计值等，用橙色加粗与普通说明文字区分 */
    QLabel#keyValueLabel {
        color: $ACCENT;
        font-weight: 700;
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

    /* 面板标题栏：与分组标题同样使用橙色，形成统一的层级感。
       这里只设置文字色；实测给 QDockWidget::title 加边框/内边距会改变标题栏
       的尺寸计算，窄面板下标题会被提前省略成「…」，所以不额外绘制背景。 */
    QDockWidget {
        color: $ACCENT;
    }

    /* 菜单栏与下拉菜单：平时用正文色，鼠标经过时用橙色提示当前位置 */
    QMenuBar {
        background-color: #121a22;
        color: $TEXT;
        border-bottom: 1px solid #2a3744;
    }

    QMenuBar::item:selected {
        background-color: #1e2c3a;
        color: $ACCENT;
    }

    QMenu {
        background-color: #16202a;
        color: $TEXT;
        border: 1px solid #2c3b4a;
    }

    QMenu::item:selected {
        background-color: #22384b;
        color: $ACCENT;
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

    QSpinBox, QDoubleSpinBox {
        background-color: #111720;
        border: 1px solid #314252;
        border-radius: 5px;
        padding: 4px 6px;
        min-height: 26px;
        color: #d6dee8;
        selection-background-color: #2f6d8a;
    }

    QSpinBox:hover, QDoubleSpinBox:hover {
        border-color: #476479;
    }

    QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #4ca3c5;
        background-color: #121c27;
    }

    /* 多行文本输入：默认样式的白底会与浅色文字同色，这里统一成深底浅字 */
    QTextEdit, QPlainTextEdit {
        background-color: #111720;
        color: $TEXT;
        border: 1px solid #314252;
        border-radius: 5px;
        padding: 4px 6px;
        selection-background-color: #2f6d8a;
    }

    QTableWidget {
        background-color: $BACKGROUND;
        alternate-background-color: $TABLE_ROW;
        color: $TEXT;
    }

    /* 表头：默认样式的浅灰底配浅色字读不清，统一改成深底橙字 */
    QHeaderView::section {
        background-color: #1b2530;
        color: $ACCENT;
        padding: 5px 8px;
        border: none;
        border-right: 1px solid #2a3744;
        border-bottom: 1px solid #2a3744;
        font-weight: 600;
    }

    QTableCornerButton::section {
        background-color: #1b2530;
        border: none;
    }

    QTableWidget::item:selected {
        background-color: #22384b;
        color: $TEXT;
    }

    /* B/C-Scan 等选项卡：默认样式的浅色标签在深色主题下只剩白块 */
    QTabWidget::pane {
        border: 1px solid #2c3a48;
        background-color: $BACKGROUND;
    }

    QTabBar::tab {
        background-color: #16202a;
        color: $MUTED;
        border: 1px solid #2c3a48;
        border-bottom: none;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
        padding: 5px 14px;
        margin-right: 3px;
    }

    QTabBar::tab:selected {
        background-color: #1d2a36;
        color: $ACCENT;
        font-weight: 700;
    }

    QTabBar::tab:hover {
        color: $ACCENT;
    }

    /* 下拉列表弹出层同样使用深色底，避免选中项在主界面之外变成白底浅字 */
    QComboBox QAbstractItemView {
        background-color: #16202a;
        color: $TEXT;
        border: 1px solid #2c3b4a;
        selection-background-color: #22384b;
        selection-color: $ACCENT;
    }

    QSplitter::handle {
        background-color: #283543;
        height: 4px;
    }
    """)


def buildDarkIndustrialStyleSheet() -> str:
    """
    构建深色工业风样式表。

    视觉策略：
    - 主背景采用冷灰深色，降低长时间监看疲劳；
    - 分组标题、面板标题与关键读数使用橙色强调，与正文拉开层次；
    - 关键操作按钮和告警颜色高对比，提升信息识别效率；
    - 输入控件边框统一细线风格，强调工业软件的秩序感。
    """
    return _STYLE_SHEET.substitute(
        BACKGROUND=BACKGROUND_COLOR,
        TEXT=TEXT_COLOR,
        MUTED=TEXT_MUTED_COLOR,
        ACCENT=ACCENT_COLOR,
        TABLE_ROW=TABLE_ROW_COLOR,
    )
