"""Kokoro local backend (plan stage 4 step 20).

The engine is optional: importing this module is cheap, and so is constructing
the backend — the KPipeline (model load) is created lazily on first ``synth``.
``info()`` still imports ``kokoro`` for its version, so ``run`` fails fast with
exit code 4 when the extra is missing, without paying for a model load twice
(once for the probe, once per worker).
"""

from __future__ import annotations

import os

from soundbook.config import TTSConfig
from soundbook.models import EngineInfo
from soundbook.tts.voices import DEFAULT_ZH_VOICE, lang_code_for

DEFAULT_VOICE = DEFAULT_ZH_VOICE
_MISSING = (
    "the kokoro backend needs the optional dependency: "
    "pip install 'epub2m4b[kokoro]' (kokoro==0.9.4, misaki[zh]==0.9.4)"
)


class KokoroBackend:
    def __init__(self, config: TTSConfig | None = None) -> None:
        self.config = config or TTSConfig()
        self._voice = self.config.voice or os.environ.get("SOUNDBOOK_KOKORO_VOICE") or DEFAULT_VOICE
        self._lang_code = os.environ.get("SOUNDBOOK_KOKORO_LANG") or lang_code_for(self._voice)
        self._pipeline = None

    def _get_pipeline(self):
        if self._pipeline is None:
            try:
                import torch
                from kokoro import KPipeline
            except Exception as exc:  # pragma: no cover - depends on install
                raise RuntimeError(_MISSING) from exc
            if (self.config.jobs or 1) > 1:
                # One worker thread per job; letting torch spawn its own pool
                # per process oversubscribes the CPU (plan stage 4).
                torch.set_num_threads(1)
            self._pipeline = KPipeline(lang_code=self._lang_code,
                                       repo_id="hexgrad/Kokoro-82M")
        return self._pipeline

    def info(self) -> EngineInfo:
        try:
            import kokoro
        except Exception as exc:  # pragma: no cover - depends on install
            raise RuntimeError(_MISSING) from exc
        return EngineInfo(
            name="kokoro",
            model_id="hexgrad/Kokoro-82M",
            model_version=getattr(kokoro, "__version__", "unknown"),
            sample_rate=24_000,
            voice=self._voice,
        )

    def synth(self, text: str) -> bytes:
        import numpy as np

        chunks: list[bytes] = []
        for _graphemes, _phonemes, audio in self._get_pipeline()(
            text, voice=self._voice, speed=float(self.config.rate or 1.0), split_pattern=r"\n+"
        ):
            array = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
            pcm = np.clip(array, -1.0, 1.0)
            chunks.append((pcm * 32767.0).astype("<i2").tobytes())
        return b"".join(chunks)
