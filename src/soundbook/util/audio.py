"""Segment audio I/O: 24 kHz mono 16-bit PCM ⇄ FLAC.

``soundfile`` is not a dependency (ADR-016).  FLAC's total sample count is read
straight from the STREAMINFO metadata block, which is exact and much cheaper
than decoding the file with ffprobe.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from soundbook.util.process import CommandError, run

SAMPLE_RATE = 24_000
CHANNELS = 1
SAMPLE_WIDTH = 2  # bytes


class AudioError(RuntimeError):
    pass


def flac_total_samples(path: str | Path) -> int | None:
    """The 36-bit ``total_samples`` field of STREAMINFO, or None if unknown."""

    with open(path, "rb") as handle:
        header = handle.read(4 + 4 + 34)
    if len(header) < 42 or header[:4] != b"fLaC":
        raise AudioError(f"not a native FLAC file: {path}")
    block_header = header[4:8]
    block_type = block_header[0] & 0x7F
    length = int.from_bytes(block_header[1:4], "big")
    if block_type != 0 or length != 34:
        raise AudioError(f"FLAC streaminfo not first/valid in {path}")
    streaminfo = header[8:42]
    packed = int.from_bytes(streaminfo[10:18], "big")
    total = packed & 0xFFFFFFFFF  # low 36 bits
    return total or None


def pcm_to_flac(
    pcm: bytes,
    path: str | Path,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
    expected_samples: int | None = None,
) -> Path:
    """Encode PCM with ffmpeg, atomically, and verify the sample count (plan §3.6)."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if len(pcm) % (SAMPLE_WIDTH * channels):
        raise AudioError("PCM payload is not a whole number of frames")
    want = expected_samples if expected_samples is not None else len(pcm) // (SAMPLE_WIDTH * channels)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    os.close(fd)
    try:
        argv = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels), "-i", "pipe:0",
            "-c:a", "flac", "-compression_level", "5", "-f", "flac", tmp_name,
        ]
        run(argv, stdin=pcm)
        got = flac_total_samples(tmp_name)
        if got != want:
            raise AudioError(f"FLAC sample count mismatch: wrote {got}, expected {want}")
        os.replace(tmp_name, target)
    except CommandError as exc:
        raise AudioError(str(exc)) from exc
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:  # pragma: no cover
                pass
    return target


def silence_pcm(n_samples: int, *, channels: int = CHANNELS) -> bytes:
    return b"\x00\x00" * (n_samples * channels)


def write_silence_flac(path: str | Path, n_samples: int, *, sample_rate: int = SAMPLE_RATE) -> Path:
    return pcm_to_flac(silence_pcm(n_samples), path, sample_rate=sample_rate,
                       expected_samples=n_samples)


def decode_to_pcm(data: bytes, *, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> bytes:
    """Decode/resample arbitrary container bytes (e.g. WAV from an HTTP TTS) to PCM."""

    fd, tmp_name = tempfile.mkstemp(prefix="epub2m4b-in-", suffix=".audio")
    os.close(fd)
    try:
        with open(tmp_name, "wb") as handle:
            handle.write(data)
        argv = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", tmp_name,
            "-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels), "pipe:1",
        ]
        return run(argv).stdout
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:  # pragma: no cover
            pass


def ffprobe_duration_ms(path: str | Path) -> int:
    argv = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    out = run(argv).stdout_text.strip()
    return int(round(float(out) * 1000))
