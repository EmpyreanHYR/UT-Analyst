"""验收标准选择对话框（View）。"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.model.acceptance_criteria import get_profile, list_profile_keys


class AcceptanceCriteriaDialog(QDialog):
    """选择验收标准、验收等级与工件壁厚。

    对话框只负责收集输入，是否合法、规则表是否存在等由控制器统一校验，
    避免把业务规则分散到界面层。
    """

    def __init__(
        self,
        profile_key: str = "",
        acceptance_level: str = "",
        wall_thickness_mm: float | None = None,
        scan_step_mm: float | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("验收标准")
        self.resize(460, 300)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(list_profile_keys())
        self.profile_combo.setCurrentText(profile_key or list_profile_keys()[0])
        form.addRow("验收标准:", self.profile_combo)

        self.level_combo = QComboBox()
        form.addRow("验收等级:", self.level_combo)

        self.thickness_spin = QDoubleSpinBox()
        self.thickness_spin.setRange(0.0, 1000.0)
        self.thickness_spin.setDecimals(1)
        self.thickness_spin.setSingleStep(1.0)
        self.thickness_spin.setSuffix(" mm")
        self.thickness_spin.setSpecialValueText("未指定")
        if wall_thickness_mm:
            self.thickness_spin.setValue(float(wall_thickness_mm))
        form.addRow("工件壁厚:", self.thickness_spin)

        self.scan_step_spin = QDoubleSpinBox()
        self.scan_step_spin.setRange(0.1, 100.0)
        self.scan_step_spin.setDecimals(2)
        self.scan_step_spin.setSingleStep(0.5)
        self.scan_step_spin.setSuffix(" mm")
        self.scan_step_spin.setValue(float(scan_step_mm) if scan_step_mm else 5.0)
        form.addRow("扫查步距:", self.scan_step_spin)

        self.note_label = QLabel("")
        self.note_label.setWordWrap(True)
        layout.addLayout(form)
        layout.addWidget(self.note_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        # Qt 标准按钮的文字来自系统语言包，这里显式写成中文，保证界面语言一致。
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 标准变化时同步等级列表与说明文字。
        self.profile_combo.currentTextChanged.connect(self._sync_profile)
        self._pending_level = acceptance_level
        self._sync_profile(self.profile_combo.currentText())

    def _sync_profile(self, profile_key: str) -> None:
        """按所选标准刷新等级下拉框与说明。"""
        profile = get_profile(profile_key)
        self.level_combo.clear()
        self.level_combo.addItems(profile.levels)
        target = self._pending_level or profile.acceptance_level
        if target in profile.levels:
            self.level_combo.setCurrentText(target)
        else:
            self.level_combo.setCurrentText(profile.acceptance_level)
        self.note_label.setText(profile.note)

    def build_values(self) -> tuple[str, str, float | None, float]:
        """返回 (标准键名, 验收等级, 工件壁厚或 None, 扫查步距)。"""
        thickness = self.thickness_spin.value()
        return (
            self.profile_combo.currentText(),
            self.level_combo.currentText(),
            thickness if thickness > 0.0 else None,
            float(self.scan_step_spin.value()),
        )
