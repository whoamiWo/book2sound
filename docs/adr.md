# 决策记录（ADR）

格式：**只追加，不删改**。每条记录"决定 + 理由 + 影响"。编号与《中文 EPUB → 带章节 M4B 生成器 · 最终方案 v4》第 2 节连续。

---

## ADR-001 赛道：做生成器，不做播放器

播放器侧已有成型项目，切换成本高、稳定性难超越；生成器的"中文 EPUB 分章 + 可恢复离线生成"仍有空白。

**影响**：产物交给 Apple Books / VLC / mpv / 任何支持章节的播放器。

## ADR-002 形态：CLI 优先，单进程 + SQLite

不引入 FastAPI / Celery / Redis。原方案在同一份文档里既说"CLI 优先"又说"FastAPI 编排层"，二者冲突，以 CLI 为准。

## ADR-003 TTS 基线：Kokoro 默认，CosyVoice 经 `openai_compat`

Kokoro 默认（CPU 可跑，进程内）；CosyVoice 3 通过 `openai_compat` 由用户自备端点。理由：v0 必须让任何人在任何机器上跑通全链路，GPU 不能是前置条件。

## ADR-004 状态粒度：book → chapter → segment

segment 是最小重试与最小失效单位。章级重试在 CPU 上意味着几十分钟白跑。

## ADR-005 中间音频格式：段 = FLAC（24 kHz mono 16-bit），无章/全书中间文件

成品 = AAC 64k。段文件是续跑缓存必须常驻，任何额外中间层都叠加峰值占用。30 万字书峰值估算 ≈ 2.1–2.4 GB。

## ADR-006 写序：先落盘并 fsync，再改 DB 状态

反向（先写 DB）会在崩溃后留下"DB 说 done、文件半截"，不可自愈。

**实现**：`util/atomic.py` 写 `.tmp` → `fsync` → `os.replace`；`db.mark_done()` 只在此之后调用。

## ADR-007 指纹失效：`audio_key = sha256(tts_input_text ‖ synth_fingerprint)`

`synth_fingerprint` 纳入 `(backend, model_id, model_version, voice, rate, sample_rate, audio_format_version)`，**不含 `pipeline_version`**。

理由：否则改清洗规则或换音色重跑，旧段仍 `done`，产出混着新老规则且"看起来成功"。

## ADR-008 不内建爬虫 / 书源

法律风险与维护成本都不划算，且不服务于"EPUB 进 M4B 出"这条链路。

## ADR-009 许可证：Apache-2.0

专利授权对下游友好。ffmpeg 通过 `subprocess` 调用，属独立进程聚合，不改变本项目许可证；Docker 镜像内 ffmpeg 组件须单独声明其 GPL/LGPL 许可。

## ADR-010 遥测：无

默认不发任何网络请求（`openai_compat` 只在用户显式指定 `--tts openai` 时联网）。

## ADR-011 自建而非给 audiblez 提 PR

audiblez（Kokoro + ebooklib、逐章 WAV）在中文场景缺三件事——fragment 级分章、段级续跑、参数变更最小重算；三者都要求重写其数据模型（从"逐章 WAV"改为"段级状态库"），不是一个 PR 的体量。**对外口径**：不贬低竞品，只发布可复现的对比，并在 README 致谢其 ffmpeg 参数思路。

## ADR-012 分段确定性

分段 = `f(clean_text, SegmentPolicy)` 纯函数，不读运行时状态。任何"自适应"只能产出建议，不能改变边界。理由：边界一变，续跑与缓存全部失效。

## ADR-013 段音频内容寻址

`audio_key = sha256(tts_input_text ‖ synth_fingerprint)`。局部文本改动只重合成真正变化的段；跨书相同句子（如"第一章"）天然复用；失效逻辑从"级联置 pending"简化为"key 不存在即合成"。

---

## ADR-014 命名：发行名 `epub2m4b`，import 包 `soundbook`

PyPI 上 `soundbook` 已被占用（0.0.4，erfansamandarian，2024-06），且其 CLI 命令也叫 `soundbook`（`soundbook --url ...`），在用户机器上会真的撞命令。

- 发行名（PyPI）：`epub2m4b`
- CLI 命令：`epub2m4b`
- 内部 import 包：`src/soundbook/`（私有，不对外暴露）
- 环境变量前缀：`SOUNDBOOK_HOME` / `SOUNDBOOK_CACHE_DIR`（不与对方冲突）
- 项目目录：`/home/who/soundbook` 不变

**影响**：`pyproject.toml` 写 `name="epub2m4b"`、`[project.scripts] epub2m4b="soundbook.cli:main"`；所有文档示例统一为 `epub2m4b`。发布前仍须用 `curl -s https://pypi.org/pypi/epub2m4b/json` 二次确认。

## ADR-015 分章锚点：优先 `Block.attributes["dom_ids"]`，lxml 二次解析作兜底

**对 v5 计划 C2 的事实更正（2026-11-19，实测 `epub-extended==0.2.3`）**：`Block.id` 确实是位置式 `"c0000/b0003"`，但 block 的 `attributes["dom_ids"]` **暴露了该 block 拥有的全部 DOM id**（`epubx/content.py:_claim_stray_ids`：未直接落在 block 元素上的 id 会被归给最近的祖先 block）。因此 6.1 的"结局 A"实际可用，无需对每个 anchor 都做 lxml 重解析。

决定（三级，全部记录到 `chapters.rejected` / `inspect` 输出）：

1. **A（首选）**：用 `dom_ids → block ordinal` 索引解析 `href#anchor`。
2. **B（兜底）**：A 区没有该 anchor 时，用 lxml 直接解析 `book.resource(spine_href).read()` 得到的字节，取 `//*[@id]` 出现顺序，与 epubx block 序列按"归一化后 20 字前缀"对齐。
3. **C（降级）**：仍对不齐时，在该 `href` 文件内按 nav 标题文本匹配 heading block，标记 `strategy=nav+hybrid` 并把原因写进 `rejected`。**绝不允许静默退化成"整文件当一章"**。

`spine_href` 一律使用 `book.spine` 的原始相对路径（不用 `ch.id`）；跨文件边界靠 `spine_href` 区分。

## ADR-016 音频 I/O：soundfile 不可用，改用 ffmpeg + FLAC STREAMINFO

v5 计划 §3.9 把 spike 3 降级为安装检查：`soundfile` 不可用则段音频直接走 ffmpeg 子进程。

本机实测（2026-11-19）：Python 3.14 + 当前索引下 `soundfile` 依赖 `numpy`，下载反复中断；而 ffmpeg 是硬依赖（concat + AAC）。因此：

- 段音频写入：Python 生成 PCM → `ffmpeg -f s16le` 转 FLAC。
- 段采样数校验：直接解析 FLAC `STREAMINFO` 的 36-bit total-samples 字段（`util/audio.flac_total_samples`），精确且零依赖，比 `soundfile.info().frames` 更快。
- `soundfile` 不再列入核心依赖；`numpy`/`torch` 只在 `[kokoro]` extra。

**影响**：少两个重依赖；代价是每段多一次极短的 ffmpeg 进程（fake 路径下每段 <10 ms）。

## ADR-017 章节时间轴：标题前置静音归上一章

- 第 0 章**无**前置静音，`START(ch0) = 0`。
- 第 N（N>0）章标题前插 1200 ms 静音；`START(chN)` = 该章标题音频第一个采样点，**不含**前置静音。
- 因此第 N 章的 `[START(chN), END(chN))` 区间天然包含"下一章标题前的 1200 ms"。
- 最后一章末尾补 1200 ms，`END(last)` = 全书总时长。
- 时间戳只由整数 `n_samples` 累加，最后一步 `round(1000 × Σsamples / 24000)`；禁止逐段取整累加。

理由：否则每章开头先播 1.2 s 静音，且 `ffprobe` 偏差校验会整章偏 1200 ms。

## ADR-018 失败段可在下一次运行重试，不是终态

规范 §5 把 segment 定义为最小重试单位。初版实现把 `failed` 当成终态：
`pending_segments()` 只取 `status='pending'`，导致"引擎临时故障 → 修复引擎 → 重跑"
永远卡在 `book is incomplete`。

决定：`pending_segments()` 取 `status IN ('pending','failed')`；`prepare()` 的重对齐
只重置文本或合成指纹变化的行，因此失败行会被自然捞起。一次运行内的重试次数
仍由 `--max-retries` 限制（默认 3），失败行继续写入 `error` 供 `status` 展示。

**影响**：`test_failed_segment_is_retried_on_next_run` 验证；`--allow-incomplete`
仍封装已完成部分并退出 2，但全书零完成段时直接报错退出 2，不再产生空 M4B。

## ADR-019 Kokoro 语言码由音色推导，音色表随包发布

`KPipeline(lang_code=...)` 必须与音色语言一致，否则中文音色配英文 G2P 会产出错误发音。
`tts/voices.py` 内置 Kokoro-82M 音色表（仅 id/语言/性别元数据，无权重无音频），
`lang_code_for()` 按音色前缀推导，未知音色回退 `z`，`SOUNDBOOK_KOKORO_LANG` 可覆盖。
`epub2m4b voices [--lang z] [--json]` 不下载模型即可列出。
