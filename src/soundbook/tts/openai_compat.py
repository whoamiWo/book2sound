"""OpenAI-compatible ``/v1/audio/speech`` backend (plan stage 5).

Deliberately endpoint-agnostic: any server that answers the OpenAI speech
contract (CosyVoice wrappers, vLLM, local gateways) works.  No image name or
model name is baked in beyond the OpenAI defaults; both are overridable.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from soundbook.config import TTSConfig
from soundbook.models import EngineInfo
from soundbook.util.audio import decode_to_pcm


class OpenAICompatBackend:
    def __init__(self, config: TTSConfig | None = None) -> None:
        self.config = config or TTSConfig()
        self.endpoint = (
            self.config.endpoint
            or os.environ.get("SOUNDBOOK_TTS_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "http://127.0.0.1:8000/v1"
        ).rstrip("/")
        self.model = os.environ.get("SOUNDBOOK_TTS_MODEL", "tts-1")
        self.voice = self.config.voice or os.environ.get("SOUNDBOOK_TTS_VOICE", "alloy")

    def info(self) -> EngineInfo:
        return EngineInfo(
            name="openai_compat",
            model_id=self.model,
            model_version="api",
            sample_rate=24_000,
            voice=self.voice,
        )

    def synth(self, text: str) -> bytes:
        payload = json.dumps(
            {
                "model": self.model,
                "input": text,
                "voice": self.voice,
                "response_format": "wav",
                "speed": float(self.config.rate or 1.0),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}/audio/speech",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_s) as response:
                body = response.read()
        except urllib.error.URLError as exc:
            raise RuntimeError(f"TTS endpoint failed: {exc}") from exc
        pcm = decode_to_pcm(body, sample_rate=24_000, channels=1)
        if not pcm:
            raise RuntimeError("TTS endpoint returned no audio")
        return pcm
