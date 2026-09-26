"""Replay panel behavior tests."""

from __future__ import annotations

from app.view.replay_panel import ReplayPanel


def test_replay_panel_lists_sessions_and_emits_selection(qapp) -> None:
    panel = ReplayPanel()
    selected: list[str] = []
    panel.sessionSelected.connect(selected.append)

    panel.set_sessions(
        [
            {"id": "session-a", "workpiece": "工件-A", "started_at": "2026-09-26T12:00:00"},
            {"id": "session-b", "workpiece": "工件-B", "started_at": "2026-09-26T13:00:00"},
        ]
    )
    panel.session_combo.setCurrentIndex(1)

    assert selected[-1] == "session-b"


def test_replay_panel_clamps_frame_range_and_emits_frame(qapp) -> None:
    panel = ReplayPanel()
    frames: list[int] = []
    panel.frameChanged.connect(frames.append)

    panel.set_frame_count(5)
    panel.frame_slider.setValue(3)

    assert frames[-1] == 3
    assert panel.frame_label.text() == "4 / 5"
