# 基准与容量

## 分章质量

本阶段先测量、后修复。2026-11-23 复测 5 本去重后的本地中文 EPUB（另有 1 本异常副本不计入，见下），5 本均通过显式 `SOUNDBOOK_CORPUS_MIN_F1=0.90` 闸门：均值 F1 `1.000`，最差 F1 `1.000`。逐章并列核对确认此前 4 本 `chapters_match=否` 全部是 skippable 辅文漏判，不是漏切或误切；修复见 ADR-022。结果只代表流程与结构覆盖验证，不足以支撑对外质量承诺。

本地执行命令：

```bash
SOUNDBOOK_CORPUS=/path/to/epubs pytest -m corpus -s
SOUNDBOOK_CORPUS=corpus SOUNDBOOK_CORPUS_MIN_F1=0.90 pytest -m corpus -s
```

`SOUNDBOOK_CORPUS_TOLERANCE` 默认 `1`；`SOUNDBOOK_CORPUS_MIN_F1` 只在显式设置时启用最差一本门槛，未设时只打印。F1 只统计生产路径会合成的非 skippable 章节，输出同时给出 skippable 章数。版本不符的金标逐本跳过，不参与评分。样本为 5 本不同的私有本地 EPUB，外加 1 本合成无 nav 样本（`8f96c9c1`，见表后说明）；`corpus/` 中另有 1 本重复/异常副本（2 个文档、占位 nav、最终合成单章）未标注、未计入统计。7 类目标结构在代码路径上已全部覆盖：完整 nav、卷级 nav、分层 nav、spine fallback、单文件多章、fragment 锚点、无 nav；前 6 类来自真实书，无 nav 由合成样本覆盖，真实无 nav 网文样本仍缺。

| EPUB SHA256 前 8 位 | 结构/策略 | F1 | 预测非 skippable | 金标 | skippable | 章节数一致 | anchor 警告 |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| `d615f98c` | 单文件多章 + fragment 锚点 + 分层 nav / nav | 1.000 | 165 | 165 | 3 | 是 | 0 |
| `dffe65b0` | 卷级 nav / nav | 1.000 | 10 | 10 | 3 | 是 | 0 |
| `c4827125` | 完整 nav / nav | 1.000 | 22 | 22 | 5 | 是 | 0 |
| `ecf98908` | fragment 锚点（8 个文档贡献多章）+ 分层 nav / nav | 1.000 | 34 | 34 | 6 | 是 | 0 |
| `3b10558e` | nav veto / spine fallback（含 6 个 fragment 锚点） | 1.000 | 18 | 18 | 5 | 是 | 0 |
| `8f96c9c1` | 无 nav 合成样本（123 文档、无导航文档、章节标题为纯文本段落）/ nav（epubx 合成 toc） | 1.000 | 120 | 120 | 3 | 是 | 0 |

`8f96c9c1` 是合成样本（2026-11-25），由 `scripts/build_nonav_sample.py` 现场生成：120 章、每章一个文档、cover/版权页/完本感言共 3 个辅文文档，正文为测试套件自带的原创填充文本，不含任何第三方正文。文件本身没有导航文档，但 epubx 会用 spine 合成 123 条 toc 条目，因此实际策略报告为 `nav`；`headings.txt` 为空，章节标题全部是文件名，生产路径下的行为与 spine 等价。金标按生成器已知的文档结构编写并人工核对。它是结构覆盖样本，**不是**真实网文：真实的「无 nav、多章合并进同一文档」网文仍缺样本，按 ADR-023 的风险说明，那种书在没有任何结构信号时按 spine 文档边界切分是预期行为，不承诺 F1。

`d615f98c` 的 16 个 spine 文档产出 168 章，其中 158 个 nav 条目带 `#fragment` 且均由锚点精确解析；`ecf98908` 的 43 个 nav 条目中 37 个带 fragment，8 个文档各贡献多章。两者共同验证了“单文件多章”和“fragment 锚点”两条路径，且没有触发 `anchor_text_fallback` / `anchor_unresolved`，因此 `anchor_warnings=0`。`3b10558e` 的 6 个 fragment 条目中 4 个可解析、2 个不可解析，但最终策略为 spine，故未产生 anchor 警告；这属于“未被选中的 nav”，不是降级切分。

`chapters_match=否` 的 4 本在前一版被归因为“标注口径差异”，本次逐章并列后确认：**边界全部一致，差异只在 skippable 判定**。旧 `classify_skippable` 只在首 2 章 / 末 1 章内看关键词，落在窗口外的目录、版权页、书名页（第 3、4 章）被当作正文；ADR-022 按 `docs/corpus.md` 的“版权页、目录页不算”改为非阅读页关键词全篇生效，并把匹配文本扩展到首段以覆盖 spine 的文件名标题。修复后 5 本全部 `chapters_match=是`。没有发现真实漏切或误切。

2026-11-25 按 ADR-023 复测同一 5 本（pipeline 0.3.0）：均值 F1 与最差 F1 均为 `1.000`。`3b10558e` 的“已出书目”一节按新规则从 skippable 改为正文（`书目` 不再全篇生效，只受后置窗口规则），金标相应去掉该行的 `[skippable]`；其余边界行与 skippable 计数不变。

另有一本公开可复现的《阿Q正传》样书用于结构/播放器 spike，不属于真实语料统计：`inspect` 实测 9 documents、9 toc entries、strategy `nav`、9 chapters、0 skippable、21,911 chars、469 estimated segments；Kokoro CPU 实测 `468 new, 1 cached, 0 failed`，输出 82.7 min / 9 chapters，VLC 3.0.23 技术解析识别 AAC、中文元数据、9 章和 PNG 封面，但人工显示/听测仍未完成，详见 [`compat.md`](compat.md)。其中 469 是段总数，1 段命中缓存，所以 468 + 1 = 469。

日期：2026-11-23，本机：Linux / Python 3.14.4 / ffmpeg 8.0.1；CPU：12th Gen Intel(R) Core(TM) i7-12700H，10 物理核 / 20 逻辑 CPU。语料测试只做解析与分章，不涉及 ffmpeg；机器信息用于对齐同一台测量机。

## 合成测试书

`tests/helpers.make_epub` 现场生成，60 章 × 约 514 字，合计 **30 840 字 / 300 段**（每章标题段 + 4 正文段）。

| 操作 | 耗时 | 备注 |
| --- | --- | --- |
| `epub2m4b inspect --json` | **0.16 s** | 含 zip 读取、epubx 解析、分章、清洗、分段 |

同尺寸的 fake-TTS 全流程（60 章）在 e2e 中断测试里被反复执行，单次 `run` 在秒级；真实 Kokoro 的吞吐以本文的 jobs A/B 实测为准。

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

## Kokoro 吞吐 A/B（jobs 1 vs 2）

日期：2026-11-22。两组使用同一台机器、同一 `epub2m4b-kokoro` 镜像、同一 voice、同一
2 章子集（3,962 字、74 段），各自 `docker run --rm` 新容器，并使用独立的
`SOUNDBOOK_HOME` 与 `SOUNDBOOK_CACHE_DIR`。两组均为 74 段新合成、0 cached、0 failed；
Hugging Face 权重已在本机缓存并以只读方式挂载，因此不含模型下载，但包含进程内首次加载。
音频由 `ffprobe` 核实为 864.595 s（14.4099 min），RTF 定义为墙钟秒数 / 音频秒数。

机器信息：Linux，Python 3.12 容器，12th Gen Intel(R) Core(TM) i7-12700H，10 物理核 / 20
逻辑 CPU，ffmpeg 由镜像提供。实际命令（`$PWD` 为仓库根）：

```bash
for jobs in 1 2; do
  /usr/bin/time -p docker run --rm --user "$(id -u):$(id -g)" \\
    -v "$PWD/.scratch/ab-path-c:/data" \\
    -v "$PWD/.scratch/spike2/hf:/data/hf:ro" \\
    -e HF_HOME=/data/hf -e HF_ENDPOINT=https://hf-mirror.com \\
    -e HF_HUB_DISABLE_XET=1 -e SOUNDBOOK_HOME=/tmp/state-j$jobs \\
    -e SOUNDBOOK_CACHE_DIR=/tmp/cache-j$jobs epub2m4b-kokoro \\
    run /data/aq-first-two.epub --tts kokoro --voice zf_xiaobei --jobs "$jobs" \\
    -o /data/ab-j$jobs.m4b
done
ffprobe -v error -show_entries format=duration .scratch/ab-path-c/ab-j1.m4b
```

| `--jobs` | 墙钟 | 音频时长 | RTF | 合成结果 |
| ---: | ---: | ---: | ---: | --- |
| 1 | 331.89 s | 864.595 s | **0.384** | 74 new / 0 cached / 0 failed |
| 2 | 486.36 s | 864.595 s | **0.563** | 74 new / 0 cached / 0 failed |

在这台 CPU 机器上，`--jobs 2` 反而比 `--jobs 1` 慢 46.5%。原因是
`src/soundbook/tts/kokoro_local.py` 在 jobs 大于 1 时对每个 worker 调用
`torch.set_num_threads(1)`；jobs 2 实际只让两个 worker 各用一个 torch 线程，而 jobs 1
允许单个 worker 使用 torch 的线程池。因此 CPU 本地运行默认建议 `--jobs 1`；不同 CPU、容器
配额或模型版本应重新测量。该结果是 2 章流程验证，不外推为所有书的保证。

## Spike 2：Kokoro 端到端

日期：2026-11-20。宿主 Python 3.14 无法安装 `kokoro==0.9.4`（要求 `<3.13`），改用 `python:3.12-slim` 容器。

| 项 | 观测值 |
| --- | --- |
| 镜像 | `epub2m4b-kokoro`，约 10.5 GB（torch 2.15.0、kokoro 0.9.4） |
| 样本 | 2 章 × 4 段 |
| 合成结果 | `synth: 6 new, 4 cached, 0 failed` |
| 输出时长 | 70.1 s |
| 章节起点 | 0 / 35.100 s |
| 运行环境 | 纯 CPU；该次集成验证包含首次模型加载/环境准备，不作为吞吐基准 |

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
