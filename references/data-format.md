# 数据文件

`init` 在技能目录外创建下列文件：

- `library.json`：歌曲、逐行歌词和内部歌曲 ID。
- `references.json`：可选引用 HTML 的原始条目。`curated` 表示非“※”整理条目；`speculative` 表示“※”或附录，均不表示创作者官方确认。
- `intertext_claims.jsonl`：可选的 claim 级校正层。一个原始条目包含多部作品或来源绑定不清时，用它拆分关系；不覆盖 `references.json`。
- `sources.json`：源文件路径和 SHA-256。
- `parse_report.json`：未匹配引用、重复标题与导入警告。
- `draws.jsonl`：不可重抽的抽取日志；每行一个 JSON 记录。
- `intertext_enrichment*.jsonl`：按需联网补全的互文资料；可分为主文件和 addendum。以 `entry_id` 关联，拆分过的条目再用 `claim_id` 精确关联。
- `language_notes.jsonl`：按需积累的语言研究笔记；以歌词行号和具体词句关联。它记录会改变解读的语法、语义、语域、字形或文字音韵现象，不是全库词典。
- `作品关联语境总索引.md`：小说、书信、创作谈等材料的人工阅读总入口；详细叙述和原文位置保留在这里及其指向的细读卡中。
- `work_context_index.jsonl`：作品关联语境的小型机器索引。`draw/show --with-reading-context` 先按歌曲 ID，再按抽中四行实际出现的日文触发词精确匹配，最多返回两张 A/B 级卡；它不参与随机抽取，也不写入 `draws.jsonl`。

用新数据目录处理新版本歌词。不要人工修改这些文件来改变已发生的抽取。

随机组始终是四行。歌曲末尾不足四行时，最后一组向前补足并与前组少量重叠；少于四行的歌曲保留在书库，但不进入随机抽取。

互文匹配分四级：

- `line_direct`：具体歌词句的引用或改写；只有抽中四行命中规范化锚点时返回。
- `title_source`：歌名明确取自原典；抽到该歌即返回，但标为歌名层，不冒充当前四行的直接引句。
- `work_level`：整曲构造候选；返回供内部核对，只有当前四行确有局部关系时才能展开。
- `association`：宽泛或作者个人联想；没有歌词锚点时不自动载入。

匹配会统一全半角、空白和普通标点，并把 `／`、斜线及换行拆成局部歌词锚点。它不会用模糊语义相似替代文本证据。

`intertext_claims.jsonl` 每行至少包含 `claim_id`、`entry_id`、`song_ids`、`relation_type`、`notes`、`sources` 和 `confidence`；`line_direct` 另写 `lyric_anchors`。补全资料若带 `claim_id`，只随对应 claim 返回，避免同一原始条目中的多部作品互相串线。

互文补全文件记录关联来源与使用方式、原典出处和必要上下文、中文工作译文及来源、检索链接与日期、不确定性说明。`line_direct` 必须记录歌词相对原典的改写动作；`title_source` 和 `work_level` 则明确没有逐句改写证据。不要把补全文件当作歌曲主题数据库。

`language_notes.jsonl` 的每条笔记应至少包含：歌曲 ID 与行号、词句、观察类型、文本版本条件、资料来源、说明和不确定性。只有该现象会改变抽中段读法时才建立笔记；不要批量分析全库。

`work_context_index.jsonl` 每行是一个 JSON 对象，至少包含：

- `context_id`：稳定且唯一的卡片 ID；
- `song_ids`、`titles`：关联歌曲；
- `source_kind`、`source_files`：来源类型与原文档案；
- `detail_file`、`anchor`：需要回读的详细材料及稳定位置；
- `evidence`：`A`（直接构造／强关联）或 `B`（强语境）；弱意象邻近不进入索引；
- `trigger_terms`：确实存在于歌词版本中的日文片段；只要当前四行没有命中，就不得返回此卡；
- `summary`、`use`、`limits`：叙述关系、局部用途和不得推出的结论；
- `chronology_note`：叙述者、页序或事件时间需要区分时的说明。

作品关联语境仍不能只凭同歌名命中；这条限制不同于经过明确登记的文学 `title_source`。成对作品必须分别标明 Amy 的信、Elma 的回忆／日期页与歌词说话者；日记页码顺序不得当作事件时间顺序。机器卡只定位，实际解读仍须回读 `detail_file` 指向的必要上下文。
