"""Audit event viewer with hash-chain verification."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.common.auth import AuthService
from app.common.time_format import format_display_time


class AuditDialog(QDialog):
    """Display local audit events and verify their integrity."""

    def __init__(
        self,
        auth_service: AuthService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.auth_service = auth_service
        self.setWindowTitle("审计日志")
        self.resize(980, 620)

        root = QVBoxLayout(self)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["时间", "用户ID", "操作", "实体类型", "实体ID", "事件哈希"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.table)

        controls = QHBoxLayout()
        self.refresh_button = QPushButton("刷新")
        self.verify_button = QPushButton("验证审计链")
        self.verification_label = QLabel("尚未验证")
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.verify_button)
        controls.addWidget(self.verification_label)
        controls.addStretch(1)
        root.addLayout(controls)

        self.refresh_button.clicked.connect(self.reload_events)
        self.verify_button.clicked.connect(self.verify_chain)
        self.reload_events()

    def reload_events(self) -> None:
        """Reload recent audit events."""
        events = self.auth_service.list_audit_events()
        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = [
                format_display_time(event["created_at"]),
                event["user_id"] or "",
                event["action"],
                event["entity_type"],
                event["entity_id"],
                event["event_hash"],
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        # 六列都按内容宽度展开后，还要给行号列、边框和滚动条留出空间，
        # 窗口按需放宽，否则最右侧的事件哈希会被裁掉。
        chrome_width = self.table.verticalHeader().width() + 60
        required_width = self.table.horizontalHeader().length() + chrome_width
        if required_width > self.width():
            self.resize(min(required_width, 1500), self.height())

    def verify_chain(self) -> None:
        """Verify that no historical audit event was modified."""
        valid = self.auth_service.verify_audit_chain()
        self.verification_label.setText(
            "审计链验证通过" if valid else "审计链验证失败：检测到篡改"
        )
