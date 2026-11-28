from __future__ import annotations

from soundbook.config import TTSConfig
from soundbook.tts.kokoro_local import KokoroBackend


def test_construction_does_not_load_the_model():
    """The CLI creates a backend just to read ``info()``; that must stay cheap.

    Before this guard, ``run --tts kokoro`` loaded the model for the probe and
    then loaded it again (and kept both alive) for the synthesis workers.
    """

    backend = KokoroBackend(TTSConfig())
    assert backend._pipeline is None
    assert backend._voice
    assert backend._lang_code


def test_voice_and_language_can_be_overridden(monkeypatch):
    monkeypatch.setenv("SOUNDBOOK_KOKORO_VOICE", "zm_yunxi")
    monkeypatch.setenv("SOUNDBOOK_KOKORO_LANG", "z")
    backend = KokoroBackend(TTSConfig())
    assert backend._voice == "zm_yunxi"
    assert backend._lang_code == "z"
