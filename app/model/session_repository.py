"""SQLite session metadata and chunked waveform persistence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import numpy as np


SCHEMA_VERSION = 2


class SessionRepository:
    """Store detection sessions, defect records, chunk indexes, and reports."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(self.database_path),
            check_same_thread=False,
        )
        self._closed = False
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)"
            )
            row = self._connection.execute(
                "SELECT version FROM schema_version LIMIT 1"
            ).fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO schema_version(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) == 1:
                self._migrate_v1_to_v2()
                self._connection.execute(
                    "UPDATE schema_version SET version = ?",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError(
                    f"数据库版本不兼容: {row['version']} != {SCHEMA_VERSION}"
                )

            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS detection_sessions(
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    workpiece TEXT NOT NULL DEFAULT '',
                    standard_key TEXT NOT NULL DEFAULT '通用',
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    decision TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS defects(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    record_uid INTEGER NOT NULL,
                    depth_mm REAL NOT NULL,
                    amplitude REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    snapshot_uri TEXT NOT NULL DEFAULT '',
                    UNIQUE(session_id, record_uid),
                    FOREIGN KEY(session_id) REFERENCES detection_sessions(id)
                );
                CREATE TABLE IF NOT EXISTS frame_chunks(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    start_sequence INTEGER NOT NULL,
                    end_sequence INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, chunk_index),
                    FOREIGN KEY(session_id) REFERENCES detection_sessions(id)
                );
                CREATE TABLE IF NOT EXISTS reports(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    format TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    signed_by INTEGER,
                    signed_at TEXT,
                    signature TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES detection_sessions(id)
                );
                """
            )

    def _migrate_v1_to_v2(self) -> None:
        columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(reports)").fetchall()
        }
        if "signed_by" not in columns:
            self._connection.execute("ALTER TABLE reports ADD COLUMN signed_by INTEGER")
        if "signed_at" not in columns:
            self._connection.execute("ALTER TABLE reports ADD COLUMN signed_at TEXT")
        if "signature" not in columns:
            self._connection.execute("ALTER TABLE reports ADD COLUMN signature TEXT")

    def start_session(
        self,
        parameters: dict[str, Any],
        workpiece: str = "",
        standard_key: str = "通用",
    ) -> str:
        session_id = uuid4().hex
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO detection_sessions(
                    id, started_at, workpiece, standard_key, parameters_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    now,
                    workpiece,
                    standard_key,
                    json.dumps(parameters, ensure_ascii=False),
                    now,
                ),
            )
        return session_id

    def finish_session(self, session_id: str, decision: str | None = None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE detection_sessions
                SET ended_at = ?, decision = COALESCE(?, decision)
                WHERE id = ?
                """,
                (datetime.now().isoformat(timespec="seconds"), decision, session_id),
            )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM detection_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM detection_sessions
                ORDER BY started_at DESC, created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def add_defect(
        self,
        session_id: str,
        record_uid: int,
        depth_mm: float,
        amplitude: float,
        timestamp: str,
        snapshot_uri: str = "",
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO defects(
                    session_id, record_uid, depth_mm, amplitude, timestamp, snapshot_uri
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    int(record_uid),
                    float(depth_mm),
                    float(amplitude),
                    timestamp,
                    snapshot_uri,
                ),
            )

    def list_defects(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM defects
                WHERE session_id = ?
                ORDER BY record_uid
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_frame_chunk(
        self,
        session_id: str,
        chunk_index: int,
        start_sequence: int,
        end_sequence: int,
        path: str | Path,
        checksum: str,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO frame_chunks(
                    session_id, chunk_index, start_sequence, end_sequence,
                    path, checksum, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    int(chunk_index),
                    int(start_sequence),
                    int(end_sequence),
                    str(path),
                    checksum,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def list_frame_chunks(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM frame_chunks
                WHERE session_id = ?
                ORDER BY chunk_index
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def iter_frames(
        self,
        session_id: str,
        store: "FrameChunkStore",
    ) -> Iterator[dict[str, Any]]:
        for chunk in self.list_frame_chunks(session_id):
            yield from store.load_chunk(chunk["path"], chunk["checksum"])

    def add_report(
        self,
        session_id: str,
        report_format: str,
        path: str | Path,
        sha256: str,
        signed_by: int | None = None,
        signed_at: str | None = None,
        signature: str | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO reports(
                    session_id, format, path, sha256,
                    signed_by, signed_at, signature, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    report_format,
                    str(path),
                    sha256,
                    signed_by,
                    signed_at,
                    signature,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def list_reports(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM reports
                WHERE session_id = ?
                ORDER BY id
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True


class FrameChunkStore:
    """Buffer frames and persist them into compressed NPZ chunks."""

    def __init__(
        self,
        root_dir: str | Path,
        repository: SessionRepository,
        chunk_size: int = 100,
    ) -> None:
        if int(chunk_size) < 1:
            raise ValueError("chunk_size必须大于等于1")
        self.root_dir = Path(root_dir)
        self.repository = repository
        self.chunk_size = int(chunk_size)
        self._buffers: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def append_frame(
        self,
        session_id: str,
        sequence_id: int,
        time_axis_us: np.ndarray,
        raw_signal: np.ndarray,
        envelope_signal: np.ndarray,
        metadata: dict[str, Any],
    ) -> None:
        frame = {
            "sequence_id": int(sequence_id),
            "time_axis_us": np.asarray(time_axis_us, dtype=np.float32),
            "raw_signal": np.asarray(raw_signal, dtype=np.float32),
            "envelope_signal": np.asarray(envelope_signal, dtype=np.float32),
            "metadata": dict(metadata),
        }
        lengths = {
            frame["time_axis_us"].size,
            frame["raw_signal"].size,
            frame["envelope_signal"].size,
        }
        if len(lengths) != 1:
            raise ValueError("时间轴、原始波形和包络长度必须一致")

        with self._lock:
            buffer = self._buffers.setdefault(session_id, [])
            buffer.append(frame)
            if len(buffer) >= self.chunk_size:
                self._flush_locked(session_id)

    def flush_session(self, session_id: str) -> None:
        with self._lock:
            self._flush_locked(session_id)

    def _flush_locked(self, session_id: str) -> None:
        buffer = self._buffers.get(session_id, [])
        if not buffer:
            return

        session_dir = self.root_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        chunk_index = len(self.repository.list_frame_chunks(session_id))
        chunk_path = session_dir / f"frames_{chunk_index:06d}.npz"

        np.savez_compressed(
            chunk_path,
            sequence_ids=np.asarray([frame["sequence_id"] for frame in buffer], dtype=np.int64),
            time_axis_us=np.stack([frame["time_axis_us"] for frame in buffer]),
            raw_signals=np.stack([frame["raw_signal"] for frame in buffer]),
            envelope_signals=np.stack([frame["envelope_signal"] for frame in buffer]),
            metadata_json=np.asarray(
                [json.dumps(frame["metadata"], ensure_ascii=False) for frame in buffer]
            ),
        )
        checksum = hashlib.sha256(chunk_path.read_bytes()).hexdigest()
        self.repository.add_frame_chunk(
            session_id=session_id,
            chunk_index=chunk_index,
            start_sequence=buffer[0]["sequence_id"],
            end_sequence=buffer[-1]["sequence_id"],
            path=chunk_path,
            checksum=checksum,
        )
        buffer.clear()

    @staticmethod
    def load_chunk(path: str | Path, expected_checksum: str = "") -> list[dict[str, Any]]:
        chunk_path = Path(path)
        if not chunk_path.exists():
            raise FileNotFoundError(f"波形分块不存在: {chunk_path}")
        actual_checksum = hashlib.sha256(chunk_path.read_bytes()).hexdigest()
        if expected_checksum and actual_checksum != expected_checksum:
            raise ValueError(f"波形分块校验失败: {chunk_path}")

        with np.load(chunk_path, allow_pickle=False) as data:
            sequence_ids = data["sequence_ids"]
            time_axes = data["time_axis_us"]
            raw_signals = data["raw_signals"]
            envelope_signals = data["envelope_signals"]
            metadata = data["metadata_json"]

            frames = []
            for index, sequence_id in enumerate(sequence_ids):
                frames.append(
                    {
                        "sequence_id": int(sequence_id),
                        "time_axis_us": time_axes[index],
                        "raw_signal": raw_signals[index],
                        "envelope_signal": envelope_signals[index],
                        "metadata": json.loads(str(metadata[index])),
                    }
                )
        return frames
