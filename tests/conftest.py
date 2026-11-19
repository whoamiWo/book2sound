from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import simple_book  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Isolated SOUNDBOOK_HOME / CACHE so tests never touch the real cache."""

    monkeypatch.setenv("SOUNDBOOK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SOUNDBOOK_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path


@pytest.fixture()
def book_path(home):
    return simple_book(home / "book.epub")
