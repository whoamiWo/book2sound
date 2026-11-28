from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner

from soundbook.cli import cli

pytestmark = pytest.mark.e2e

need_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                 reason="ffmpeg not installed")


def _invoke(args, home):
    runner = CliRunner()
    return runner.invoke(cli, args,
                         env={"SOUNDBOOK_HOME": str(home / "home"),
                              "SOUNDBOOK_CACHE_DIR": str(home / "cache")},
                         catch_exceptions=False)


@need_ffmpeg
def test_run_fake_end_to_end(book_path, home):
    out = home / "book.m4b"
    result = _invoke(["run", str(book_path), "--tts", "fake", "-o", str(out)], home)
    assert result.exit_code == 0, result.output
    assert out.is_file() and out.stat().st_size > 1000
    assert "wrote" in result.output

    # chapters: 5 non-skippable chapters (none flagged — equal-length chapters)
    from soundbook.assemble.m4b import probe_chapters

    chapters = probe_chapters(out)
    assert len(chapters) == 5
    assert all(c["tags"]["title"] for c in chapters)


@need_ffmpeg
def test_chapter_starts_match_timeline(book_path, home):

    from soundbook.assemble.concat import build_timeline
    from soundbook.assemble.m4b import verify_output
    from soundbook.config import db_path
    from soundbook.db import connect

    out = home / "book.m4b"
    result = _invoke(["run", str(book_path), "--tts", "fake", "-o", str(out)], home)
    assert result.exit_code == 0, result.output

    from soundbook.util.hashing import sha256_file

    db = connect(db_path())
    book_id = sha256_file(book_path)
    timeline = build_timeline(db, book_id, str(home / "work2"))
    problems = verify_output(out, timeline.spans, tolerance_ms=150)
    assert problems == []
    db.close()


@need_ffmpeg
def test_rerun_is_fully_cached_and_voice_switch_resynthesizes(book_path, home):
    out = home / "book.m4b"
    first = _invoke(["run", str(book_path), "--tts", "fake", "-o", str(out)], home)
    assert first.exit_code == 0, first.output

    second = _invoke(["run", str(book_path), "--tts", "fake", "-o", str(out)], home)
    assert second.exit_code == 0, second.output
    assert "synth:" not in second.output
    assert "up to date" in second.output

    # a different voice invalidates every segment; identical texts across
    # chapters still hit the cache, so this is "some new, some cached"
    third = _invoke(["run", str(book_path), "--tts", "fake",
                     "--voice", "other", "-o", str(out)], home)
    assert third.exit_code == 0, third.output
    assert "synth:" in third.output
    assert "0 new" not in third.output
    assert "wrote" in third.output

    # switching back hits the audio cache — zero synthesis; the file is
    # reassembled once because the previous run overwrote it
    fourth = _invoke(["run", str(book_path), "--tts", "fake", "-o", str(out)], home)
    assert fourth.exit_code == 0, fourth.output
    assert "0 new" in fourth.output
    assert "wrote" in fourth.output

    # fifth run: everything matches, nothing to do
    fifth = _invoke(["run", str(book_path), "--tts", "fake", "-o", str(out)], home)
    assert fifth.exit_code == 0, fifth.output
    assert "synth:" not in fifth.output
    assert "up to date" in fifth.output


@need_ffmpeg
def test_inspect_json(book_path, home):
    import json

    result = _invoke(["inspect", str(book_path), "--json"], home)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["strategy"] == "nav"
    assert payload["n_chapters"] == 5
    assert payload["n_segments"] > 5


def test_doctor_never_fails_on_missing_inputs(home):
    result = _invoke(["doctor"], home)
    assert result.exit_code in (0, 1)


@need_ffmpeg
def test_inspect_does_not_downgrade_finished_status(book_path, home):
    """After a successful run, `inspect` must not flip the book back to `ready`."""

    out = home / "book.m4b"
    result = _invoke(["run", str(book_path), "--tts", "fake", "-o", str(out)], home)
    assert result.exit_code == 0, result.output

    from soundbook.db import connect

    db = connect(home / "home" / "state.sqlite")
    status_row = db.execute("SELECT status FROM books").fetchone()
    assert status_row["status"] == "done"
    db.close()

    inspected = _invoke(["inspect", str(book_path)], home)
    assert inspected.exit_code == 0, inspected.output

    db = connect(home / "home" / "state.sqlite")
    status_row = db.execute("SELECT status FROM books").fetchone()
    assert status_row["status"] == "done"
    db.close()


@need_ffmpeg
def test_second_run_on_a_locked_book_exits_1(book_path, home):
    """Book-level mutual exclusion must fail fast and clearly, not crash."""

    from filelock import FileLock

    from soundbook.util.hashing import sha256_file

    locks = home / "home" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(locks / f"{sha256_file(book_path)}.lock"))
    lock.acquire(timeout=0)
    try:
        result = _invoke(
            ["run", str(book_path), "--tts", "fake", "-o", str(home / "x.m4b")],
            home)
    finally:
        lock.release()
    assert result.exit_code == 1, result.output
    assert "already working on this book" in result.output


@need_ffmpeg
@pytest.mark.parametrize("option", [
    "--rate=0", "--rate=-1", "--jobs=0", "--max-retries=0",
])
def test_invalid_numeric_options_exit_1(book_path, home, option):
    result = _invoke(
        ["run", str(book_path), "--tts", "fake", option, "-o", str(home / "x.m4b")],
        home)
    assert result.exit_code == 1, result.output
    assert "epub2m4b:" in result.output


@need_ffmpeg
def test_loudnorm_on_silence_is_skipped_with_warning(book_path, home):
    """Plan §3.1: two-pass loudnorm on silence must degrade, not crash."""

    from soundbook import config
    from soundbook.config import Policies
    from soundbook.db import connect
    from soundbook.pipeline import build_artifact, prepare, synthesize
    from soundbook.tts.base import synth_fingerprint_for
    from soundbook.tts.fake import FakeBackend

    config.ensure_dirs()
    policies = Policies()
    tts = FakeBackend()
    fp = synth_fingerprint_for(tts.info(), tts.config)
    db = connect(config.db_path())
    prepared = prepare(db, book_path, policies, write_segments=True, synth_fp=fp)
    report = synthesize(db, prepared.book.info.book_id,
                        backend_factory=FakeBackend, synth_fp=fp)
    assert report.failed == []
    result = build_artifact(db, prepared.book, policies=policies,
                            output=home / "loud.m4b", allow_loudnorm=True)
    assert result.loudnorm_used is False
    assert any("silent" in w for w in result.warnings)
    db.close()
