"""Integration test for the openai_compat backend against a local fake server.

A stdlib ``http.server`` returns a real WAV (PCM sine tone) so the whole path —
HTTP JSON → WAV bytes → ffmpeg decode → 24 kHz mono PCM → FLAC cache → M4B —
is exercised without any external service.
"""

from __future__ import annotations

import io
import json
import math
import shutil
import struct
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from soundbook.cli import cli

pytestmark = pytest.mark.e2e

need_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                 reason="ffmpeg not installed")

LONG = ("这是一段足够长的正文，用来确保章节不会被误判为辅文。"
        "山风穿过松林，发出低沉的声响，像是有人在远处低声说话。" * 12)


def _wav(sample_rate: int = 22050, seconds: float = 0.25, freq: float = 440.0) -> bytes:
    """A real, non-silent mono WAV — different rate on purpose, to test resampling."""

    n = int(sample_rate * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / sample_rate)))
            for i in range(n)
        )
        wav.writeframes(frames)
    return buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *args):  # silence test output
        pass

    def do_POST(self):
        if not self.path.endswith("/audio/speech"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).requests.append(payload)
        body = _wav()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def speech_server():
    _Handler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", _Handler.requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _invoke(args, home):
    runner = CliRunner()
    return runner.invoke(cli, args,
                         env={"SOUNDBOOK_HOME": str(home / "home"),
                              "SOUNDBOOK_CACHE_DIR": str(home / "cache")},
                         catch_exceptions=False)


@need_ffmpeg
def test_openai_compat_synth_resamples_to_24k_mono(speech_server, home):
    endpoint, requests = speech_server
    from soundbook.config import TTSConfig
    from soundbook.tts.openai_compat import OpenAICompatBackend

    backend = OpenAICompatBackend(TTSConfig(backend="openai_compat", endpoint=endpoint,
                                            voice="cosyvoice-zh"))
    pcm = backend.synth("测试一句话。")
    assert requests and requests[0]["input"] == "测试一句话。"
    assert requests[0]["voice"] == "cosyvoice-zh"
    assert requests[0]["response_format"] == "wav"
    # 0.25 s @ 24 kHz mono s16le = 12000 bytes
    assert len(pcm) == 12_000


@need_ffmpeg
def test_openai_compat_full_run(speech_server, home):
    endpoint, requests = speech_server
    from helpers import Chapter, make_epub

    book = make_epub(home / "remote.epub",
                     [Chapter(f"第{i + 1}章 远程合成", [LONG, LONG]) for i in range(3)])
    out = home / "remote.m4b"
    result = _invoke(["run", str(book), "--tts", "openai_compat",
                      "--endpoint", endpoint, "--voice", "cosyvoice-zh",
                      "-o", str(out)], home)
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert len(requests) > 3

    from soundbook.assemble.m4b import probe_chapters

    assert len(probe_chapters(out)) == 3

    # Second run: fully cached, no further HTTP calls.
    before = len(requests)
    again = _invoke(["run", str(book), "--tts", "openai_compat",
                     "--endpoint", endpoint, "--voice", "cosyvoice-zh",
                     "-o", str(out)], home)
    assert again.exit_code == 0, again.output
    assert "up to date" in again.output
    assert len(requests) == before


@need_ffmpeg
def test_openai_compat_unreachable_endpoint_exits_4(home):
    from helpers import Chapter, make_epub

    book = make_epub(home / "unreachable.epub", [Chapter("第一章", [LONG, LONG])])
    result = _invoke(["run", str(book), "--tts", "openai_compat",
                      "--endpoint", "http://127.0.0.1:1/v1",
                      "--max-retries", "1", "--allow-incomplete"], home)
    # Segment-level connection failures are exit 2; backend construction
    # failures (import errors) are exit 4. Either way: no traceback, no hang.
    assert result.exit_code in (2, 4), result.output
