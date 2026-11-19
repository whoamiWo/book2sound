"""Deterministic silent backend for CI (plan §3.1).

Duration is a pure function of the text length and ``--rate``, so cache tests
("switch voice, switch back, zero synthesis") work without a model, and the
audio is silence, which is exactly why loudnorm must be skipped for it.
"""

from __future__ import annotations

from soundbook.config import TTSConfig
from soundbook.models import EngineInfo
from soundbook.util.audio import silence_pcm

MS_PER_CHAR = 40
MIN_MS = 200
MAX_MS = 30_000


class FakeBackend:
    def __init__(self, config: TTSConfig | None = None) -> None:
        self.config = config or TTSConfig()

    def info(self) -> EngineInfo:
        return EngineInfo(
            name="fake",
            model_id="fake-silence",
            model_version="1",
            sample_rate=24_000,
            voice=self.config.voice or "silence",
        )

    def duration_ms(self, text: str) -> int:
        rate = self.config.rate or 1.0
        return max(MIN_MS, min(MAX_MS, int(len(text) * MS_PER_CHAR / rate)))

    def synth(self, text: str) -> bytes:
        samples = int(round(24_000 * self.duration_ms(text) / 1000))
        return silence_pcm(samples)
