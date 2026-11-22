# 本地语料与人工金标

## 隐私与运行方式

真实 EPUB、金标、标题清单和合成音频只留在用户本机，不进入 Git 仓库或 wheel。
将私有书放在被忽略的仓库根 `corpus/`，或仓库外的目录，再运行：

```bash
SOUNDBOOK_CORPUS=/path/to/epubs pytest -m corpus -s
```

`SOUNDBOOK_CORPUS_TOLERANCE` 是同文件内允许的块索引偏差，默认 `1`；
`SOUNDBOOK_CORPUS_MIN_F1` 是最差一本的 F1 门槛，默认 `0.90`。
测试不会写入用户的真实 `SOUNDBOOK_HOME`。CI 使用 `-m "not corpus"`，不会运行真实语料测试。

## 草稿与人工核对

对已安装开发环境的仓库运行：

```bash
.venv/bin/python scripts/corpus_draft.py /path/to/book.epub
```

脚本在 EPUB 旁生成两个文件；已有金标时默认拒绝覆盖，确认需要重做时才加 `--force`：

- `<stem>.boundaries`：预测边界草稿。首行 `# pipeline 0.1.0` 记录块索引所对应的
  `PIPELINE_VERSION`，其后每行 `<zip-relative-href>|<block-index> # 预测章节标题`。
  若 pipeline 与当前版本不一致，语料测试会显式跳过该书，不用旧块索引计算分数。
- `<stem>.headings.txt`：全部非空标题块，格式为 `<key>\t<标题文本>`。逐项核对，
  找出漏切和误切，再编辑 `.boundaries`。行尾 `#` 注释仅供人阅读，不是边界的一部分。

块索引是 loader 输出的序号，不是 XHTML 中原始元素序号。金标中的边界对应
`ChapterDraft.start_key`，不包含用于表示一章结束的 `end_key`。

## 标注规则

1. 每个阅读意义上的章节起点算一个边界，包括序、跋、附录。
2. 版权页、目录页不算。
3. 一个章节跨多个文件时只标首个文件。
4. 以正文内容为准修正草稿，不把导航中的错误层级直接当成金标。
5. 私有书及私有标注不提交，不把正文贴入 issue、日志或公开文档。

## 首批覆盖目标与记录

首批目标为 10–20 本人工复核书，覆盖：完整 nav 的出版社书、nav 只到卷级、无 nav
网文、单文件多章、fragment 锚点。类别汇总只报告书的数量、结构和分数，不报告私有书名。

| 书或 sha256 前 8 位 | 类型 | 来源（公版书填写 URL） | 人工复核 |
| --- | --- | --- | --- |
| 待用户本机补充 | 尚未提供可评测的真实语料 | — | 未完成 |

公开可复现的公版子集应先记录书名与原始文本 URL，再记录来源校验值；尚未取得并
人工复核的公版书不能计入样本量。2026-11-21 本机未设置 `SOUNDBOOK_CORPUS`，因此
这里不虚构首批书目或 F1 结果。
