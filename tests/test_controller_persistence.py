"""Controller integration tests for session persistence."""

from __future__ import annotations

from app.controller.main_controller import MainController
from app.model.session_repository import FrameChunkStore, SessionRepository
from app.model.ultrasonic_model import UltrasonicSignalModel
from app.view.main_window import MainWindow


def test_single_shot_persists_session_and_replay_frames(tmp_path, qapp) -> None:
    repository = SessionRepository(tmp_path / "sessions.db")
    store = FrameChunkStore(tmp_path / "session-data", repository, chunk_size=2)
    window = MainWindow()
    controller = MainController(
        UltrasonicSignalModel(),
        window,
        session_repository=repository,
        frame_chunk_store=store,
    )

    controller.singleShotAcquisition()

    sessions = repository.list_sessions()
    assert len(sessions) == 1
    frames = list(repository.iter_frames(sessions[0]["id"], store))
    assert len(frames) == 1

    controller.loadReplaySession(sessions[0]["id"])
    assert controller.replayFrames
    controller.loadReplayFrame(0)
    assert controller.lastFrameData is not None
    controller.shutdown()
    repository.database_path.unlink()
