"""Local login and first-run administrator setup dialog."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.common.auth import AuthService, Role, User


class LoginDialog(QDialog):
    """Authenticate a local user or bootstrap the first administrator."""

    def __init__(
        self,
        auth_service: AuthService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.auth_service = auth_service
        self.authenticated_user: User | None = None
        self.is_bootstrap = auth_service.get_user_count() == 0

        self.setWindowTitle("首次初始化" if self.is_bootstrap else "用户登录")
        self.resize(380, 210)
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("用户名:", self.username_edit)
        form.addRow("密码:", self.password_edit)
        root.addLayout(form)

        self.message_label = QLabel(
            "首次运行将创建本地管理员账户。" if self.is_bootstrap else ""
        )
        self.message_label.setWordWrap(True)
        root.addWidget(self.message_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(
            "创建管理员" if self.is_bootstrap else "登录"
        )
        buttons.accepted.connect(self.submit_credentials)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def submit_credentials(self) -> None:
        """Authenticate or create the first administrator."""
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        try:
            if self.is_bootstrap:
                self.authenticated_user = self.auth_service.create_user(
                    username,
                    password,
                    role=Role.ADMIN,
                    bootstrap=True,
                )
            else:
                self.authenticated_user = self.auth_service.authenticate(
                    username,
                    password,
                )
        except Exception as error:
            self.message_label.setText(str(error))
            self.message_label.setStyleSheet("color: #ff6b6b;")
            return
        self.accept()
