# 第三方许可与再分发清单

本项目（`epub2m4b`，import 包 `soundbook`）本身以 **Apache-2.0** 发布，见仓库根目录 `LICENSE`。
**不分发任何 EPUB 文本、TTS 模型权重、语料或音频样本。** 测试用的 EPUB 全部由
`tests/helpers.py` 在测试时现场生成，内容为本项目自写的占位文本。

## 运行时依赖（随 `pip install epub2m4b` 安装）

| 包 | 锁定版本 | 许可 | 用途 |
| --- | --- | --- | --- |
| `epub-extended`（import 名 `epubx`） | `==0.2.3` | MIT | EPUB 解析，仅在 `src/soundbook/ingest/loader.py` 中 import |
| `lxml` | `>=5`（实测 6.1.3） | BSD-3-Clause | 分章锚点的二次解析兜底（`ingest/anchors.py`） |
| `click` | `>=8`（实测 8.5.1） | BSD-3-Clause | CLI |
| `filelock` | `>=3`（实测 4.2.12） | MIT | 书级互斥锁 |

`epub-extended` 是 0.x 版本，因此**精确锁定**到 0.2.3；升级前必须重跑测试套件。

## 可选依赖（`pip install 'epub2m4b[kokoro]'`）

| 包 | 版本 | 许可 | 说明 |
| --- | --- | --- | --- |
| `kokoro` | `==0.9.4` | Apache-2.0 | 本地 TTS 引擎（惰性 import） |
| `misaki[zh]` | `==0.9.4` | Apache-2.0 | 中文 G2P；`[zh]` extra 需在目标环境验证 |

Kokoro 模型权重（`hexgrad/Kokoro-82M`）由用户在首次运行时从 Hugging Face 下载，
**不随本项目分发**。模型权重与音色有自己的使用条款，使用者自行确认。

## 外部程序（用户自行安装，不由 pip 拉取）

- **ffmpeg / ffprobe**：段 FLAC 编码、concat、AAC 封装、响度测量。LGPL/GPL 取决于用户的构建；
  本项目只通过命令行调用，不链接、不分发其二进制。
- 任何 OpenAI 兼容 TTS 端点（CosyVoice 包装、vLLM 等）：由用户自行部署，本项目只发 HTTP 请求。

## 开发依赖

- `pytest`（MIT）— 测试。
- 无其他构建期依赖；构建后端为 `setuptools`（MIT）。

## 语料与版权

- `tests/corpus/` 需要用户通过 `SOUNDBOOK_CORPUS` 指向自己的 EPUB 目录，**仓库不含任何真实书籍**。
- 用户对自己输入的 EPUB 及生成的音频承担版权责任（见 `docs/limitations.md`）。
