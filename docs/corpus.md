# 本地语料与人工金标

## 隐私与运行方式

真实 EPUB、金标、标题清单和合成音频只留在用户本机，不进入 Git 仓库或 wheel。
将私有书放在被忽略的仓库根 `corpus/`，或仓库外的目录，再运行：

```bash
SOUNDBOOK_CORPUS=/path/to/epubs pytest -m corpus -s
```

`SOUNDBOOK_CORPUS_TOLERANCE` 是同文件内允许的块索引偏差，默认 `1`。
`SOUNDBOOK_CORPUS_MIN_F1` **默认不设**：只打印每本与汇总分数，不判失败；需要回归闸门时显式设置，例如：

```bash
SOUNDBOOK_CORPUS=corpus SOUNDBOOK_CORPUS_MIN_F1=0.90 pytest -m corpus -s
```

设了门槛才断言最差一本达到该值。版本不符的金标会逐本跳过并打印原因，不会让其余书的分数一起消失。
测试不会写入用户的真实 `SOUNDBOOK_HOME`。CI 使用 `-m "not corpus"`，不会运行真实语料测试。

F1 只统计生产中会合成的非 skippable 章节；预测集先调用与 `run` 相同的 `classify_skippable`
规则，再按 `ChapterDraft.start_key` 计分。金标只含正文边界（版权页、目录页不算）。
输出中的 `skippable` 是排除的章节数，应与金标章节数一起核对，避免把辅文误判成漏切。

## 草稿与人工核对

对已安装开发环境的仓库运行：

```bash
.venv/bin/python scripts/corpus_draft.py /path/to/book.epub
```

脚本在 EPUB 旁生成两个文件；已有金标时默认拒绝覆盖，确认需要重做时才加 `--force`：

- `<stem>.boundaries`：预测边界草稿。首行 `# pipeline 0.2.0` 记录块索引所对应的
  `PIPELINE_VERSION`，其后每行 `<zip-relative-href>|<block-index> # 预测章节标题`。
  与生产路径一致的 skippable 章节会在标题后标 `[skippable]`（例如
  `OEBPS/Text/ch1.xhtml|0 # 目录 [skippable]`），表示该行不会被计入 F1，不要把它当成漏切。
  若 pipeline 与当前版本不一致，语料测试会显式跳过该书，不用旧块索引计算分数。
- `<stem>.headings.txt`：全部非空标题块，格式为 `<key>\t<标题文本>`。逐项核对，
  找出漏切和误切，再编辑 `.boundaries`。普通行尾 `#` 注释仅供人阅读，不是边界的一部分；
  草稿生成的 `[skippable]` 标记是例外，表示该边界明确排除在 F1 外。

块索引是 loader 输出的序号，不是 XHTML 中原始元素序号。金标中的边界对应
`ChapterDraft.start_key`，不包含用于表示一章结束的 `end_key`。`.boundaries` 文件存在但去掉注释后
没有任何边界时，测试会明确失败并指出文件；完全没有文件才算「未标注」，整条测试会 skip。

## 标注规则

1. 每个阅读意义上的章节起点算一个边界，包括序、跋、附录。
2. 版权页、目录页不算。
3. 一个章节跨多个文件时只标首个文件。
4. 以正文内容为准修正草稿，不把导航中的错误层级直接当成金标。
5. 私有书及私有标注不提交，不把正文贴入 issue、日志或公开文档。

## 首批覆盖目标与记录

本阶段已用 **5 本**去重后的人工复核书跑通闭环（草稿 → 核对 → 测量）；验证工具与流程后再扩到
10–20 本。7 类目标结构已覆盖 6 类：完整 nav、卷级 nav、分层 nav、spine fallback、单文件多章、
fragment 锚点；真实“无 nav 网文”仍缺合格样本。类别汇总只报告 SHA256 前 8 位、结构和分数，
不报告私有书名。

记录每本时增加 `skippable` 章数，并核对「预测的非 skippable 章数 + skippable 章数」与
猜测的原始章节总数、以及金标章节数是否一致；这样「多切/少切/错位」可以分开判断。
F1、策略、anchor 警告数之外，结果表如下：

| 书或 sha256 前 8 位 | 结构 | 来源（公版书填写 URL） | F1 | 策略 | anchor 警告 | skippable | 章节数一致 | 人工复核 |
| --- | --- | --- | ---: | --- | ---: | ---: | --- | --- |
| `d615f98c` | 单文件多章 + fragment 锚点 + 分层 nav | — | 1.000 | nav | 0 | 3 | 是 | 已核对 |
| `dffe65b0` | 卷级 nav | — | 1.000 | nav | 0 | 3 | 是 | 已核对 |
| `c4827125` | 完整 nav | — | 1.000 | nav | 0 | 5 | 是 | 已核对 |
| `ecf98908` | fragment 锚点 + 分层 nav | — | 1.000 | nav | 0 | 6 | 是 | 已核对 |
| `3b10558e` | nav veto / spine fallback（含 fragment 锚点） | — | 1.000 | spine | 0 | 6 | 是 | 已核对 |
| 异常副本（未计入） | 无标题证据、2 文档、占位 nav | — | — | spine | — | 0 | — | 未纳入 |

`d615f98c` 有 16 个 spine 文档、168 章，158 个 fragment 锚点全部精确解析；`ecf98908` 的
37 个 fragment 锚点解析、8 个文档各贡献多章。这两本覆盖了“单文件多章”和“fragment 锚点”。
`3b10558e` 的 6 个 fragment 条目中 2 个不可解析，但最终走 spine，不影响切分。

公开可复现的公版子集应先记录书名与原始文本 URL，再记录来源校验值；尚未取得并
人工复核的公版书不能计入样本量。私有 EPUB 和金标仍不提交 Git；本表只保留 SHA256 前 8 位、
结构、分数和人工核对状态。
