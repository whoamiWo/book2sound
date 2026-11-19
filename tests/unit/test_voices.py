from __future__ import annotations

from soundbook.tts.voices import (
    ALL_VOICES,
    BY_ID,
    DEFAULT_ZH_VOICE,
    ZH_VOICES,
    lang_code_for,
    voices_for_lang,
)


def test_catalogue_is_consistent():
    assert len({v.id for v in ALL_VOICES}) == len(ALL_VOICES)
    assert BY_ID[DEFAULT_ZH_VOICE].language == "zh"
    for voice in ALL_VOICES:
        assert voice.lang_code in "abzje fhip".replace(" ", "")
        assert voice.gender in {"female", "male"}
        assert voice.id[0] == voice.lang_code


def test_mandarin_voices_are_listed():
    zh = voices_for_lang("z")
    assert zh == ZH_VOICES
    assert {v.id for v in zh} >= {"zf_xiaobei", "zm_yunjian"}
    assert all(v.language == "zh" for v in zh)


def test_lang_code_inference_and_fallback():
    assert lang_code_for("zf_xiaobei") == "z"
    assert lang_code_for("af_heart") == "a"
    assert lang_code_for("bf_emma") == "b"
    assert lang_code_for("jm_kumo") == "j"
    # unknown community voice: prefix still decides
    assert lang_code_for("zf_custom") == "z"
    assert lang_code_for("am_custom") == "a"
    # completely unparseable: fall back to the Mandarin default
    assert lang_code_for("nonsense") == "z"
    assert lang_code_for("nonsense", default="e") == "e"
