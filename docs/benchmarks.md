# 基准与容量

日期：2026-11-19，本机：Linux / Python 3.14.4 / ffmpeg 8.0.1。

## 合成测试书

`tests/helpers.make_epub` 现场生成，60 章 × 约 514 字，合计 **30 840 字 / 300 段**（每章标题段 + 4 正文段）。

| 操作 | 耗时 | 备注 |
| --- | --- | --- |
| `epub2m4b inspect --json` | **0.16 s** | 含 zip 读取、epubx 解析、分章、清洗、分段 |

同尺寸的 fake-TTS 全流程（60 章）在 e2e 中断测试里被反复执行，单次 `run` 在秒级；真实 Kokoro 端未实测（模型未下载）。

## 单段开销（fake 后端）

每段一次 `ffmpeg -f s16le → FLAC` 子进程，实测 <10 ms/段。段采样数校验直接读 FLAC STREAMINFO 的 36-bit 字段，无需 ffprobe。

## 容量估算（`util/disk.py`）

- `BYTES_PER_CHAR_FLAC = 5800`：FLAC 段缓存 + 临时 WAV 的保守上限。
- AAC 成品 ≈ 64 kbps ÷ (≈4.5 字/s) ≈ **1778 字节/字**。
- 预检：`(待合成字数 × 5800 + 全书字数 × 1778) × 1.3 ≤ 可用空间`，不足退出码 5。
- 30 万字书：缓存峰值约 1.74 GB，成品约 0.53 GB。

## 章节时间轴

`assemble/concat.build_timeline` 只累加整数采样数，`round(1000 × Σ/24000)` 在最后一步计算；`verify_output` 用 ffprobe 对照，容差 150 ms。e2e `test_chapter_starts_match_timeline` 断言零漂移。

## 重复运行

`tests/e2e/test_run_fake.py::test_rerun_is_fully_cached_and_voice_switch_resynthesizes`：

1. 第一次 run：全部新合成。
2. 第二次 run：`up to date`，不合成、不封装。
3. `--voice other`：全部重做（文本相同者仍命中缓存）。
4. 切回原 voice：`0 new`，仅重新封装一次（因为第 3 步覆盖了输出）。
5. 第五次 run：`up to date`。

`tests/e2e/test_resume.py::test_hard_kill_then_resume`：40 章书，SIGKILL 中断后重跑，已完成的段不重复合成。
