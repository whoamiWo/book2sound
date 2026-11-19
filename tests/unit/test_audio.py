from __future__ import annotations

import shutil

import pytest

from soundbook.util.audio import (
    AudioError,
    flac_total_samples,
    pcm_to_flac,
    silence_pcm,
    write_silence_flac,
)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_silence_flac_sample_count_roundtrip(tmp_path):
    path = write_silence_flac(tmp_path / "sil.flac", 12000, sample_rate=24000)
    assert flac_total_samples(path) == 12000


def test_pcm_to_flac_verifies_frame_count(tmp_path):
    pcm = silence_pcm(6000)
    path = pcm_to_flac(pcm, tmp_path / "tone.flac", sample_rate=24000, channels=1,
                       expected_samples=6000)
    assert flac_total_samples(path) == 6000


def test_pcm_to_flac_rejects_short_writes(tmp_path):
    with pytest.raises(AudioError):
        pcm_to_flac(silence_pcm(2400), tmp_path / "bad.flac", sample_rate=24000,
                    channels=1, expected_samples=9999)
    assert not (tmp_path / "bad.flac").exists()


def test_pcm_must_be_whole_frames(tmp_path):
    with pytest.raises(AudioError):
        pcm_to_flac(b"\x00", tmp_path / "odd.flac")
