from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from helpers import Chapter, make_epub

pytestmark = pytest.mark.e2e

need_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                 reason="ffmpeg not installed")

PARAGRAPH = ("风雪压在松枝上，山道上没有一个人影。他独自走着，"
             "心里却异常安静，仿佛整个世界都在为他让路。")


def _book(path: Path, n: int = 40) -> Path:
    chapters = [
        Chapter(f"第{i + 1}章 远行", [f"{PARAGRAPH}{i}", PARAGRAPH, f"{PARAGRAPH}·{i}"])
        for i in range(n)
    ]
    return make_epub(path, chapters)


def _env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["SOUNDBOOK_HOME"] = str(home / "home")
    env["SOUNDBOOK_CACHE_DIR"] = str(home / "cache")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _cli_cmd() -> list[str]:
    return [sys.executable, "-m", "soundbook"]


def _counts(db_file: Path) -> dict[str, int]:
    if not db_file.exists():
        return {}
    db = sqlite3.connect(db_file)
    rows = db.execute("SELECT status, COUNT(*) FROM segments GROUP BY status").fetchall()
    db.close()
    return dict(rows)


@need_ffmpeg
def test_hard_kill_then_resume(tmp_path):
    book = _book(tmp_path / "big.epub", n=40)
    out = tmp_path / "big.m4b"
    db_file = tmp_path / "home" / "state.sqlite"

    proc = subprocess.Popen(
        _cli_cmd() + ["run", str(book), "--tts", "fake", "--jobs", "2",
                      "-o", str(out)],
        env=_env(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True)
    deadline = time.time() + 20
    while time.time() < deadline:
        if db_file.exists():
            try:
                if _counts(db_file).get("done", 0) >= 3:
                    break
            except sqlite3.OperationalError:
                pass
        time.sleep(0.05)
    proc.kill()  # SIGKILL: no cleanup, no commit of the in-flight row
    proc.wait(timeout=10)

    done_before = _counts(db_file).get("done", 0)
    assert done_before > 0, "the run never got far enough to test resumption"

    resumed = subprocess.run(
        _cli_cmd() + ["run", str(book), "--tts", "fake", "--jobs", "2",
                      "-o", str(out)],
        env=_env(tmp_path), capture_output=True, text=True, timeout=120)
    assert resumed.returncode == 0, resumed.stderr[-3000:]
    assert "synth:" in resumed.stderr
    # segments finished before the kill were reused, not redone
    assert "0 cached" not in resumed.stderr
    assert out.is_file()

    again = subprocess.run(
        _cli_cmd() + ["run", str(book), "--tts", "fake", "-o", str(out)],
        env=_env(tmp_path), capture_output=True, text=True, timeout=120)
    assert again.returncode == 0, again.stderr[-3000:]
    assert "up to date" in again.stdout
