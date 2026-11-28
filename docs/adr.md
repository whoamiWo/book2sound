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
3. **C（降级）**：仍对不齐时，在该 `href` 文件内按 nav 标题文本匹配 heading block，把原因写进 `rejected`。**绝不允许静默退化成"整文件当一章"**。实现细节见 ADR-020（2026-11-20 修订：匹配规则、理由取值与 B 级 4 字约束以 ADR-020 为准）。

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

## ADR-020 分章锚点降级（路径 C）：按标题文本回退，理由随章节记录

2026-11-20。ADR-015 第 3 级的落地决定，并修订 B 级。

- **回退位置**：只在 `chaptering._resolve_entry` 的 nav/outline 条目层。`anchors.resolve_anchor` 返回 None 的语义不变（该文档内无法定义此锚点，调用方当作文档首块）。
- **匹配规则**：`_match_heading` 在目标文档的 heading 中先做空白归一化后的精确匹配；其次才做前缀匹配，且两侧都必须不少于 4 字，避免单字标题（如“序”）误对齐。
- **理由取值**：`anchor_text_fallback`（按标题文本找到）和 `anchor_unresolved`（找不到，在文档起点切分）。写入 `Rejection(strategy, reason, {anchor,label,href,match})`。
- **B 级收紧**：`MIN_PREFIX_MATCH_CHARS=4`，较短一侧不足 4 字时只允许相等；`lxml_anchors` 加 `lru_cache(maxsize=32)`，避免对每个条目重复解析整份文档。
- **不吞理由**：`_build_drafts` 的位置去重与空章过滤会把被丢弃候选的理由并入下一个保留章节；`choose_strategy` 把 veto 拒因追加到 `draft.rejected`，不再整体覆盖。
- **呈现**：`anchor_*` 并入 `ChapterPlan.warnings`，不新增顶层字段。`inspect` 文本模式单独打印 warnings 并让 `rejected` 行排除 `anchor_*`，因为降级切分不是策略被否决；`--json` 的 `rejected` 与 `warnings` 都保留 `anchor_*`。`run` 在 prepare 之后向 stderr 输出 `warning: chapter N: anchor_*`。

## ADR-021 发布走 PyPI Trusted Publishing，不再保存 API token

2026-11-20。0.1.0 上传时 TestPyPI token 被误存为 PyPI token，导致 403；同时账号级 token 权限过宽。

- **机制**：`.github/workflows/release.yml` 在 push `v*` tag 时触发。`build` job 只构建一次 `dist/`，校验 tag、`pyproject.toml` 版本与 wheel 内 `soundbook.__version__` 三者一致；`testpypi` 与 `pypi` job 下载同一份 artifact 上传，保证两侧逐字节相同。
- **鉴权**：GitHub OIDC（`permissions: id-token: write` 仅给两个上传 job，工作流顶层为 `contents: read`），仓库与 GitHub secrets 中不存放任何长期凭据。
- **人工闸门**：`pypi` job 依赖 `testpypi`，并使用 GitHub environment `pypi` 的手动批准，作为不可逆上传前的确认。
- **供应链**：`actions/*` 与 `pypa/gh-action-pypi-publish` 均固定到具体 commit SHA，不用浮动 tag。
- **前置（网页配置）**：PyPI 与 TestPyPI 的 `epub2m4b` 项目各添加一个 Trusted Publisher（owner `whoamiWo`、repo `book2sound`、workflow `release.yml`、environment 分别为 `pypi` / `testpypi`），GitHub 仓库创建同名 environment。配置生效后撤销账号级 token 与 TestPyPI token。
- **失败处理**：tag 先于上传创建；若 `build` 或 `testpypi` 失败，修复后发下一个补丁版本，不移动已推送的 tag。若仅 `pypi` job 失败（`testpypi` 已成功），在 GitHub 上只 Re-run failed jobs——整条重跑会因 TestPyPI 拒绝重复文件名而失败。

## ADR-022 辅文判定：非阅读页按关键词全篇跳过，阅读章节仍限首末窗口

2026-11-23。5 本语料的 `chapters_match=否` 全部不是漏切/误切：逐章并列后，预测边界与金标 100% 对齐，差异只在 `classify_skippable` 的辅文判定。`docs/corpus.md` 标注规则明确「版权页、目录页不算」，但旧实现把关键词命中也限制在前 2 章 / 后 1 章窗口内，落在窗口之外的书名页、版权页、目录页（如第 3、4 章）会被当作正文合成。

- **两类关键词分开**：`NON_READING_KEYWORDS`（目录、扉页、版权、书名页、cover、title page、contents、copyright、colophon、书目）全篇命中即跳过，不再受窗口限制；`FRONT_KEYWORDS` / `BACK_KEYWORDS`（前言、序、引言、楔子、后记、附录、致谢、参考文献、番外等）保持标题命中 + 窗口规则；短章仍按既有首末窗口桩长度规则处理。
- **匹配文本**：非阅读页关键词检查「标题 + 第一段」，因为 spine fallback 下章节标题可能退化为文件名（如 `part0001.html`），而「版权页」「目录」只出现在正文第一段；前言/后记等阅读内容关键词仍只检查标题并受首末窗口限制，避免正文首段偶然提到这些词时误跳过。
- **语料复核**：同一 5 本（结构不变，块索引不变）重测 F1 全部 1.000，之前 4 本 `chapters_match=否` 全部消除；百年孤独的编辑导言此前被人工标为 skippable，与规则 1「序算章节」冲突，金标已统一为正文。
- **版本**：这是分章输出语义变化，`PIPELINE_VERSION` 升 `0.2.0`（包版本同步 0.2.0）；块索引未变，旧金标经重生成核对后更新版本头继续可用。除百年孤独编辑导言的一处 skippable 标记更正外，其余边界行保持一致。

## ADR-023 短书分类：非阅读页标记仍生效，首段只认前缀，全跳过有兜底

2026-11-25。ADR-022 把非阅读页判定扩展到全篇后暴露出两个缺陷：`n <= 2` 的提前返回让 1–2 章的书完全不分类，而 `_probe` 把标题与首段拼成一个字符串做无限制子串匹配，正文首段“他翻开目录，检查版权归属……”会被误判成辅文。

- **`n <= 2` 守卫**：保留，但只跳过 stub 与首末窗口规则。原始目的是防止整本短书被 `STUB_CHARS=300` 全部吃掉；非阅读页（目录、版权页、扉页、书名页等）在短书中仍然全篇生效，因为这些页面本来就不该朗读。
- **首段匹配改前缀**：标题仍用 `keyword in title` 子串匹配（标题是元数据）；首段必须 `startswith(keyword)`，先按 `_squash` 去掉全部空白并小写化。正文提到“目录/版权”不再命中，独立的“目录”“版权所有 © …”仍然命中。`Table Of Contents` 这类英文标记以完整短语加入 `NON_READING_KEYWORDS`，而不是回退到无限制子串。
- **`书目` 移出全篇规则**：`书目` 从 `NON_READING_KEYWORDS` 移到 `BACK_KEYWORDS`，中段书目作为可听附录保留，只有落在后置窗口内才跳过。`参考文献` 同样保持窗口规则。
- **全跳过保护**：分类结束后若 `all(d.skippable)`，清空所有 `skippable`。skippable 章节不生成分段（`pipeline.py` 的 `if include_skippable or not draft.skippable`），整本被跳过会让 `run` 以“nothing was synthesized; there is no audio to package”退出码 2；宁可多合成一章，也不产出空结果。该事件不新增 warnings 通道（`classify_skippable` 先于 `ChapterPlan.warnings` 构建，改动签名超出本轮最小修复），只在 docstring 与本 ADR 固定。
- **语料与版本**：5 本复测 F1 仍全部 `1.000`；`3b10558e` 的“已出书目”由 skippable 改为正文，金标相应去掉 `[skippable]`（标注口径随规则更新，不是回退代码）。这是分章选择语义变化，`PIPELINE_VERSION` 升 `0.3.0`（包版本同步）；块索引未变，金标版本头统一更新到 `0.3.0`。

## ADR-024 运行鲁棒性：锁前置、孤儿段清理、惰性模型加载与中断即取消

2026-11-28。审计发现四处与既有决定相悖的实现缺陷，一并固定处理方式。

- **锁前置**：`run` 原本在 `prepare()` 之后才取书级锁，两个并发进程会同时重写 `chapters`/`segments`。
  现在先用 `book_id_from_path`（与 `prepare` 同源的 sha256）算 book_id，取锁成功后再写库；
  锁被占时以退出码 1 报“another epub2m4b process is already working on this book”，不再走
  `main()` 的兜底“unexpected error”。
- **孤儿段清理**：章节数减少（策略切换/合并/去重）后，旧 `segments` 行无任何 chapter 归属，
  会被 `pending_segments` 反复捞起重做。`replace_chapters` 末尾删除
  `chapter_idx NOT IN (SELECT ... FROM chapters)` 的段行；段 FLAC 仍在内容寻址缓存里，
  文本再现时零合成复用（ADR-013 语义不变）。
- **标题只砍“切点所在块”**：`_build_drafts` 原先丢弃跨度内遇到的第一个 heading，fragment
  锚点落在正文段落时会把随后的 `<h2>` 当章节标题静默吞掉。现改为仅当切点块本身是
  heading 才跳过。这改变 fragment 切分书目的章节正文，属分章输出语义变化：
  `PIPELINE_VERSION` 升 `0.3.1`（包版本同步）；边界（`start_key`）不变，本地金标只更新版本头。
- **Kokoro 惰性加载**：`run` 为读 `EngineInfo` 构造的探针实例原先就把 KPipeline 加载进内存，
  合成 worker 又各自加载一份，jobs=1 时整本书运行期间内存里存在两份模型。
  改为构造与 `info()` 均不建 pipeline（`info()` 只 import kokoro 取版本，保持 exit 4 语义），
  首次 `synth` 才加载。
- **中断即取消**：`ThreadPoolExecutor` 上下文退出会等待全部已提交任务，Ctrl-C 形同虚设。
  捕获 `BaseException` 后 `cancel()` 未开始任务并 `shutdown(wait=False, cancel_futures=True)`；
  最多 `jobs` 个进行中的段按 Python 线程语义跑完当前合成，队列不再继续。
- **成品自校验**：`assemble_m4b` 写完 M4B 后即跑 `verify_output`（ffprobe，150 ms 容差），
  偏差进入 `AssembleResult.warnings` 由 CLI 打印，而不是只在测试里校验（接受表 §5 的运行期落地）。
  非 JPEG/PNG 封面（webp/gif/bmp）转码为 MJPEG 再作 attached_pic，避免 mp4 muxer 直接失败。
