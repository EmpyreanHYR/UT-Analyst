"""Report configuration dialog."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.common.report_generator import ReportConfig, ReportGenerator


class ReportConfigDialog(QDialog):
    """Collect all report metadata before previewing a report."""

    def __init__(
        self,
        config: ReportConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("报告参数")
        self.resize(520, 480)

        source = config or ReportConfig()
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.standard_combo = QComboBox()
        self.standard_combo.addItems(ReportGenerator().get_available_standards())
        self.standard_combo.setCurrentText(source.standard_key)
        form.addRow("检测标准:", self.standard_combo)

        self.workpiece_edit = QLineEdit(source.workpiece_name)
        form.addRow("工件名称:", self.workpiece_edit)

        self.company_edit = QLineEdit(source.company_name)
        form.addRow("公司名称:", self.company_edit)

        self.project_edit = QLineEdit(source.project_name)
        form.addRow("项目名称:", self.project_edit)

        self.operator_edit = QLineEdit(source.operator_name)
        form.addRow("操作人员:", self.operator_edit)

        self.inspector_edit = QLineEdit(source.inspector_name)
        form.addRow("审核人员:", self.inspector_edit)

        self.location_edit = QLineEdit(source.test_location)
        form.addRow("检测地点:", self.location_edit)

        self.notes_edit = QPlainTextEdit(source.notes)
        self.notes_edit.setMaximumHeight(90)
        form.addRow("备注:", self.notes_edit)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        # Qt 标准按钮的文字来自系统语言包，这里显式写成中文，保证界面语言一致。
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def build_config(self) -> ReportConfig:
        """Create a report configuration from the current values."""
        return ReportConfig(
            standard_key=self.standard_combo.currentText(),
            workpiece_name=self.workpiece_edit.text().strip() or "工件-001",
            operator_name=self.operator_edit.text().strip(),
            inspector_name=self.inspector_edit.text().strip(),
            company_name=self.company_edit.text().strip(),
            project_name=self.project_edit.text().strip(),
            test_location=self.location_edit.text().strip(),
            notes=self.notes_edit.toPlainText().strip(),
        )
