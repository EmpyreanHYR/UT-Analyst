"""Shared pytest fixtures for headless Qt tests."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Create one QApplication for all UI tests."""
    application = QApplication.instance() or QApplication([])
    yield application
