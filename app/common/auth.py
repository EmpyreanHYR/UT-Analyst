"""Local authentication, role checks, audit chain, and report signatures."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from app.model.session_repository import SessionRepository


class Role(str, Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"
    OPERATOR = "operator"
    VIEWER = "viewer"


class AccountLockedError(RuntimeError):
    """Raised when an account is temporarily locked."""


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: Role
    disabled: bool = False


@dataclass(frozen=True)
class ReportSignature:
    signed_by: int
    signed_at: str
    signature: str


PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {
        "view",
        "acquire",
        "configure",
        "edit_report",
        "delete_records",
        "manage_users",
        "view_audit",
    },
    Role.ENGINEER: {
        "view",
        "acquire",
        "configure",
        "edit_report",
        "delete_records",
        "view_audit",
    },
    Role.OPERATOR: {
        "view",
        "acquire",
        "edit_report",
    },
    Role.VIEWER: {
        "view",
    },
}


def has_permission(role: Role | str, permission: str) -> bool:
    """Return whether a role has a permission."""
    normalized = role if isinstance(role, Role) else Role(str(role))
    return permission in PERMISSIONS[normalized]


class AuthService:
    """Manage local users and append-only hash-chained audit events."""

    def __init__(
        self,
        database_path: str | Path,
        max_failed_attempts: int = 5,
        lockout_seconds: int = 300,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_failed_attempts = max(1, int(max_failed_attempts))
        self.lockout_seconds = max(1, int(lockout_seconds))
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(self.database_path),
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );
                """
            )

    def get_user_count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return int(row["count"])

    def create_user(
        self,
        username: str,
        password: str,
        role: Role,
        bootstrap: bool = False,
    ) -> User:
        normalized_username = username.strip()
        if not normalized_username:
            raise ValueError("用户名不能为空")
        if len(password) < 8:
            raise ValueError("密码长度不能少于8位")
        if not bootstrap and self.get_user_count() == 0:
            raise ValueError("首个用户必须通过初始化流程创建")

        salt = os.urandom(16)
        password_hash = self._hash_password(password, salt)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO users(
                    username, password_hash, salt, role, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    normalized_username,
                    password_hash.hex(),
                    salt.hex(),
                    role.value,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        return User(int(cursor.lastrowid), normalized_username, role)

    @staticmethod
    def _hash_password(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            200_000,
        )

    def authenticate(self, username: str, password: str) -> User:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
        if row is None:
            raise ValueError("用户名或密码错误")

        locked_until = self._parse_datetime(row["locked_until"])
        if locked_until and locked_until > datetime.now():
            raise AccountLockedError(
                f"账户已锁定至 {locked_until.isoformat(timespec='seconds')}"
            )

        expected = bytes.fromhex(row["password_hash"])
        actual = self._hash_password(password, bytes.fromhex(row["salt"]))
        if not hmac.compare_digest(actual, expected):
            failed_attempts = int(row["failed_attempts"]) + 1
            locked_until_value = None
            if failed_attempts >= self.max_failed_attempts:
                locked_until_value = (
                    datetime.now() + timedelta(seconds=self.lockout_seconds)
                ).isoformat(timespec="seconds")
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    UPDATE users
                    SET failed_attempts = ?, locked_until = ?
                    WHERE id = ?
                    """,
                    (failed_attempts, locked_until_value, row["id"]),
                )
            if locked_until_value:
                raise AccountLockedError(
                    f"账户已锁定至 {locked_until_value}"
                )
            raise ValueError("用户名或密码错误")

        if bool(row["disabled"]):
            raise AccountLockedError("账户已禁用")

        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE users
                SET failed_attempts = 0, locked_until = NULL
                WHERE id = ?
                """,
                (row["id"],),
            )
        return User(
            id=int(row["id"]),
            username=str(row["username"]),
            role=Role(str(row["role"])),
            disabled=bool(row["disabled"]),
        )

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    def record_audit(
        self,
        user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: str,
        details: dict[str, Any] | None = None,
    ) -> str:
        details_json = json.dumps(
            details or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        created_at = datetime.now().isoformat(timespec="milliseconds")
        with self._lock, self._connection:
            previous_row = self._connection.execute(
                "SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
            previous_hash = str(previous_row["event_hash"]) if previous_row else ""
            event_hash = self._calculate_event_hash(
                created_at=created_at,
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details_json=details_json,
                previous_hash=previous_hash,
            )
            self._connection.execute(
                """
                INSERT INTO audit_events(
                    created_at, user_id, action, entity_type, entity_id,
                    details_json, previous_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    user_id,
                    action,
                    entity_type,
                    entity_id,
                    details_json,
                    previous_hash,
                    event_hash,
                ),
            )
        return event_hash

    @staticmethod
    def _calculate_event_hash(**values: Any) -> str:
        payload = json.dumps(
            values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_audit_chain(self) -> bool:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM audit_events ORDER BY id"
            ).fetchall()
        previous_hash = ""
        for row in rows:
            if str(row["previous_hash"]) != previous_hash:
                return False
            expected_hash = self._calculate_event_hash(
                created_at=str(row["created_at"]),
                user_id=row["user_id"],
                action=str(row["action"]),
                entity_type=str(row["entity_type"]),
                entity_id=str(row["entity_id"]),
                details_json=str(row["details_json"]),
                previous_hash=previous_hash,
            )
            if not hmac.compare_digest(expected_hash, str(row["event_hash"])):
                return False
            previous_hash = expected_hash
        return True

    def list_audit_events(self, limit: int = 200) -> list[dict[str, Any]]:
        """Return recent audit events in reverse chronological order."""
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, created_at, user_id, action, entity_type,
                       entity_id, details_json, event_hash
                FROM audit_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def sign_report(
        self,
        session_id: str,
        report_format: str,
        report_path: str | Path,
        sha256: str,
        user_id: int,
    ) -> ReportSignature:
        signed_at = datetime.now().isoformat(timespec="seconds")
        payload = {
            "session_id": session_id,
            "format": report_format,
            "path": str(report_path),
            "sha256": sha256,
            "signed_by": int(user_id),
            "signed_at": signed_at,
        }
        signature = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        repository = SessionRepository(self.database_path)
        try:
            repository.add_report(
                session_id=session_id,
                report_format=report_format,
                path=report_path,
                sha256=sha256,
                signed_by=user_id,
                signed_at=signed_at,
                signature=signature,
            )
        finally:
            repository.close()
        self.record_audit(
            user_id,
            "report.sign",
            "report",
            str(report_path),
            {"session_id": session_id, "format": report_format, "sha256": sha256},
        )
        return ReportSignature(int(user_id), signed_at, signature)

    def close(self) -> None:
        with self._lock:
            self._connection.close()
