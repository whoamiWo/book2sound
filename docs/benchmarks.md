# 基准与容量

## 分章质量

本阶段先测量，不修分章。截至 2026-11-21，本机没有设置 `SOUNDBOOK_CORPUS`，也没有已人工复核的首批真实书金标，因此**没有可报告的真实语料 F1、策略命中统计或最差书目原因**；不得把公开样书或虚构结果计入首批样本。

本地执行命令：

```bash
SOUNDBOOK_CORPUS=/path/to/epubs pytest -m corpus -s
```

计划中的首批样本量为 10–20 本，`SOUNDBOOK_CORPUS_TOLERANCE` 默认 `1`，`SOUNDBOOK_CORPUS_MIN_F1` 默认 `0.90`。实际本数、各策略命中数、各类书 F1 和最差原因须在提供并人工复核金标后补测；版本不符的金标会跳过，不参与评分。首批覆盖目标包括完整 nav、卷级 nav、无 nav 网文、单文件多章和 fragment 锚点，但目前这些类别均未测量。

另有一本公开可复现的《阿Q正传》样书用于结构/播放器 spike，不属于真实语料统计：`inspect` 实测 9 documents、9 toc entries、strategy `nav`、9 chapters、0 skippable、21,911 chars、469 estimated segments；Kokoro CPU 实测 `468 new, 1 cached, 0 failed`，输出 82.7 min / 9 chapters，详见 [`compat.md`](compat.md)。

日期：2026-11-19，本机：Linux / Python 3.14.4 / ffmpeg 8.0.1。

## 合成测试书

`tests/helpers.make_epub` 现场生成，60 章 × 约 514 字，合计 **30 840 字 / 300 段**（每章标题段 + 4 正文段）。

| 操作 | 耗时 | 备注 |
| --- | --- | --- |
| `epub2m4b inspect --json` | **0.16 s** | 含 zip 读取、epubx 解析、分章、清洗、分段 |

同尺寸的 fake-TTS 全流程（60 章）在 e2e 中断测试里被反复执行，单次 `run` 在秒级；真实 Kokoro 端只有一次小样本观测，见下文“Spike 2：Kokoro 端到端”，不据此推算 RTF。

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

## Spike 2：Kokoro 端到端

日期：2026-11-20。宿主 Python 3.14 无法安装 `kokoro==0.9.4`（要求 `<3.13`），改用 `python:3.12-slim` 容器。

| 项 | 观测值 |
| --- | --- |
| 镜像 | `epub2m4b-kokoro`，约 10.5 GB（torch 2.15.0、kokoro 0.9.4） |
| 样本 | 2 章 × 4 段 |
| 合成结果 | `synth: 6 new, 4 cached, 0 failed` |
| 输出时长 | 70.1 s |
| 章节起点 | 0 / 35.100 s |
| 运行环境 | 纯 CPU，10 个短段约 10 分钟以上 |

注意事项：

- 样本只有 10 个短段，且包含模型首次加载，**只记录观测值，不推算 RTF**。
- 构建时使用了华为 PyPI 镜像；Hugging Face 需 `HF_ENDPOINT=https://hf-mirror.com` 加 `HF_HUB_DISABLE_XET=1`，否则 Xet CDN 下载挂起。
- 0.1.1 用仓库中提交的 `Dockerfile.kokoro` 复验通过，输出与上表一致（AAC 24 kHz 单声道，70.1 s，2 章）：
  ```
  docker build -f Dockerfile.kokoro --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple -t epub2m4b-kokoro .
  docker run --rm -v "$PWD:/data" -e HF_ENDPOINT=https://hf-mirror.com -e HF_HUB_DISABLE_XET=1 \
    epub2m4b-kokoro run sample.epub --tts kokoro -o sample.m4b
  ```
- 首次构建较慢的两个原因：ffmpeg 带来 133 MB apt 包（deb.debian.org 当时约 50 kB/s）；PyPI 默认的 torch 2.15.0 附带约 3 GB CUDA（`nvidia-*`）wheel。镜像最终约 10.5 GB。
