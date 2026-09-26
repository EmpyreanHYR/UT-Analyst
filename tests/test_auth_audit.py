"""Local authentication, role, and audit-chain tests."""

from __future__ import annotations

import sqlite3

import pytest

from app.common.auth import (
    AccountLockedError,
    AuthService,
    Role,
    User,
    has_permission,
)
from app.model.session_repository import SessionRepository
from app.model.ultrasonic_model import UltrasonicSignalModel
from app.view.main_window import MainWindow
from app.controller.main_controller import MainController
from app.view.login_dialog import LoginDialog
from app.view.audit_dialog import AuditDialog


def test_password_authentication_and_role_permissions(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")
    admin = service.create_user("admin", "secret-123", Role.ADMIN, bootstrap=True)

    authenticated = service.authenticate("admin", "secret-123")

    assert authenticated.id == admin.id
    assert has_permission(admin.role, "manage_users")
    assert has_permission(Role.OPERATOR, "acquire")
    assert not has_permission(Role.VIEWER, "edit_report")


def test_wrong_password_locks_account(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db", max_failed_attempts=3)
    service.create_user("operator", "correct-123", Role.OPERATOR, bootstrap=True)

    for _ in range(2):
        with pytest.raises(ValueError, match="用户名或密码错误"):
            service.authenticate("operator", "wrong")

    with pytest.raises(AccountLockedError, match="账户已锁定"):
        service.authenticate("operator", "wrong")
    with pytest.raises(AccountLockedError, match="账户已锁定"):
        service.authenticate("operator", "correct-123")


def test_audit_hash_chain_detects_tampering(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")
    admin = service.create_user("admin", "secret-123", Role.ADMIN, bootstrap=True)
    service.record_audit(admin.id, "session.start", "session", "s1", {"workpiece": "A"})
    service.record_audit(admin.id, "report.export", "report", "r1", {"format": "pdf"})

    assert service.verify_audit_chain() is True

    with sqlite3.connect(tmp_path / "auth.db") as connection:
        connection.execute(
            "UPDATE audit_events SET details_json = ? WHERE id = 1",
            ('{"tampered": true}',),
        )
        connection.commit()

    assert service.verify_audit_chain() is False


def test_report_signature_is_stored_with_hash(tmp_path) -> None:
    database_path = tmp_path / "sessions.db"
    repository = SessionRepository(database_path)
    auth = AuthService(database_path)
    user = auth.create_user("engineer", "secret-123", Role.ENGINEER, bootstrap=True)
    session_id = repository.start_session(parameters={}, workpiece="签名测试")

    signature = auth.sign_report(
        session_id=session_id,
        report_format="pdf",
        report_path=tmp_path / "report.pdf",
        sha256="a" * 64,
        user_id=user.id,
    )

    reports = repository.list_reports(session_id)
    assert signature.signed_by == user.id
    assert reports[0]["sha256"] == "a" * 64
    assert reports[0]["signed_by"] == user.id
    assert reports[0]["signature"]


def test_login_dialog_bootstraps_first_admin(tmp_path, qapp) -> None:
    service = AuthService(tmp_path / "auth.db")
    dialog = LoginDialog(service)
    dialog.username_edit.setText("admin")
    dialog.password_edit.setText("secret-123")

    dialog.submit_credentials()

    assert dialog.authenticated_user is not None
    assert dialog.authenticated_user.role == Role.ADMIN


def test_audit_dialog_displays_and_verifies_chain(tmp_path, qapp) -> None:
    service = AuthService(tmp_path / "auth.db")
    admin = service.create_user("admin", "secret-123", Role.ADMIN, bootstrap=True)
    service.record_audit(admin.id, "session.start", "session", "s1", {})
    dialog = AuditDialog(service)

    dialog.reload_events()
    dialog.verify_chain()

    assert dialog.table.rowCount() == 1
    assert "通过" in dialog.verification_label.text()


def test_viewer_cannot_start_acquisition(tmp_path, qapp) -> None:
    window = MainWindow()
    controller = MainController(
        UltrasonicSignalModel(),
        window,
        data_dir=tmp_path,
        use_worker=False,
        current_user=User(1, "viewer", Role.VIEWER),
    )

    controller.startAcquisition()

    assert not controller._isAcquisitionRunning()
    window.close()
