"""Two-pass loudnorm, with the silence guard from plan §3.1.

Pass 1 prints a JSON measurement on stderr; pass 2 applies it linearly.  When
the measurement is unusable (silence, ``LRA=0``, non-finite values) loudnorm is
skipped and the caller records a warning — CI always walks this path because
``--tts fake`` produces silence by construction.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from soundbook.config import AudioPolicy
from soundbook.util.process import CommandError, run

_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def build_measure_argv(concat_list: str | Path, audio: AudioPolicy) -> list[str]:
    return [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-af", (f"loudnorm=I={audio.loudnorm_i}:TP={audio.loudnorm_tp}"
                f":LRA={audio.loudnorm_lra}:print_format=json"),
        "-f", "null", "-",
    ]


def parse_measurement(stderr: str) -> dict[str, float] | None:
    """Extract the last JSON object ffmpeg printed; None if there is none."""

    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        raw = json.loads(stderr[start:end + 1])
    except json.JSONDecodeError:
        return None
    result: dict[str, float] = {}
    for key in _KEYS:
        try:
            result[key] = float(raw[key])
        except (KeyError, TypeError, ValueError):
            return None
    return result


def validate_measurement(params: dict[str, float] | None) -> tuple[bool, str]:
    if params is None:
        return False, "loudnorm measurement missing"
    if params["input_lra"] <= 0:
        return False, "loudnorm measurement is silent (LRA=0)"
    for key in _KEYS:
        if not math.isfinite(params[key]):
            return False, f"loudnorm measurement not finite ({key})"
    return True, ""


def measure(concat_list: str | Path, audio: AudioPolicy) -> dict[str, float] | None:
    try:
        result = run(build_measure_argv(concat_list, audio), check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return parse_measurement(result.stderr_text)


def loudnorm_filter(params: dict[str, float], audio: AudioPolicy,
                    *, out_sample_rate: int = 24_000) -> str:
    return (
        f"loudnorm=I={audio.loudnorm_i}:TP={audio.loudnorm_tp}:LRA={audio.loudnorm_lra}"
        f":measured_I={params['input_i']}:measured_LRA={params['input_lra']}"
        f":measured_TP={params['input_tp']}:measured_thresh={params['input_thresh']}"
        f":offset={params['target_offset']}:linear=true,"
        f"aresample={out_sample_rate}:first_pts=0"
    )
