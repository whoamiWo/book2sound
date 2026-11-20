"""``epub2m4b`` command line (spec §11).

Exit codes: 0 success · 1 general error · 2 failed/incomplete segments ·
3 input unusable · 4 TTS unavailable · 5 insufficient disk · 130 interrupted.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import click
from filelock import FileLock

from soundbook import DIST_NAME, PIPELINE_VERSION, __version__
from soundbook import config
from soundbook.config import AudioPolicy, Policies, SegmentPolicy, TTSConfig
from soundbook.db import (
    book_complete,
    connect,
    done_segments,
    failed_segments,
    get_artifact,
    get_chapters,
    segment_counts,
    set_book_meta,
)
from soundbook.ingest.loader import UnusableBook, load_book
from soundbook.pipeline import (
    all_done,
    build_artifact,
    content_signature,
    prepare,
    synthesize,
    verify_cached_segments,
)
from soundbook.tts.base import synth_fingerprint_for
from soundbook.util.disk import InsufficientSpace

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_SEGMENTS = 2
EXIT_INPUT = 3
EXIT_TTS = 4
EXIT_DISK = 5


def _policies(bitrate: str | None, loudnorm: bool, speak_titles: bool) -> Policies:
    audio = AudioPolicy(bitrate=bitrate) if bitrate else AudioPolicy()
    audio = AudioPolicy(
        bitrate=audio.bitrate, loudnorm=loudnorm, sample_rate=audio.sample_rate,
        channels=audio.channels, loudnorm_i=audio.loudnorm_i, loudnorm_tp=audio.loudnorm_tp,
        loudnorm_lra=audio.loudnorm_lra, aac_profile=audio.aac_profile,
        language=audio.language, faststart=audio.faststart,
    )
    segment = SegmentPolicy(speak_titles=speak_titles)
    return Policies(audio=audio, segment=segment)


def _fail(message: str, code: int) -> None:
    click.echo(f"{DIST_NAME}: {message}", err=True)
    raise SystemExit(code)


def _artifact_is_fresh(artifact, sig: str, policies: Policies,
                       cover_sha256: str | None) -> bool:
    """True when the existing M4B was built with exactly these options."""

    if artifact is None:
        return False
    opts = json.loads(artifact["build_opts"])
    audio = policies.audio
    return (
        opts.get("content_sig") == sig
        and opts.get("bitrate") == audio.bitrate
        and opts.get("sample_rate") == audio.sample_rate
        and opts.get("channels") == audio.channels
        and opts.get("loudnorm") == audio.loudnorm
        and opts.get("loudnorm_i") == audio.loudnorm_i
        and opts.get("loudnorm_tp") == audio.loudnorm_tp
        and opts.get("loudnorm_lra") == audio.loudnorm_lra
        and opts.get("cover_sha256") == cover_sha256
    )


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name=DIST_NAME)
def cli() -> None:
    """Turn a Chinese EPUB into a chaptered M4B audiobook."""


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def _doctor_report() -> tuple[list[str], list[str]]:
    ok: list[str] = []
    bad: list[str] = []
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if not path:
            bad.append(f"{tool}: not found on PATH")
            continue
        try:
            from soundbook.util.process import run

            version = run([tool, "-version"]).stdout_text.splitlines()[0]
            ok.append(f"{tool}: {version}")
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{tool}: found at {path} but not runnable ({exc})")

    home = config.home_dir()
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        ok.append(f"home: {home} writable")
    except OSError as exc:
        bad.append(f"home: {home} not writable ({exc})")

    cache = config.cache_dir()
    try:
        cache.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(cache).free
        ok.append(f"cache: {cache} ({free / 1e9:.1f} GB free)")
        if free < 512 * 1024 * 1024:
            bad.append(f"cache: only {free / 1e6:.0f} MB free, need at least 512 MB")
    except OSError as exc:
        bad.append(f"cache: {cache} unavailable ({exc})")

    try:
        import lxml  # noqa: F401
        import epubx  # noqa: F401

        ok.append(f"epubx: {epubx.__version__}")
    except Exception as exc:  # noqa: BLE001
        bad.append(f"epubx: import failed ({exc})")
    return ok, bad


@cli.command()
def doctor() -> None:
    """Check ffmpeg, writable home and free space. Never writes the database."""

    ok, bad = _doctor_report()
    for line in ok:
        click.echo(f"  ok   {line}")
    for line in bad:
        click.echo(f"  FAIL {line}", err=True)
    if bad:
        raise SystemExit(EXIT_ERROR)
    click.echo(f"{DIST_NAME} {__version__} (pipeline {PIPELINE_VERSION}) looks usable")


# --------------------------------------------------------------------------
# inspect
# --------------------------------------------------------------------------


@cli.command()
@click.argument("book", type=click.Path(exists=True, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, help="machine-readable output")
@click.option("--include-front-matter", is_flag=True,
              help="count skippable front/back matter as chapters")
def inspect(book: str, as_json: bool, include_front_matter: bool) -> None:
    """Parse a book, choose a chaptering strategy and record it. No synthesis."""

    config.ensure_dirs()
    policies = Policies()
    db = connect(config.db_path())
    try:
        prepared = prepare(db, book, policies,
                           include_skippable=include_front_matter,
                           write_segments=False)
    except UnusableBook as exc:
        _fail(f"cannot use {book}: {exc}", EXIT_INPUT)
        return

    info = prepared.book.info
    chapters = prepared.chapters
    skippable = sum(1 for c in chapters if c.draft.skippable)
    payload = {
        "book_id": info.book_id,
        "path": info.path,
        "title": info.title,
        "language": info.language,
        "n_spine": info.n_spine,
        "n_toc": info.n_toc,
        "strategy": prepared.strategy,
        "n_chapters": len(chapters),
        "skippable_chapters": skippable,
        "total_chars": sum(c.draft.char_count for c in chapters),
        "n_segments": prepared.n_segments,
        "obfuscated_fonts": list(info.obfuscated_fonts),
        "cover_sha256": info.cover_sha256,
        "chapters": [
            {
                "idx": c.draft.idx,
                "title": c.draft.title,
                "chars": c.draft.char_count,
                "segments": len(c.segments),
                "skippable": c.draft.skippable,
                "start_key": c.draft.start_key,
                "end_key": c.draft.end_key,
                "rejected": [r.as_dict() for r in c.draft.rejected],
                "warnings": c.warnings,
            }
            for c in chapters
        ],
    }
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(f"{info.title}  ({info.language or 'unknown language'})")
    click.echo(f"  book_id     {info.book_id[:16]}…")
    click.echo(f"  spine       {info.n_spine} documents, {info.n_toc} toc entries")
    click.echo(f"  strategy    {prepared.strategy}")
    click.echo(f"  chapters    {len(chapters)} ({skippable} skippable), "
               f"{payload['total_chars']} chars")
    click.echo(f"  segments    {payload['n_segments']} (estimated)")
    if info.obfuscated_fonts:
        click.echo(f"  note        {len(info.obfuscated_fonts)} obfuscated font(s); text readable")
    if info.cover_sha256:
        click.echo(f"  cover       {info.cover_sha256[:16]}…")
    # anchor_* records are degraded cuts, not a vetoed strategy: report separately.
    rejected = {r.reason for c in chapters for r in c.draft.rejected
                if not r.reason.startswith("anchor_")}
    if rejected:
        click.echo(f"  rejected    {', '.join(sorted(rejected))}")
    chapter_warnings = [(c.draft.idx, w) for c in chapters for w in c.warnings]
    if chapter_warnings:
        click.echo(f"  warnings    {len(chapter_warnings)}")
        for idx, text in chapter_warnings[:5]:
            click.echo(f"    [{idx:>3}] {text}")
        if len(chapter_warnings) > 5:
            click.echo(f"    … {len(chapter_warnings) - 5} more")
    for c in chapters[:5]:
        click.echo(f"    [{c.draft.idx:>3}] {c.draft.title[:40]:<40} "
                   f"{c.draft.char_count:>7} chars  {len(c.segments):>4} segs")
    if len(chapters) > 5:
        click.echo(f"    … {len(chapters) - 5} more")


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


@cli.command()
@click.argument("book", required=False, type=click.Path(dir_okay=False))
def status(book: str | None) -> None:
    """Show the state of one book, or of the whole library."""

    config.ensure_dirs()
    db = connect(config.db_path())
    if book:
        from soundbook.util.hashing import sha256_file

        book_id = sha256_file(Path(book).expanduser())
        row = db.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
        if row is None:
            _fail(f"not in the database yet: {book}", EXIT_ERROR)
            return
        counts = segment_counts(db, book_id)
        click.echo(f"{row['title']}  [{row['status']}]  {row['n_chapters']} chapters  "
                   f"strategy={row['strategy']}")
        click.echo(f"  segments: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        artifact = get_artifact(db, book_id)
        if artifact:
            click.echo(f"  output:   {artifact['output_path']} "
                       f"({artifact['duration_ms'] / 1000 / 60:.1f} min, "
                       f"{artifact['chapter_count']} chapters)")
        chapters = get_chapters(db, book_id)
        if chapters:
            chars = sum(c["char_count"] for c in chapters)
            duration = (artifact["duration_ms"] / 1000) if artifact else 0
            click.echo(f"  chars:    {chars}")
            if duration > 0:
                click.echo(f"  chars/s:  {chars / duration:.1f}")
        failed = failed_segments(db, book_id)
        for row_seg in failed[:10]:
            click.echo(f"  FAILED c{row_seg['chapter_idx']} #{row_seg['seg_idx']}: "
                       f"{row_seg['error']}", err=True)
        return

    rows = db.execute("SELECT * FROM books ORDER BY updated_at DESC").fetchall()
    if not rows:
        click.echo("no books yet — run `epub2m4b inspect <book.epub>`")
        return
    for row in rows:
        counts = segment_counts(db, row["book_id"])
        total = sum(counts.values())
        done = counts.get("done", 0)
        click.echo(f"{row['book_id'][:12]}  {row['status']:<8} {done}/{total:<6} "
                   f"{row['n_chapters']:>4} ch  {row['title'][:40]}")


# --------------------------------------------------------------------------
# voices
# --------------------------------------------------------------------------


@cli.command()
@click.option("--lang", "lang_code", default=None,
              help="filter by language code: z, a, b, j, e, f, h, i, p")
@click.option("--json", "as_json", is_flag=True, help="machine-readable output")
def voices(lang_code: str | None, as_json: bool) -> None:
    """List the known Kokoro voices (no model download required)."""

    from soundbook.tts.voices import ALL_VOICES, DEFAULT_ZH_VOICE, voices_for_lang

    selected = voices_for_lang(lang_code) if lang_code else ALL_VOICES
    if not selected:
        _fail(f"unknown language code: {lang_code}", EXIT_ERROR)
        return
    if as_json:
        import json

        click.echo(json.dumps(
            {
                "default_zh_voice": DEFAULT_ZH_VOICE,
                "voices": [
                    {"id": v.id, "lang_code": v.lang_code,
                     "language": v.language, "gender": v.gender}
                    for v in selected
                ],
            },
            ensure_ascii=False, indent=2,
        ))
        return
    click.echo(f"default Chinese voice: {DEFAULT_ZH_VOICE}")
    for v in selected:
        click.echo(f"  {v.id:<14} {v.lang_code}  {v.language}  {v.gender}")


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------


@cli.command()
@click.argument("book", type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "-o", type=click.Path(dir_okay=False), help="output .m4b path")
@click.option("--tts", "tts_name", default="fake",
              type=click.Choice(["fake", "kokoro", "openai_compat"]))
@click.option("--voice", default=None, help="voice id (engine specific)")
@click.option("--rate", default=1.0, type=float, help="speaking rate multiplier")
@click.option("--jobs", default=1, type=int, help="parallel synthesis workers")
@click.option("--max-retries", default=3, type=int)
@click.option("--endpoint", default=None, help="base URL for openai_compat")
@click.option("--bitrate", default=None, help="AAC bitrate, e.g. 64k")
@click.option("--no-loudnorm", is_flag=True, help="skip two-pass loudnorm")
@click.option("--no-speak-titles", is_flag=True, help="do not narrate chapter titles")
@click.option("--include-front-matter", is_flag=True,
              help="also narrate chapters classified as front/back matter")
@click.option("--allow-incomplete", is_flag=True,
              help="package what finished, still exit 2")
def run(book: str, out: str | None, tts_name: str, voice: str | None, rate: float,
        jobs: int, max_retries: int, endpoint: str | None, bitrate: str | None,
        no_loudnorm: bool, no_speak_titles: bool, include_front_matter: bool,
        allow_incomplete: bool) -> None:
    """Synthesize and package a book. Resumable: rerunning does only new work."""

    config.ensure_dirs()
    ok, bad = _doctor_report()
    if bad:
        for line in bad:
            click.echo(f"FAIL {line}", err=True)
        raise SystemExit(EXIT_ERROR)

    policies = _policies(bitrate, not no_loudnorm, not no_speak_titles)
    tts_config = TTSConfig(backend=tts_name, voice=voice, rate=rate, jobs=jobs,
                           max_retries=max_retries, endpoint=endpoint)
    book_path = Path(book).expanduser()
    book_id = None
    lock = None
    db = connect(config.db_path())

    try:
        from soundbook.tts.base import make_backend

        try:
            backend = make_backend(tts_name, tts_config)
            info = backend.info()
        except Exception as exc:  # noqa: BLE001
            _fail(f"TTS backend {tts_name} unavailable: {exc}", EXIT_TTS)
            return
        synth_fp = synth_fingerprint_for(info, tts_config)

        prepared = prepare(db, book_path, policies,
                           include_skippable=include_front_matter,
                           write_segments=True, synth_fp=synth_fp)
        book_id = prepared.book.info.book_id
        for plan in prepared.chapters:
            for text in plan.warnings:
                if text.startswith("anchor_"):
                    click.echo(f"warning: chapter {plan.draft.idx}: {text}", err=True)
        lock = FileLock(str(config.locks_dir() / f"{book_id}.lock"))
        lock.acquire(timeout=0)

        reset = verify_cached_segments(db, book_id)
        if reset:
            click.echo(f"cache: {reset} segment(s) lost their audio, resynthesizing")

        def progress(done: int, total: int) -> None:
            if done == total or done % 25 == 0:
                click.echo(f"  synth {done}/{total}", err=True)

        report = synthesize(
            db, book_id,
            backend_factory=lambda: make_backend(tts_name, tts_config),
            synth_fp=synth_fp,
            jobs=max(1, jobs),
            max_retries=max(1, max_retries),
            progress=progress,
        )
        if report.total:
            click.echo(f"synth: {report.done - report.cached} new, "
                       f"{report.cached} cached, {len(report.failed)} failed",
                       err=True)
        if report.failed:
            click.echo(f"{len(report.failed)} segment(s) failed:", err=True)
            for chapter_idx, seg_idx, error in report.failed[:10]:
                click.echo(f"  c{chapter_idx} #{seg_idx}: {error}", err=True)
            if not allow_incomplete:
                set_book_meta(db, book_id, status="failed")
                db.commit()
                raise SystemExit(EXIT_SEGMENTS)

        incomplete = not all_done(db, book_id)
        if incomplete and not allow_incomplete:
            click.echo("book is incomplete; rerun to resume or pass --allow-incomplete",
                       err=True)
            raise SystemExit(EXIT_SEGMENTS)
        if incomplete and not done_segments(db, book_id):
            click.echo("nothing was synthesized; there is no audio to package", err=True)
            raise SystemExit(EXIT_SEGMENTS)

        output = Path(out).expanduser() if out else Path.cwd() / f"{book_path.stem}.m4b"
        artifact = get_artifact(db, book_id)
        sig = content_signature(db, book_id)
        if (artifact is not None and Path(artifact["output_path"]) == output
                and output.is_file()
                and _artifact_is_fresh(artifact, sig, policies,
                                       prepared.book.info.cover_sha256)):
            click.echo(f"up to date: {output}")
        else:
            try:
                result = build_artifact(
                    db, prepared.book, policies=policies, output=output,
                    allow_loudnorm=tts_name != "fake" and policies.audio.loudnorm,
                )
            except InsufficientSpace as exc:
                _fail(str(exc), EXIT_DISK)
                return
            for warning in result.warnings:
                click.echo(f"warning: {warning}", err=True)
            click.echo(f"wrote {result.path} ({result.duration_ms / 1000 / 60:.1f} min, "
                       f"{result.chapter_count} chapters)")
        set_book_meta(db, book_id, status="done" if not incomplete else "partial")
        db.commit()
        if incomplete:
            click.echo("incomplete book was packaged; failed segments are still listed",
                       err=True)
            raise SystemExit(EXIT_SEGMENTS)
    except UnusableBook as exc:
        _fail(f"cannot use {book}: {exc}", EXIT_INPUT)
    except InsufficientSpace as exc:
        _fail(str(exc), EXIT_DISK)
    except KeyboardInterrupt:
        click.echo("interrupted", err=True)
        raise SystemExit(130)
    finally:
        if lock is not None and lock.is_locked:
            lock.release()
        db.close()


def main() -> None:
    try:
        cli(prog_name=DIST_NAME)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - last-resort exit code
        click.echo(f"{DIST_NAME}: unexpected error: {exc}", err=True)
        raise SystemExit(EXIT_ERROR)


if __name__ == "__main__":  # pragma: no cover
    main()
