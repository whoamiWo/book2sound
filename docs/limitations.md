# 已知限制与失败模式

本文档对应规范 §14，并逐条标注当前代码的处理方式。

## 输入侧

| 情况 | 行为 | 退出码 |
| --- | --- | --- |
| 真正的 DRM（`EncryptedKey` 或非字体 `CipherReference`） | `book.unsupported` 非空 → `UnusableBook` | 3 |
| 仅字体混淆（`encryption.xml` 里只有 font） | 正常朗读，`inspect` 里报告 `obfuscated_fonts` | 0 |
| 图片型 EPUB（扫描书） | 惰性检测在 `load_book` 中被强制触发，无法提取文本 | 3 |
| 非 zip / 损坏文件 | `epubx.open_book` 抛错 → `UnusableBook` | 3 |
| 全文无正文块 | `no narratable text blocks in any spine document` | 3 |

## 文本提取的已知偏差

- epubx 0.2.3 会把 `<h1>` 同时发成 `paragraph` + `heading` 两块；`ingest/loader.py` 会丢弃紧邻同文的 paragraph 副本。若上游修复了这一点，去重逻辑是 no-op。
- 表格、列表、preformatted 会被当作正文朗读（把单元格文本串起来）。复杂表格的朗读体验有限。
- `<math>`、`<figure>`、`page_break`、脚注引用块默认静默；脚注正文仍保留在 spine 顺序里。
- CJK 之外的语言未做专门处理：`segment` 依赖中文句末标点，英文文本仍能分段，但打包粒度会偏大。
- 分章否决器（`dominant_chapter` / `oversized_chapter` / `tiny_median_chapter`）会沿 nav → outline → spine 逐级降级，并把拒绝原因写进 `chapters.rejected`（`inspect --json` 可见）。
- 前/后辅文（目录、序言、版权、后记…）默认**不合成**；`--include-front-matter` 打开。stub 阈值 300 字符，见 `ingest/classify.py`。
- 分段以段落为边界：短段不会与下一段合并，因此对话体、诗歌或大量单句成段的书会产生很多明显短于
  `target_chars`（默认 90 字）的段。样书实测 21,911 字 → 469 段，约 47 字/段。每个非标题分段是一次
  TTS 调用；HTTP 后端按分段发请求，30 万字书约 6k 次请求，需要端点承受这个请求量，停顿听感也会更碎。
  目前没有公开的 `--target-chars` CLI 选项；手工调整时修改 `SegmentPolicy.target_chars`（不要超过
  `hard_max_chars=300`），并注意这会改变分段与缓存键。

## 合成侧

- `--tts fake` 产生**纯静音**，因此 loudnorm 自动关闭（`allow_loudnorm=False`）。e2e/CI 全部走这条路径。
- `--tts kokoro` 需要 `pip install 'epub2m4b[kokoro]'`（kokoro 0.9.4 + `misaki[zh]` 0.9.4）；kokoro 要求 Python < 3.13，宿主 Python 更新时用 `Dockerfile.kokoro`（3.12）。已在容器内跑通端到端（见 `docs/benchmarks.md` 的 Spike 2），纯 CPU 速度慢。
- `--tts openai_compat` 依赖用户自备的 OpenAI 兼容 `/v1/audio/speech` 端点，默认 `http://127.0.0.1:8000/v1`；WAV 响应由 ffmpeg 解码重采样到 24 kHz mono。
- 采样数以 FLAC STREAMINFO 回读为准；不一致 → 段标 `failed`，绝不按文件大小推断。
- 每段最多 `--max-retries` 次（默认 3），仍失败则标 `failed` 并继续；`run` 默认以退出码 2 结束，`--allow-incomplete` 会封装已完成部分但仍返回 2（ADR-018）。
- **`failed` 不是终态**：下一次 `run` 会自动重试失败段，因此"引擎临时故障 → 修复 → 重跑"可以完成整本书。
- 全书零完成段时不会产出空 M4B，直接退出码 2。
- 网络/本地引擎不可用（import 失败、连不上端点）→ 退出码 4。

## 缓存与状态

- 段缓存键 = `sha256(text + NUL + synth_fingerprint)`；`synth_fingerprint` 包含 backend / model_id / model_version / voice / rate / sample_rate / AUDIO_FORMAT_VERSION。
- 已存在的缓存 FLAC 直接复用，所以"换 voice 再换回来"是零合成；但上一次运行覆盖过输出文件时会重新封装一次。
- 段文件丢失或采样数不符 → 该段自动回到 `pending`。
- 书级锁 = `SOUNDBOOK_HOME/locks/<book_id>.lock`，非阻塞获取；两个进程同时跑同一本书时第二个直接失败。
- 中断（SIGKILL）后已 `done` 的段不会丢；运行中的段在下次 `run` 时重做。

## 封装侧

- loudnorm 两遍法在静音或测量不可用时降级为"loudnorm 关闭 + 警告"，不会产出坏文件。
- 章节时间轴只累加整数采样数，最后换算毫秒；容差 150 ms（`verify_output`）。
- 封面以 `attached_pic` 复制进 M4B；无封面时纯音频。
- 磁盘估算 = `5800 字节/字 × 待合成字数 + AAC 估重`，再乘 1.3；不足 → 退出码 5。
- 本实现不处理"同一本书多版本输出"的并发写，仅依赖输出文件的原子 rename。

## 明确的非目标（v0）

- 不做 OCR、不做 GUI、不做在线服务。
- 不做流式边下边播。
- 不重新分发任何受版权保护的文本；用户自行负责输入 EPUB 的合法性。
