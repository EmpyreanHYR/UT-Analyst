"""快捷键帮助对话框（View）。"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ShortcutHelpDialog(QDialog):
    """列出当前生效的快捷键绑定。"""

    def __init__(
        self,
        tips: list[tuple[str, str, str]],
        parent: QWidget | None = None,
    ) -> None:
        """
        初始化快捷键帮助对话框。

        参数：
        - tips: 由快捷键管理器给出的 (动作标识, 功能说明, 快捷键) 列表
        """
        super().__init__(parent)
        self.setWindowTitle("快捷键帮助")
        self.resize(520, 660)

        root = QVBoxLayout(self)
        hint = QLabel(
            "下表列出当前生效的绑定。输入框获得焦点时按键会优先作为文字写入，"
            "先点击波形区再使用快捷键。"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.table = QTableWidget(len(tips), 2)
        self.table.setHorizontalHeaderLabels(["功能", "快捷键"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        # 只有两列，宽度永远够用；关掉横向滚动条，避免它在表格底部挤掉一行。
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        for row, (_action_id, description, shortcut) in enumerate(tips):
            self.table.setItem(row, 0, QTableWidgetItem(description))
            shortcut_item = QTableWidgetItem(shortcut)
            shortcut_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, shortcut_item)
        root.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        # Qt 标准按钮的文字来自系统语言包，这里显式写成中文，保证界面语言一致。
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
