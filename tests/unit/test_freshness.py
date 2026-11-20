from __future__ import annotations

import json

from soundbook.cli import _artifact_is_fresh
from soundbook.config import AudioPolicy, Policies, SegmentPolicy


def _policies(**audio_overrides) -> Policies:
    return Policies(audio=AudioPolicy(**audio_overrides), segment=SegmentPolicy())


def _artifact(**build_opts_overrides):
    opts = {
        "bitrate": "64k",
        "sample_rate": 24_000,
        "channels": 1,
        "loudnorm": True,
        "loudnorm_i": -18.0,
        "loudnorm_tp": -1.5,
        "loudnorm_lra": 11.0,
        "cover_sha256": None,
        "content_sig": "sig",
    }
    opts.update(build_opts_overrides)
    return {"output_path": "/x/b.m4b", "build_opts": json.dumps(opts)}


def test_fresh_when_everything_matches():
    assert _artifact_is_fresh(_artifact(), "sig", _policies(), None) is True


def test_stale_when_loudnorm_i_changes():
    policies = _policies(loudnorm_i=-14.0)
    assert _artifact_is_fresh(_artifact(), "sig", policies, None) is False


def test_stale_when_loudnorm_tp_changes():
    policies = _policies(loudnorm_tp=-1.0)
    assert _artifact_is_fresh(_artifact(), "sig", policies, None) is False


def test_stale_when_loudnorm_lra_changes():
    policies = _policies(loudnorm_lra=7.0)
    assert _artifact_is_fresh(_artifact(), "sig", policies, None) is False


def test_stale_when_loudnorm_disabled():
    policies = _policies(loudnorm=False)
    assert _artifact_is_fresh(_artifact(), "sig", policies, None) is False


def test_stale_when_sample_rate_or_channels_change():
    assert _artifact_is_fresh(_artifact(), "sig",
                              _policies(sample_rate=48000), None) is False
    assert _artifact_is_fresh(_artifact(), "sig",
                              _policies(channels=2), None) is False


def test_stale_when_cover_changes():
    policies = _policies()
    assert _artifact_is_fresh(_artifact(cover_sha256="old"), "sig",
                              policies, "new") is False
    assert _artifact_is_fresh(_artifact(), "sig", policies, "new") is False


def test_stale_when_content_changes():
    assert _artifact_is_fresh(_artifact(), "other", _policies(), None) is False


def test_no_artifact_is_stale():
    assert _artifact_is_fresh(None, "sig", _policies(), None) is False
