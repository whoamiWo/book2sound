from __future__ import annotations

from soundbook.config import (
    SegmentPolicy,
    audio_key,
    canonical_json,
    sha256_text,
    synth_fingerprint,
    text_fingerprint,
)


def test_audio_key_depends_on_text_and_fingerprint():
    fp = synth_fingerprint(backend="fake", model_id="m", model_version="1",
                           voice="v", rate=1.0, sample_rate=24000)
    key_a = audio_key("你好。", fp)
    key_b = audio_key("你好！", fp)
    key_c = audio_key("你好。", fp + "x")
    assert key_a != key_b
    assert key_a != key_c
    assert audio_key("你好。", fp) == key_a
    assert len(key_a) == 64


def test_synth_fingerprint_changes_with_voice_and_rate():
    base = synth_fingerprint(backend="fake", model_id="m", model_version="1",
                             voice="v", rate=1.0, sample_rate=24000)
    other_voice = synth_fingerprint(backend="fake", model_id="m", model_version="1",
                                    voice="w", rate=1.0, sample_rate=24000)
    other_rate = synth_fingerprint(backend="fake", model_id="m", model_version="1",
                                   voice="v", rate=1.1, sample_rate=24000)
    assert len({base, other_voice, other_rate}) == 3


def test_canonical_json_stable_ordering():
    a = canonical_json({"b": 1, "a": [1, 2], "中": "文"})
    b = canonical_json({"中": "文", "a": [1, 2], "b": 1})
    assert a == b


def test_text_fingerprint_changes_with_policy():
    from soundbook.config import Policies

    p1 = text_fingerprint(Policies())
    p2 = text_fingerprint(Policies(segment=SegmentPolicy(target_chars=120)))
    assert p1 != p2


def test_sha256_text_deterministic():
    assert sha256_text("abc") == sha256_text("abc")
    assert sha256_text("abc") != sha256_text("abd")
