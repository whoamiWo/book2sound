"""TTS backend contract (spec §9).

A backend is a pure text → PCM function with an identity.  It must return
24 kHz mono 16-bit little-endian PCM; resampling, if the engine speaks another
rate, happens inside the backend so every cached FLAC has one format.
"""

from __future__ import annotations

from typing import Protocol

from soundbook.config import TTSConfig, synth_fingerprint
from soundbook.models import EngineInfo


class TTSBackend(Protocol):
    def info(self) -> EngineInfo: ...

    def synth(self, text: str) -> bytes:
        """Return PCM bytes (s16le, mono, ``info().sample_rate``)."""


def synth_fingerprint_for(info: EngineInfo, config: TTSConfig) -> str:
    return synth_fingerprint(
        backend=info.name,
        model_id=info.model_id,
        model_version=info.model_version,
        voice=info.voice,
        rate=config.rate,
        sample_rate=info.sample_rate,
    )


def make_backend(name: str, config: TTSConfig) -> TTSBackend:
    name = (name or "fake").lower()
    if name == "fake":
        from soundbook.tts.fake import FakeBackend

        return FakeBackend(config)
    if name == "kokoro":
        from soundbook.tts.kokoro_local import KokoroBackend

        return KokoroBackend(config)
    if name in {"openai", "openai_compat"}:
        from soundbook.tts.openai_compat import OpenAICompatBackend

        return OpenAICompatBackend(config)
    raise ValueError(f"unknown TTS backend: {name} (expected fake, kokoro, openai_compat)")
