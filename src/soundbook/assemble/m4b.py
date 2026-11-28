"""M4B packaging (spec §10).

``build_ffmpeg_argv`` is a pure function so the three states required by the
acceptance table — no cover, no loudnorm, cover + loudnorm — are unit-testable
without ffmpeg or an audio file.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from soundbook.assemble.concat import Timeline, build_concat_list, build_ffmeta, build_timeline
from soundbook.assemble.loudnorm import (
    loudnorm_filter,
    measure,
    validate_measurement,
)
from soundbook.config import AudioPolicy, artifact_fingerprint
from soundbook.db import done_segments
from soundbook.util.atomic import atomic_write_text
from soundbook.util.process import CommandError, run


def build_ffmpeg_argv(
    *,
    concat_list: str,
    output: str,
    audio: AudioPolicy,
    ffmeta: str | None = None,
    cover: str | None = None,
    loudnorm_params: dict[str, float] | None = None,
    title: str | None = None,
) -> list[str]:
    """Compose the single ffmpeg invocation that writes the finished M4B."""

    argv = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list]
    cover_index = None
    meta_index = None
    if cover:
        argv += ["-i", cover]
        cover_index = 1
    if ffmeta:
        argv += ["-f", "ffmetadata", "-i", ffmeta]
        meta_index = 2 if cover else 1

    argv += ["-map", "0:a:0"]
    if cover_index is not None:
        argv += ["-map", f"{cover_index}:v:0"]

    if loudnorm_params is not None:
        argv += ["-af", loudnorm_filter(loudnorm_params, audio)]
        argv += ["-ar", str(audio.sample_rate)]
    else:
        argv += ["-ar", str(audio.sample_rate)]

    argv += [
        "-c:a", "aac",
        "-b:a", audio.bitrate,
        "-profile:a", audio.aac_profile,
        "-ac", str(audio.channels),
    ]
    if cover_index is not None:
        # MP4 accepts JPEG/PNG attached pictures verbatim; other formats
        # (webp/gif/bmp) must be transcoded or the muxer rejects them.
        if Path(cover or "").suffix.lower() in {".jpg", ".jpeg", ".png"}:
            argv += ["-c:v", "copy"]
        else:
            argv += ["-c:v", "mjpeg", "-q:v", "2"]
        argv += ["-disposition:v:0", "attached_pic"]
    if meta_index is not None:
        argv += ["-map_metadata", str(meta_index)]
    elif title:
        argv += ["-metadata", f"title={title}"]
    argv += ["-metadata:s:a:0", f"language={audio.language}"]
    if audio.faststart:
        argv += ["-movflags", "+faststart"]
    argv += ["-f", "ipod", output]
    return argv


@dataclass
class AssembleResult:
    path: str
    duration_ms: int
    fingerprint: str
    chapter_count: int
    loudnorm_used: bool
    warnings: list[str] = field(default_factory=list)


def _timeline_fingerprint(db: sqlite3.Connection, book_id: str, audio: AudioPolicy,
                          params: dict[str, float] | None, cover_sha: str | None,
                          timeline: Timeline) -> str:
    keys = [row["audio_key"] for row in done_segments(db, book_id)]
    silences = tuple(e.n_samples for e in timeline.entries if e.kind == "silence")
    samples = [e.n_samples for e in timeline.entries]
    return artifact_fingerprint(
        audio_keys=keys,
        audio=audio,
        loudnorm_params=params,
        cover_sha256=cover_sha,
        silence_ms=silences,
        n_samples=samples,
    )


def assemble_m4b(
    db: sqlite3.Connection,
    book_id: str,
    *,
    title: str,
    output: str | Path,
    work_dir: str | Path,
    audio: AudioPolicy,
    cover_path: str | Path | None,
    cover_sha256: str | None,
    allow_loudnorm: bool = True,
) -> AssembleResult:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    timeline = build_timeline(db, book_id, str(work), sample_rate=audio.sample_rate)
    if not timeline.entries:
        raise RuntimeError("nothing to assemble: no done segments")

    concat_path = work / "concat.txt"
    ffmeta_path = work / "chapters.ffmeta"
    atomic_write_text(concat_path, build_concat_list(timeline.entries))
    atomic_write_text(ffmeta_path, build_ffmeta(timeline.spans, title=title,
                                                language=audio.language))

    warnings: list[str] = []
    params: dict[str, float] | None = None
    if audio.loudnorm and allow_loudnorm:
        measured = measure(concat_path, audio)
        ok, reason = validate_measurement(measured)
        if ok:
            params = measured
        else:
            warnings.append(f"loudnorm skipped: {reason}")

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=out.name + ".", suffix=".tmp.m4b", dir=out.parent)
    os.close(fd)
    try:
        argv = build_ffmpeg_argv(
            concat_list=str(concat_path),
            output=tmp_name,
            audio=audio,
            ffmeta=str(ffmeta_path),
            cover=str(cover_path) if cover_path else None,
            loudnorm_params=params,
            title=title,
        )
        run(argv)
        os.replace(tmp_name, out)
    except CommandError as exc:
        raise RuntimeError(f"ffmpeg failed: {exc}") from exc
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:  # pragma: no cover
                pass

    # The acceptance table (§5) promises chapter START accuracy; check it on
    # the file we just wrote instead of relying on test-only verification.
    try:
        problems = verify_output(out, timeline.spans)
    except (CommandError, OSError) as exc:  # pragma: no cover - ffprobe missing
        problems = [f"could not verify chapter timeline: {exc}"]
    warnings.extend(problems)

    fingerprint = _timeline_fingerprint(db, book_id, audio, params, cover_sha256, timeline)
    return AssembleResult(
        path=str(out),
        duration_ms=timeline.total_ms,
        fingerprint=fingerprint,
        chapter_count=len(timeline.spans),
        loudnorm_used=params is not None,
        warnings=warnings,
    )


def probe_chapters(path: str | Path) -> list[dict]:
    argv = ["ffprobe", "-v", "error", "-show_chapters", "-of", "json", str(path)]
    payload = run(argv).stdout_text
    return json.loads(payload).get("chapters", [])


def verify_output(path: str | Path, expected_spans, tolerance_ms: int = 150) -> list[str]:
    """Chapter count and START drift, per the acceptance table (§5)."""

    problems: list[str] = []
    chapters = probe_chapters(path)
    if len(chapters) != len(expected_spans):
        problems.append(f"chapter count {len(chapters)} != expected {len(expected_spans)}")
    for got, want in zip(chapters, expected_spans, strict=False):
        start_ms = int(round(float(got["start_time"]) * 1000))
        if abs(start_ms - want.start_ms) > tolerance_ms:
            problems.append(
                f"chapter {want.chapter_idx} START {start_ms} ms, expected {want.start_ms} ms")
    return problems
