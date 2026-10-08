# lyrics-bibliomancy

一个面向 Codex 的本地歌词书占 skill：从用户自己持有的歌词文件建立语料库，固定抽取四行歌词，并结合歌曲语境、分级文学互文，以及按原句命中的小说／书信／创作谈材料进行文本式占读。

它不是塔罗、易经或歌词推荐器，也不把歌词中的“我”自动等同于词作者、演唱者或提问者。

## 特性

- 从 DOCX 导入歌曲与逐行歌词；从结构化 HTML 导入既有互文整理。
- 先等概率选歌、再等概率选四行，避免长歌获得更高抽中概率。
- 末尾不足四行时用向前补足的尾部窗口，保证新抽取始终是四行且不丢弃尾句。
- 写入不可重抽的本地抽取日志，可凭 `draw_id` 恢复同一次抽取。
- 将抽中四行作为解读中心；整首歌只用于校正局部语境，不以“歌曲主题”取代四行细读。
- 将文学互文单列：只补充实际命中的引用歌词句，不把同一首歌别处的典故带入当前解读。
- 区分逐句引用、歌名来源、整曲候选和宽泛联想；歌名来源可以出现，但不会冒充当前四行的直接引句。
- 支持按需补全互文：首次遇到未补全的命中条目时，检索原典、必要上下文与中文工作译文，并保留来源和不确定性。
- 在抽中段中按需细读日语语法、词义、字形与文字音韵；不把仅有歌词文本时的观察伪装成旋律或编曲分析。
- 可建立本地作品语境库：小说、书信、日记和创作说明不进入随机池；脚本仅在抽中四行出现精确触发词时返回最多两张 A/B 级卡，再由 Codex 回读详细材料。
- 区分成对文本、多说话者与非线性页序，不把后来的日记认识倒灌成较早书信当时已经知道的事实。

## 不包含的内容

此仓库不包含歌词、引用整理、抽取记录或互文补全资料。请只对你拥有合法使用权的本地文本运行工具，且不要把这些材料或其中可能包含的私人问题提交到公开仓库。

## 要求

- Python 3.10 或更高版本
- 无第三方 Python 依赖
- Codex（用于加载 `SKILL.md` 并执行文本解读工作流）

通用 `bibliomancy` skill 是可选协作项，不是运行依赖；缺少它时，本 skill 按自身的阅读与输出规则完成解读。

## 当前发布范围

当前版本已用 Yorushika 本地语料和对应整理格式验证。歌词 DOCX 导入是通用的；HTML 导入只保证兼容项目文档所述结构，不宣称支持任意网页。仓库不附带 Yorushika 歌词、小说、引用数据库或私人抽取记录。

## 安装

将此目录复制或克隆到 Codex skills 目录：

```text
<CODEX_HOME>/skills/lyrics-bibliomancy
```

Windows 默认位置通常为：

```text
C:\Users\<用户名>\.codex\skills\lyrics-bibliomancy
```

检查 skill 元数据：

```powershell
python -X utf8 "<CODEX_HOME>\skills\.system\skill-creator\scripts\quick_validate.py" `
  "<CODEX_HOME>\skills\lyrics-bibliomancy"
```

## 建立本地语料库

在 skill 目录以外新建一个数据目录。准备：

- 一份歌词 DOCX：歌曲标题须有可识别的较大字号；标题后的段落视为歌词行；
- 一份结构化 HTML：可选，用于导入已有的文学引用整理。

```powershell
python -X utf8 scripts/lyrics.py init `
  --data-dir "D:\lyrics-bibliomancy-data" `
  --lyrics-docx "D:\source\lyrics.docx" `
  --corpus-name "my-corpus"
```

如有结构化互文整理，使用包含可选参数的完整命令：

```powershell
python -X utf8 scripts/lyrics.py init `
  --data-dir "D:\lyrics-bibliomancy-data" `
  --lyrics-docx "D:\source\lyrics.docx" `
  --corpus-name "my-corpus" `
  --references-html "D:\source\literary-references.html"
```

然后检查导入报告：

```powershell
python -X utf8 scripts/lyrics.py --data-dir "D:\lyrics-bibliomancy-data" check
```

如报告出现未匹配标题、重复标题或格式警告，请如实处理；没有互文不是错误。

## 命令行使用

抽取一段歌词：

```powershell
python -X utf8 scripts/lyrics.py --data-dir "D:\lyrics-bibliomancy-data" draw `
  --question "我现在最该留意什么？" --with-reading-context
```

恢复同一次抽取的歌词：

```powershell
python -X utf8 scripts/lyrics.py --data-dir "D:\lyrics-bibliomancy-data" show `
  --draw-id "<draw_id>" --with-reading-context
```

查看该歌曲的导入互文卡：

```powershell
python -X utf8 scripts/lyrics.py --data-dir "D:\lyrics-bibliomancy-data" lookup `
  --draw-id "<draw_id>"
```

`--with-reading-context` 一次返回抽取、完整歌曲语境、互文候选、已有补全资料及作品语境卡，供 Codex 内部阅读。逐句互文和作品语境要求当前四行直接命中；明确登记的文学歌名来源会作为非逐句候选返回。`lookup` 返回歌曲级原始互文索引。

## 在 Codex 中使用

直接说，例如：

- “用歌词书占：我喜欢的人现在怎么看我？”
- “从我的歌词库抽一段，看这个项目会怎么走。”
- “继续用刚才那段歌词看它的文学引用。”
- “把这篇小说整理成歌曲的关联语境；不要加入随机抽取。”

新抽取会产生新的 `draw_id`。针对同一段歌词的追问必须沿用原 `draw_id`，不重新抽取。

完整的解读原则、输出格式、互文边界与按需补全流程见 [SKILL.md](SKILL.md)。

## 数据目录

`init` 会在你指定的数据目录创建：

| 文件 | 用途 |
|---|---|
| `library.json` | 歌曲、逐行歌词与内部歌曲 ID |
| `references.json` | 从 HTML 导入的原始互文索引 |
| `intertext_claims.jsonl` | 将含多部原典的条目拆成独立 claim 的可选校正层 |
| `sources.json` | 源文件路径与 SHA-256 |
| `parse_report.json` | 导入报告与警告 |
| `draws.jsonl` | 抽取日志；可能含私人问题 |
| `intertext_enrichment*.jsonl` | 按需补全的互文资料及 addendum；仅在使用该流程后出现 |
| `language_notes.jsonl` | 按需补充的语言研究笔记；仅在使用该流程后出现 |
| `作品关联语境总索引.md` | 小说、书信、日记与创作谈的人工阅读总入口 |
| `work_context_index.jsonl` | 按歌曲和四行内精确日文触发词定位的机器索引 |

不要修改既有 `library.json`、`references.json` 或 `draws.jsonl` 来改变过去的抽取。更换歌词版本或修正切歌时，请使用新的数据目录。

## 测试

```powershell
python -X utf8 -m unittest discover -s tests -v
```

测试覆盖固定四行尾部窗口、多行 `／` 互文、标题级互文、非自动联想及 addendum 加载。

## 隐私与公开发布

请将数据目录置于仓库之外。尤其不要提交：

- 歌词 DOCX 与导入后的 `library.json`；
- 引用整理 HTML 与 `references.json`；
- `draws.jsonl`、`sources.json` 或互文补全文件；
- 含有私人问题、路径、账号或受版权保护长文本的测试样本。

本仓库的 `.gitignore` 已忽略这些常见文件名；提交前仍请检查 `git status`。

## 致谢与方法来源

本项目在设计之初受到 [Kico-Tachagemofet 的 Bibliomancy Reading · 书占解读法](https://github.com/Kico-Tachagemofet/bibliomancy-reading) 启发，尤其是把随机文本作为具体场景细读、区分文本证据与推测，并说明现实类比边界的做法。在此基础上，本项目针对歌词另行设计了本地建库、四行随机抽取、全歌局部校正、分级文学互文、日语语言研究与作品语境检索流程。感谢 Kico-Tachagemofet 提供最初的方法启发。

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目的代码与项目文档采用 [MIT License](LICENSE)。歌词、文学作品原文、用户整理的引文材料及本地数据不属于本仓库内容，也不包含在该许可证的授权范围内；这些材料仍受其各自权利人的权利约束。
