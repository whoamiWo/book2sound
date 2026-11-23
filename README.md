# epub2m4b

[![CI](https://github.com/whoamiWo/book2sound/actions/workflows/ci.yml/badge.svg)](https://github.com/whoamiWo/book2sound/actions/workflows/ci.yml)

Chinese EPUB → chaptered **M4B** audiobook, as a single resumable CLI.

- **Chaptering**: nav → nav+hybrid → outline → spine, with a vetoer that rejects implausible cuts and records *why* (see `epub2m4b inspect --json`).
- **Resumable**: every segment is cached by `sha256(text + synth_fingerprint)`. Interrupt with Ctrl-C / SIGKILL and rerun — finished segments are never redone.
- **Switch voices for free**: switching back to a previous voice costs zero synthesis.
- **Chapter-accurate timeline**: START/END computed from integer sample counts, verified against ffprobe within 150 ms.
- **Graceful degradation**: DRM/image-only books exit 3; silent loudnorm measurement degrades to "loudnorm off + warning"; per-segment failures exit 2 with `--allow-incomplete` packaging what finished.

## Install

```bash
python3 -m pip install epub2m4b            # core (fake + openai_compat TTS)
python3 -m pip install 'epub2m4b[kokoro]'  # + local Kokoro 0.9.4 engine
ffmpeg -version                            # ffmpeg + ffprobe are required
```

## Use

```bash
epub2m4b doctor                      # check environment (never touches the DB)
epub2m4b inspect book.epub           # show chaptering strategy and segment counts
epub2m4b inspect book.epub --json    # machine-readable version
epub2m4b voices                      # list Kokoro voices (no model download)
epub2m4b voices --lang z             # only Mandarin voices
epub2m4b run book.epub --tts kokoro --voice zf_xiaobei -o book.m4b
epub2m4b status                      # library overview
epub2m4b status book.epub            # one book, including failed segments
```

Options on `run`: `--voice`, `--rate`, `--jobs`, `--max-retries`, `--endpoint` (for `openai_compat`), `--bitrate`, `--no-loudnorm`, `--no-speak-titles`, `--include-front-matter`, `--allow-incomplete`.

For CPU Kokoro runs, start with `--jobs 1`: on the tested 10-core/20-thread machine it was faster than `--jobs 2` because multi-job mode limits each worker to one torch thread. Re-measure on other hardware; see [benchmarks](docs/benchmarks.md).

Exit codes: **0** success · **1** general error · **2** failed/incomplete segments · **3** unusable input · **4** TTS unavailable · **5** insufficient disk · **130** interrupted.

## State

- `SOUNDBOOK_HOME` (default `~/.local/share/soundbook`): `state.sqlite`, `locks/`, `work/`.
- `SOUNDBOOK_CACHE_DIR` (default `~/.cache/soundbook/audio`): per-segment FLAC files, content-addressed.

## TTS backends

| `--tts` | what it does |
| --- | --- |
| `fake` | Deterministic silence, for tests/CI (loudnorm auto-disabled) |
| `kokoro` | Local Kokoro 82M, default voice `zf_xiaobei`, `lang_code` inferred from the voice id (`SOUNDBOOK_KOKORO_VOICE`, `SOUNDBOOK_KOKORO_LANG` override) |
| `openai_compat` | Any OpenAI-compatible `/v1/audio/speech` endpoint (CosyVoice, …). Env: `SOUNDBOOK_TTS_URL`, `SOUNDBOOK_TTS_MODEL`, `SOUNDBOOK_TTS_VOICE` |

A failed segment is retried on the next `run` — failure is not sticky.

Kokoro notes: `kokoro==0.9.4` requires **Python < 3.13** (use the Docker image, which is
3.12, if your system Python is newer). Model weights come from Hugging Face on first
run; behind a firewall set `HF_ENDPOINT=https://hf-mirror.com` and
`HF_HUB_DISABLE_XET=1` (the Xet CDN is not served by the mirror).

## Docker

```bash
docker build -t epub2m4b .
docker run --rm -v "$PWD:/data" epub2m4b inspect book.epub
docker run --rm -v "$PWD:/data" epub2m4b run book.epub --tts fake -o book.m4b
```

The default image ships the core backends only. For the local Kokoro engine use `Dockerfile.kokoro` (Python 3.12, installs `.[kokoro]`; validated end to end, see [docs/benchmarks.md](docs/benchmarks.md) Spike 2):

```bash
docker build -f Dockerfile.kokoro -t epub2m4b-kokoro .
docker run --rm -v "$PWD:/data" -e HF_ENDPOINT=https://hf-mirror.com -e HF_HUB_DISABLE_XET=1 \
  epub2m4b-kokoro run book.epub --tts kokoro -o book.m4b
```

The `HF_*` variables are only needed behind a firewall. The Kokoro image is large (about 10.5 GB with torch).

Two practical notes:

- If `pypi.org` is unreachable from your Docker network, pass a mirror:
  `docker build -t epub2m4b --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple .`
- The container runs as root, so files it writes into a bind-mounted `/data` (the M4B, the cache, the SQLite state) are root-owned on the host. Use a named volume, or `--user "$(id -u):$(id -g)"` together with `-e SOUNDBOOK_HOME=/tmp/state -e SOUNDBOOK_CACHE_DIR=/tmp/cache`.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install -e ".[dev]"
pytest                    # unit + e2e (real ffmpeg, --tts fake)
pytest -m e2e             # only end-to-end
SOUNDBOOK_CORPUS=/path/to/epubs pytest -m corpus -s  # optional local real-book evaluation
```

Docs: [`docs/adr.md`](docs/adr.md) (decision records), [`docs/limitations.md`](docs/limitations.md), [`docs/benchmarks.md`](docs/benchmarks.md), [`docs/corpus.md`](docs/corpus.md) (local annotation), [`docs/compat.md`](docs/compat.md) (sample/player matrix), [`docs/compare.md`](docs/compare.md), [`docs/licenses.md`](docs/licenses.md).

## Legal

Apache-2.0. No text, model weights or corpora are redistributed with this project. You are responsible for the legality of the EPUBs you convert. The optional Release-only public-domain sample is documented in [`docs/compat.md`](docs/compat.md); it is not included in the repository or pip package.
