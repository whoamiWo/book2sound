from __future__ import annotations

from soundbook.assemble.loudnorm import (
    loudnorm_filter,
    parse_measurement,
    validate_measurement,
)
from soundbook.config import AudioPolicy

STDERR = """ffmpeg version 8.0.1
[Parsed_loudnorm_0] progress end
{
        "input_i" : "-20.04",
        "input_tp" : "-2.97",
        "input_lra" : "6.9",
        "input_thresh" : "-30.52",
        "output_i" : "-18.02",
        "output_tp" : "-1.50",
        "output_lra" : "6.0",
        "output_thresh" : "-28.54",
        "normalization_type" : "dynamic",
        "target_offset" : "0.02"
}
"""

PARAMS = {"input_i": -20.04, "input_tp": -2.97, "input_lra": 6.9,
          "input_thresh": -30.52, "target_offset": 0.02}


def test_parse_last_json_object():
    params = parse_measurement(STDERR)
    assert params == PARAMS


def test_parse_returns_none_on_garbage():
    assert parse_measurement("no json here") is None
    assert parse_measurement("{ \"input_i\": \"x\" }") is None


def test_validate_rejects_silence():
    silent = {**PARAMS, "input_lra": 0.0}
    ok, reason = validate_measurement(silent)
    assert not ok
    assert "silent" in reason


def test_validate_rejects_missing():
    ok, _ = validate_measurement(None)
    assert not ok


def test_validate_accepts_real_measurement():
    ok, reason = validate_measurement(PARAMS)
    assert ok and reason == ""


def test_filter_includes_measured_values():
    text = loudnorm_filter(PARAMS, AudioPolicy())
    assert "measured_I=-20.04" in text
    assert "measured_TP=-2.97" in text
    assert "linear=true" in text
    assert text.endswith("aresample=24000:first_pts=0")
