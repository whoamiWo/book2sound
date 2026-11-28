from __future__ import annotations

import pytest

from soundbook.assemble.m4b import build_ffmpeg_argv
from soundbook.config import AudioPolicy

AUDIO = AudioPolicy()
PARAMS = {"input_i": -20.0, "input_tp": -3.0, "input_lra": 7.0,
          "input_thresh": -30.0, "target_offset": 0.1}


def _argv(**kwargs):
    base = dict(concat_list="list.txt", output="out.m4b", audio=AUDIO)
    base.update(kwargs)
    return build_ffmpeg_argv(**base)


def test_no_cover_no_loudnorm():
    argv = _argv()
    assert argv[0] == "ffmpeg"
    assert argv[-3:] == ["-f", "ipod", "out.m4b"]
    assert "loudnorm" not in " ".join(argv)
    assert "-c:v" not in argv
    assert "-disposition:v:0" not in argv
    assert "-map" in argv and argv[argv.index("-map") + 1] == "0:a:0"
    assert argv[argv.index("-metadata:s:a:0") + 1] == "language=zho"
    assert "+faststart" in argv


def test_cover_attached_pic():
    argv = _argv(cover="cover.jpg")
    assert argv.count("-i") == 2
    assert "1:v:0" in argv
    assert argv[argv.index("-c:v") + 1] == "copy"
    assert argv[argv.index("-disposition:v:0") + 1] == "attached_pic"


def test_png_cover_is_copied():
    argv = _argv(cover="cover.png")
    assert argv[argv.index("-c:v") + 1] == "copy"


@pytest.mark.parametrize("cover", ["cover.webp", "cover.gif", "cover.bmp", "cover.img"])
def test_other_cover_formats_are_transcoded(cover):
    argv = _argv(cover=cover)
    assert argv[argv.index("-c:v") + 1] == "mjpeg"
    assert argv[argv.index("-q:v") + 1] == "2"
    assert argv[argv.index("-disposition:v:0") + 1] == "attached_pic"


def test_loudnorm_applied():
    argv = _argv(loudnorm_params=PARAMS)
    joined = " ".join(argv)
    assert "loudnorm=I=-18" in joined
    assert "measured_I=-20.0" in joined
    assert "aresample=24000:first_pts=0" in joined


def test_cover_metadata_and_loudnorm_together():
    argv = _argv(cover="c.jpg", ffmeta="chapters.ffmeta", loudnorm_params=PARAMS)
    assert argv.count("-i") == 3
    assert argv[argv.index("-map_metadata") + 1] == "2"
    assert "loudnorm" in " ".join(argv)
    assert argv[argv.index("-b:a") + 1] == AUDIO.bitrate
    assert argv[-2:] == ["-f", "ipod"] or argv[-3] == "-f"


def test_indexing_without_cover():
    argv = _argv(ffmeta="chapters.ffmeta")
    assert argv[argv.index("-map_metadata") + 1] == "1"


def test_title_metadata_when_no_ffmeta():
    argv = _argv(title="我的书")
    assert "title=我的书" in argv


@pytest.mark.parametrize("bad", ["out.m4b", "a b.m4b"])
def test_output_always_last_argument(bad):
    assert _argv(output=bad)[-1] == bad
