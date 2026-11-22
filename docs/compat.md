# 公版样书与播放器兼容矩阵

## 样书与来源

- 样书：鲁迅《阿Q正传》，九章，EPUB 3，每章一个 XHTML 文档和 `<h1>`，含导航和自绘封面。
- 正文为公版作品（鲁迅 1936 年去世）。生成脚本：`scripts/build_sample.py`。
- 文本来源（固定 commit）：<https://raw.githubusercontent.com/baooab/The-true-story-of-Ah-Q/1402397efe0e18f3d6dbaaecd628c76647aa1ba3/content.md>，取文日期 2026-11-21。该 Markdown 的 SHA256 为 `e6a6d42367cd1b741790b6a130e68ac3f5e5aa0a615c6593377fcdf3869032e5`（64,731 bytes）。
- Wikisource 原计划 URL <https://zh.wikisource.org/wiki/阿Q正傳> 在本次执行时多次请求超时，未能核实；因此没有把 Wikisource 作为本次来源，也未声称与其校对。
- 生成命令：
  ```bash
  .venv/bin/python scripts/build_sample.py \
    --source .scratch/path-c/aq-source.md \
    --font /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc \
    -o .scratch/path-c/aq-zhengzhuan.epub
  ```
- 本次产出 EPUB SHA256：`992700456b3d239b6cc022628fbb27bb8d82d5c2b0e42b41df39fafbb8d401b0`。该文件为本地样书，不作为 Git 提交；重复生成时 zip 时间戳可能改变 EPUB hash。
- 封面由脚本绘制 1200×1600 PNG（纯色底、金色边框、Q 形图案），用本机文泉驿字体绘制中文书名和作者；无第三方图片或封面素材。

## 分章与合成检查

- `epub2m4b inspect`：9 documents、9 toc entries、strategy=`nav`、9 chapters、0 skippable、21,911 chars、469 estimated segments，封面可识别。
- 合成：`epub2m4b-kokoro` 镜像（0.1.1 runtime，Kokoro 0.9.4 / torch 2.15.0+cu132），voice `zf_xiaobei`，CPU，命令为 `run /data/aq-zhengzhuan.epub --tts kokoro --voice zf_xiaobei -o /data/aq-zhengzhuan.m4b`。实际 `synth: 468 new, 1 cached, 0 failed`，最终 `wrote ... (82.7 min, 9 chapters)`；整段运行约 38 分钟（含首次模型加载），不据此推算 RTF。
- `ffprobe` 实测：总时长 **4963.240 s**（82 分 43.240 秒），文件 **36,989,015 bytes**，9 个章节；音频 AAC 24 kHz 单声道，另有 PNG 封面流（1200×1600）。章节起点（秒）与标题：

  | 起点 | 标题 |
  | ---: | --- |
  | 0.000 | 第一章 序 |
  | 373.295 | 第二章 优胜记略 |
  | 864.595 | 第三章 续优胜记略 |
  | 1384.960 | 第四章 恋爱的悲剧 |
  | 1997.605 | 第五章 生计问题 |
  | 2502.915 | 第六章 从中兴到末路 |
  | 3122.575 | 第七章 革命 |
  | 3695.940 | 第八章 不准革命 |
  | 4286.205 | 第九章 大团圆 |

- 本次 M4B SHA256：`7cc04a19c383586eb95c92ca354098576ad0c6c17ccbe9b500c7a25a85567319`。嵌入封面可由 ffmpeg 成功提取；文件不提交进仓库。
- 以上是 EPUB/M4B 结构和元数据实测，不等于播放器听测通过。

## 播放器矩阵

检查项：①章节列表与中文标题；②跳转落在标题音频开头；③封面显示；④总时长。

| 播放器 / 环境 | 版本与设备 | 章节标题 | 跳转 | 封面 | 总时长 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| VLC（桌面） | 本机未安装 VLC | 未测 | 未测 | 未测 | 未测 | 不能推断通过；ffprobe 已核实 9 章节、封面流和 4963.240 s |
| VLC（Android / iOS） | 无设备 | 未测 | 未测 | 未测 | 未测 | 不能推断通过 |
| Apple Books | 无设备 | 未测 | 未测 | 未测 | 未测 | 不能推断通过 |
| Smart AudioBook Player（Android） | 无设备 | 未测 | 未测 | 未测 | 未测 | 不能推断通过 |

`ffprobe` 的结构检查不能替代上述播放器的听测；无设备或未安装时保持「未测」。M4B 只作为 Release 附件，不提交进仓库。
