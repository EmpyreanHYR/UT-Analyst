"""Phase 2 persistence and replay foundation tests."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from app.model.session_repository import FrameChunkStore, SessionRepository


def test_session_roundtrip_and_defect_records(tmp_path) -> None:
    repository = SessionRepository(tmp_path / "sessions.db")
    session_id = repository.start_session(
        parameters={"samplingRateHz": 20_000_000.0},
        workpiece="工件-测试",
    )
    repository.add_defect(
        session_id=session_id,
        record_uid=1,
        depth_mm=42.5,
        amplitude=0.81,
        timestamp="2026-09-26T12:00:00",
        snapshot_uri="data:image/png;base64,abc",
    )
    repository.finish_session(session_id, decision="不合格")

    session = repository.get_session(session_id)
    defects = repository.list_defects(session_id)

    assert session is not None
    assert session["workpiece"] == "工件-测试"
    assert session["decision"] == "不合格"
    assert defects[0]["depth_mm"] == pytest.approx(42.5)


def test_frame_chunks_roundtrip_and_checksum(tmp_path) -> None:
    repository = SessionRepository(tmp_path / "sessions.db")
    store = FrameChunkStore(tmp_path / "session-data", repository, chunk_size=2)
    session_id = repository.start_session(parameters={}, workpiece="分块测试")

    for index in range(3):
        store.append_frame(
            session_id=session_id,
            sequence_id=index,
            time_axis_us=np.array([0.0, 1.0, 2.0], dtype=np.float32),
            raw_signal=np.array([index, index + 1, index + 2], dtype=np.float32),
            envelope_signal=np.array([index + 0.5, index + 1.5, index + 2.5], dtype=np.float32),
            metadata={"sample_rate_hz": 20_000_000.0},
        )
    store.flush_session(session_id)

    frames = list(repository.iter_frames(session_id, store))

    assert len(frames) == 3
    assert frames[2]["sequence_id"] == 2
    assert frames[1]["raw_signal"].tolist() == [1.0, 2.0, 3.0]

    chunk = repository.list_frame_chunks(session_id)[0]
    content = (tmp_path / "session-data" / session_id / "frames_000000.npz").read_bytes()
    assert chunk["checksum"] == hashlib.sha256(content).hexdigest()


def test_missing_chunk_raises_clear_error(tmp_path) -> None:
    repository = SessionRepository(tmp_path / "sessions.db")
    store = FrameChunkStore(tmp_path / "session-data", repository, chunk_size=1)
    session_id = repository.start_session(parameters={})
    store.append_frame(
        session_id=session_id,
        sequence_id=0,
        time_axis_us=np.array([0.0, 1.0], dtype=np.float32),
        raw_signal=np.array([1.0, 2.0], dtype=np.float32),
        envelope_signal=np.array([1.0, 2.0], dtype=np.float32),
        metadata={},
    )
    store.flush_session(session_id)
    chunk = repository.list_frame_chunks(session_id)[0]
    (tmp_path / "session-data" / session_id / "frames_000000.npz").unlink()

    with pytest.raises(FileNotFoundError, match="波形分块不存在"):
        list(repository.iter_frames(session_id, store))

    assert chunk["path"].endswith("frames_000000.npz")
