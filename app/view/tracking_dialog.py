"""跨会话缺陷跟踪结果对话框（View）。"""

from __future__ import annotations

from typing import Any

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


class TrackingDialog(QDialog):
    """展示跨会话归组结果。

    对话框只负责呈现控制器算好的数据，不在这里做任何归组或判定计算。
    """

    COLUMNS = ["组", "深度(mm)", "会话数", "波幅变化", "长度变化", "说明"]

    def __init__(self, result: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("跨会话缺陷跟踪")
        self.resize(820, 460)

        layout = QVBoxLayout(self)

        tracks = result.get("tracks", [])
        summary_text = (
            f"重复出现的位置：{result.get('repeated_count', 0)} 处；"
            f"跨会话重复：{result.get('cross_session_count', 0)} 处。"
        )
        layout.addWidget(QLabel(summary_text))

        self.table = QTableWidget(len(tracks), len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)

        for rowIndex, track in enumerate(tracks):
            amplitude_change = track.get("amplitude_change")
            length_change = track.get("length_change")
            values = [
                f"#{track.get('track_id', rowIndex + 1)}",
                f"{float(track.get('depth_mm', 0.0)):.1f}",
                str(track.get("session_count", 0)),
                "——" if amplitude_change is None else f"{float(amplitude_change):+.3f}",
                "——" if length_change is None else f"{float(length_change):+.1f} mm",
                str(track.get("note", "")),
            ]
            for columnIndex, text in enumerate(values):
                self.table.setItem(rowIndex, columnIndex, QTableWidgetItem(text))

        layout.addWidget(self.table)

        notes = result.get("notes", [])
        if notes:
            noteLabel = QLabel("\n".join(f"· {note}" for note in notes))
            noteLabel.setWordWrap(True)
            layout.addWidget(noteLabel)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        # Qt 标准按钮的文字来自系统语言包，这里显式写成中文，保证界面语言一致。
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
