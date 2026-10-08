#!/usr/bin/env python3
"""Local corpus tooling for lyrics-bibliomancy. Uses only the Python standard library."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import secrets
import sys
import unicodedata
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def title_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[\s\-‐‑–—・、。！？!?'’\"（）()\[\]【】]", "", value)


def title_keys(value: str) -> set[str]:
    """Return the complete title and a title without a parenthetical reading."""
    base = re.split(r"[（(]", value, maxsplit=1)[0].strip()
    return {title_key(value), title_key(base)}


def paragraph_text(node: ET.Element) -> str:
    return "".join(t.text or "" for t in node.iter(f"{W}t")).strip()


def is_title(node: ET.Element) -> bool:
    sizes = []
    for size in node.iter(f"{W}sz"):
        try:
            sizes.append(int(size.attrib.get(f"{W}val", "0")))
        except ValueError:
            pass
    return any(size >= 30 for size in sizes)


def read_docx_songs(path: Path, corpus_name: str) -> tuple[list[dict[str, Any]], list[str]]:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs = root.findall(f".//{W}body/{W}p")
    songs: list[dict[str, Any]] = []
    warnings: list[str] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        if current_title and current_lines:
            songs.append({"title": current_title, "lines": current_lines[:]})
        elif current_title:
            warnings.append(f"标题“{current_title}”没有可用歌词行。")
        current_title, current_lines = None, []

    for paragraph in paragraphs:
        text = paragraph_text(paragraph)
        if not text:
            continue
        if is_title(paragraph):
            flush()
            current_title = text
            continue
        if current_title is None:
            # The source document begins with an unformatted song title.
            current_title = text
        else:
            current_lines.append(text)
    flush()

    if not songs:
        raise ValueError("未能在 DOCX 中识别任何歌曲；请检查标题格式。")
    result = []
    seen: dict[str, int] = {}
    for index, song in enumerate(songs, 1):
        key = title_key(song["title"])
        seen[key] = seen.get(key, 0) + 1
        result.append({
            "song_id": f"{corpus_name}-{index:03d}",
            "title": song["title"],
            "title_key": key,
            "occurrence": seen[key],
            "lines": [{"number": n, "text": line} for n, line in enumerate(song["lines"], 1)],
        })
    for key, count in seen.items():
        if count > 1:
            duplicate = next(song["title"] for song in result if song["title_key"] == key)
            warnings.append(f"标题“{duplicate}”出现 {count} 次；已用 occurrence 区分，建议日后补充专辑或版本。")
    return result, warnings


class ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[dict[str, Any]] = []
        self.section_id = ""
        self.section_name = ""
        self.current: dict[str, Any] | None = None
        self.capture: str | None = None
        self.depth = 0
        self.buffer: list[str] = []

    @staticmethod
    def classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        return set(dict(attrs).get("class", "").split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = self.classes(attrs)
        if tag == "section" and "collection" in classes:
            self.section_id = attr.get("id", "")
        if tag == "article" and "entry" in classes:
            self.current = {"entry_id": attr.get("id", ""), "section_id": self.section_id,
                            "section": self.section_name, "title": "", "notes": [],
                            "lyric_excerpts": [], "sources": [], "quotes": []}
        if not self.current:
            if tag == "h2":
                self.capture, self.depth, self.buffer = "section", 1, []
            return
        if tag == "h3":
            self.capture, self.depth, self.buffer = "title", 1, []
        elif tag == "p" and "note" in classes:
            self.capture, self.depth, self.buffer = "note", 1, []
        elif tag == "div" and "lyric" in classes:
            self.capture, self.depth, self.buffer = "lyric", 1, []
        elif tag == "p" and "source" in classes:
            self.capture, self.depth, self.buffer = "source", 1, []
        elif tag == "blockquote" and "quote" in classes:
            self.capture, self.depth, self.buffer = "quote", 1, []
        elif self.capture:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.capture:
            self.depth -= 1
            if self.depth == 0:
                text = " ".join("".join(self.buffer).split())
                if self.capture == "section":
                    self.section_name = text
                elif self.current and text:
                    field = {"title": "title", "note": "notes", "lyric": "lyric_excerpts",
                             "source": "sources", "quote": "quotes"}.get(self.capture)
                    if field == "title":
                        self.current[field] = text
                    elif field:
                        self.current[field].append(text)
                self.capture, self.buffer = None, []
        if tag == "article" and self.current:
            if self.current["title"]:
                joined = " ".join(self.current["notes"] + self.current["lyric_excerpts"])
                self.current["confidence"] = "speculative" if self.current["section_id"] == "s10" or "※" in joined else "curated"
                self.records.append(self.current)
            self.current = None

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.buffer.append(data)


def read_references(path: Path, songs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parser = ReferenceParser()
    source = path.read_text(encoding="utf-8")
    # Entry numbers live in a separate span. Remove them before collecting h3 text;
    # otherwise a numeric song title such as "23-3" is corrupted.
    source = re.sub(r'<span\s+class="entry-index"[^>]*>.*?</span>', "", source, flags=re.IGNORECASE | re.DOTALL)
    parser.feed(source)
    by_key: dict[str, list[str]] = {}
    for song in songs:
        for key in title_keys(song["title"]):
            by_key.setdefault(key, []).append(song["song_id"])
    for record in parser.records:
        record["title_key"] = title_key(record["title"])
        record["song_ids"] = by_key.get(record["title_key"], [])
    return parser.records


def paths(data_dir: Path) -> dict[str, Path]:
    return {name: data_dir / filename for name, filename in {
        "library": "library.json", "references": "references.json", "sources": "sources.json",
        "report": "parse_report.json", "draws": "draws.jsonl"}.items()}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_init(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).expanduser().resolve()
    lyrics = Path(args.lyrics_docx).expanduser().resolve()
    refs = Path(args.references_html).expanduser().resolve() if args.references_html else None
    if not lyrics.is_file():
        raise ValueError("歌词 DOCX 不存在。")
    if refs is not None and not refs.is_file():
        raise ValueError("指定的引用 HTML 不存在。")
    data_dir.mkdir(parents=True, exist_ok=True)
    out = paths(data_dir)
    if any(out[key].exists() for key in ("library", "references", "draws")):
        raise ValueError("数据目录已有书库或抽取日志；为保留可恢复性，请使用新的数据目录。")
    corpus_name = re.sub(r"[^a-z0-9-]+", "-", args.corpus_name.lower()).strip("-") or "lyrics"
    songs, warnings = read_docx_songs(lyrics, corpus_name)
    for song in songs:
        if len(song["lines"]) < 4:
            warnings.append(f"标题“{song['title']}”少于四行，抽取时将跳过。")
    references = read_references(refs, songs) if refs is not None else []
    matched = sum(bool(r["song_ids"]) for r in references)
    library = {"schema_version": 1, "kind": "lyrics-bibliomancy", "corpus_name": args.corpus_name,
               "created_at": utc_now(), "songs": songs}
    sources = {"lyrics_docx": {"path": str(lyrics), "sha256": digest(lyrics)}}
    if refs is not None:
        sources["references_html"] = {"path": str(refs), "sha256": digest(refs)}
    report = {"songs": len(songs), "lyric_lines": sum(len(s["lines"]) for s in songs),
              "references": len(references), "matched_references": matched,
              "unmatched_reference_titles": sorted({r["title"] for r in references if not r["song_ids"]}),
              "warnings": warnings,
              "notes": ["歌词按 DOCX 标题格式切歌；空行不作为切歌依据。",
                        "每组固定四行；末尾不足四行时使用向前补足的尾部窗口，未声称是主歌或副歌。",
                        "curated 仅表示引用整理中的非“※”条目；speculative 包含“※”与附录条目。"]}
    write_json(out["library"], library)
    write_json(out["references"], {"schema_version": 1, "created_at": utc_now(), "records": references})
    write_json(out["sources"], sources)
    write_json(out["report"], report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def load_data(data_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    out = paths(data_dir)
    if not out["library"].is_file() or not out["references"].is_file():
        raise ValueError("未找到书库。请先运行 init。")
    return json.loads(out["library"].read_text(encoding="utf-8")), json.loads(out["references"].read_text(encoding="utf-8"))


def chunks(lines: list[dict[str, Any]], size: int = 4) -> list[list[dict[str, Any]]]:
    """Return fixed-size groups and cover a short tail with one overlapping final window."""
    if len(lines) < size:
        return []
    groups: list[list[dict[str, Any]]] = []
    for start in range(0, len(lines), size):
        group = lines[start:start + size]
        if len(group) < size:
            group = lines[-size:]
        if not groups or group[0]["number"] != groups[-1][0]["number"]:
            groups.append(group)
    return groups


def command_check(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).expanduser().resolve()
    library, refs = load_data(data_dir)
    report_path = paths(data_dir)["report"]
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    work_report = validate_work_context_records(data_dir, library, work_context_records(data_dir))
    intertext_report = validate_intertext_index(data_dir, library, refs)
    draw_policy = {
        "passage_lines": 4,
        "tail_window": "overlap-backward",
        "eligible_songs": sum(len(song["lines"]) >= 4 for song in library["songs"]),
        "skipped_short_songs": sum(len(song["lines"]) < 4 for song in library["songs"]),
    }
    print(json.dumps({"corpus": library["corpus_name"], "songs": len(library["songs"]),
                      "references": len(refs["records"]), "intertext_index": intertext_report,
                      "work_context": work_report, "draw_policy": draw_policy,
                      "report": report}, ensure_ascii=False, indent=2))


def get_draw(data_dir: Path, draw_id: str) -> dict[str, Any]:
    log = paths(data_dir)["draws"]
    if not log.is_file():
        raise ValueError("没有抽取日志。")
    for line in log.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["draw_id"] == draw_id:
            return item
    raise ValueError(f"找不到 draw_id: {draw_id}")


def compact_match_text(value: str) -> str:
    """Normalize harmless typography while keeping letters, numbers, and symbols."""
    value = unicodedata.normalize("NFKC", value).lower()
    return "".join(
        char for char in value
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def quoted_fragments(value: str) -> list[str]:
    """Extract text enclosed by common Japanese or curly quotation marks."""
    results = []
    for pattern in (r"「([^」]+)」", r"『([^』]+)』", r"“([^”]+)”"):
        results.extend(match.strip() for match in re.findall(pattern, value, flags=re.DOTALL) if match.strip())
    return results


def split_anchor(value: str) -> list[str]:
    """Split imported multi-line lyric notation such as A／B into local anchors."""
    results = []
    for part in re.split(r"[／/\r\n]+", value):
        part = re.sub(
            r"^\s*(?:[①-⑳]|\d+[.)、]?)?\s*(?:歌词|歌詞|歌曲标题|歌曲標題)?\s*",
            "", part,
        ).strip().strip("「」『』“”")
        if len(compact_match_text(part)) >= 3:
            results.append(part)
    return results


def lyric_anchor_candidates(card: dict[str, Any], song: dict[str, Any]) -> list[str]:
    """Recover lyric anchors from both old and new layouts of the imported HTML."""
    song_text = "\n".join(line["text"] for line in song["lines"])
    song_key = compact_match_text(song_text)
    candidates = []
    seen_keys = set()
    for field in ("lyric_excerpts", "quotes", "notes"):
        for value in card.get(field, []):
            fragments = quoted_fragments(value)
            if field == "notes":
                fragments.extend(re.findall(r"[（(]([^（）()]+)[）)]", value))
            if field == "lyric_excerpts":
                remainder = re.sub(
                    r"^\s*(?:[①-⑳]|\d+[.)、]?)?\s*(?:歌词|歌詞|歌曲标题|歌曲標題)\s*",
                    "", value,
                ).strip()
                if remainder and remainder != value:
                    fragments.append(remainder)
            for fragment in fragments:
                for anchor in split_anchor(fragment):
                    key = compact_match_text(anchor)
                    if key and key in song_key and key not in seen_keys:
                        seen_keys.add(key)
                        candidates.append(anchor)
    return candidates


def inferred_relation_type(card: dict[str, Any], song: dict[str, Any],
                           anchors: list[str]) -> str:
    if anchors:
        return "line_direct"
    if card.get("confidence") == "speculative" or "作者个人联想到" in card.get("section", ""):
        return "association"
    notes = " ".join(card.get("notes", []))
    explicit_title_language = any(term in notes for term in ("取自", "源自", "名称", "名字", "标题", "題名", "名叫"))
    song_title_in_note = len(title_key(song["title"])) >= 2 and title_key(song["title"]) in title_key(notes)
    return "title_source" if explicit_title_language or song_title_in_note else "work_level"


def intertext_claim_overrides(data_dir: Path) -> list[dict[str, Any]]:
    """Load optional claim-level corrections for entries that contain multiple works."""
    path = data_dir / "intertext_claims.jsonl"
    if not path.is_file():
        return []
    records = []
    required = {"claim_id", "entry_id", "song_ids", "relation_type", "notes", "sources", "confidence"}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"intertext_claims.jsonl 第 {number} 行不是有效 JSON：{exc.msg}") from exc
        missing = sorted(required - item.keys())
        if missing:
            raise ValueError(f"intertext_claims.jsonl 第 {number} 行缺少字段：{', '.join(missing)}")
        if item["relation_type"] not in {"line_direct", "title_source", "work_level", "association"}:
            raise ValueError(f"{item['claim_id']} 的 relation_type 无效。")
        records.append(item)
    return records


def validate_intertext_index(data_dir: Path, library: dict[str, Any],
                             refs: dict[str, Any]) -> dict[str, int]:
    songs = {song["song_id"]: song for song in library["songs"]}
    overrides = intertext_claim_overrides(data_dir)
    claim_ids = set()
    for claim in overrides:
        if claim["claim_id"] in claim_ids:
            raise ValueError(f"intertext_claims.jsonl 的 claim_id 重复：{claim['claim_id']}")
        claim_ids.add(claim["claim_id"])
        for song_id in claim["song_ids"]:
            if song_id not in songs:
                raise ValueError(f"{claim['claim_id']} 使用了未知 song_id：{song_id}")
            song_key = compact_match_text("\n".join(line["text"] for line in songs[song_id]["lines"]))
            for anchor in claim.get("lyric_anchors", []):
                if compact_match_text(anchor) not in song_key:
                    raise ValueError(f"{claim['claim_id']} 的歌词锚点未出现在关联歌曲中：{anchor!r}")

    counts = {"line_direct": 0, "title_source": 0, "work_level": 0, "association": 0}
    overridden_entries = {claim["entry_id"] for claim in overrides}
    for claim in overrides:
        counts[claim["relation_type"]] += 1
    for card in refs["records"]:
        if card["entry_id"] in overridden_entries or not card["song_ids"]:
            continue
        song = songs.get(card["song_ids"][0])
        if song is None:
            continue
        anchors = lyric_anchor_candidates(card, song)
        counts[inferred_relation_type(card, song, anchors)] += 1
    return {
        "claim_overrides": len(overrides),
        "line_direct": counts["line_direct"],
        "title_source": counts["title_source"],
        "work_level": counts["work_level"],
        "association_not_auto_loaded": counts["association"],
    }


def matched_intertext_cards(data_dir: Path, refs: dict[str, Any], song: dict[str, Any],
                            draw: dict[str, Any]) -> list[dict[str, Any]]:
    """Return line matches plus clearly labeled title/work-level candidates."""
    passage_key = compact_match_text("\n".join(line["text"] for line in draw["passage"]))
    matches = []
    overrides = intertext_claim_overrides(data_dir)
    overridden_entries = {claim["entry_id"] for claim in overrides}

    for claim in overrides:
        if draw["song_id"] not in claim["song_ids"]:
            continue
        anchors = claim.get("lyric_anchors", [])
        hit = [anchor for anchor in anchors if compact_match_text(anchor) in passage_key]
        relation = claim["relation_type"]
        if relation == "line_direct" and not hit:
            continue
        if relation == "association" and not hit:
            continue
        item = dict(claim)
        item["matched_lyric_fragments"] = hit
        item["match_scope"] = "drawn_lines" if hit else ("song_title" if relation == "title_source" else "whole_song_candidate")
        item["requires_local_relevance_check"] = not bool(hit)
        matches.append(item)

    for card in refs["records"]:
        if card["entry_id"] in overridden_entries or draw["song_id"] not in card["song_ids"]:
            continue
        anchors = lyric_anchor_candidates(card, song)
        hit = [anchor for anchor in anchors if compact_match_text(anchor) in passage_key]
        relation = inferred_relation_type(card, song, anchors)
        if relation == "line_direct" and not hit:
            continue
        if relation == "association" and not hit:
            continue
        item = dict(card)
        item["relation_type"] = relation
        item["lyric_anchors"] = anchors
        item["matched_lyric_fragments"] = hit
        item["match_scope"] = "drawn_lines" if hit else ("song_title" if relation == "title_source" else "whole_song_candidate")
        item["requires_local_relevance_check"] = not bool(hit)
        matches.append(item)

    rank = {"line_direct": 0, "title_source": 1, "work_level": 2, "association": 3}
    matches.sort(key=lambda item: (rank.get(item.get("relation_type", "association"), 9),
                                   item.get("claim_id", item.get("entry_id", ""))))
    return matches


def enrichment_records(data_dir: Path, entry_ids: set[str],
                       claim_ids: set[str] | None = None) -> list[dict[str, Any]]:
    if not entry_ids:
        return []
    claim_ids = claim_ids or set()
    records = []
    seen = set()
    paths = sorted(data_dir.glob("intertext_enrichment*.jsonl"))
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name} 第 {number} 行不是有效 JSON：{exc.msg}") from exc
            if item.get("entry_id") not in entry_ids:
                continue
            if item.get("claim_id") and item["claim_id"] not in claim_ids:
                continue
            identity = item.get("enrichment_id") or json.dumps(item, ensure_ascii=False, sort_keys=True)
            if identity in seen:
                continue
            seen.add(identity)
            item = dict(item)
            item["_source_file"] = path.name
            records.append(item)
    return records


def work_context_records(data_dir: Path) -> list[dict[str, Any]]:
    """Load the optional compact index for novels, letters, and creator notes."""
    path = data_dir / "work_context_index.jsonl"
    if not path.is_file():
        return []
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"work_context_index.jsonl 第 {number} 行不是有效 JSON：{exc.msg}") from exc
        required = {"context_id", "song_ids", "trigger_terms", "detail_file", "anchor",
                    "evidence", "summary", "use", "limits"}
        missing = sorted(required - item.keys())
        if missing:
            raise ValueError(
                f"work_context_index.jsonl 第 {number} 行缺少字段：{', '.join(missing)}"
            )
        if not isinstance(item["song_ids"], list) or not isinstance(item["trigger_terms"], list):
            raise ValueError(
                f"work_context_index.jsonl 第 {number} 行的 song_ids 和 trigger_terms 必须是数组。"
            )
        records.append(item)
    return records


def validate_work_context_records(data_dir: Path, library: dict[str, Any],
                                  records: list[dict[str, Any]]) -> dict[str, int]:
    """Validate IDs, evidence levels, detail pointers, and exact lyric triggers."""
    songs = {song["song_id"]: song for song in library["songs"]}
    seen: set[str] = set()
    trigger_count = 0
    for item in records:
        context_id = item["context_id"]
        if context_id in seen:
            raise ValueError(f"work_context_index.jsonl 的 context_id 重复：{context_id}")
        seen.add(context_id)
        if item["evidence"] not in {"A", "B"}:
            raise ValueError(f"{context_id} 的 evidence 必须是 A 或 B。")
        detail = data_dir / item["detail_file"]
        if not detail.is_file():
            raise ValueError(f"{context_id} 指向的详细材料不存在：{detail}")
        linked = []
        for song_id in item["song_ids"]:
            if song_id not in songs:
                raise ValueError(f"{context_id} 使用了未知 song_id：{song_id}")
            linked.append("\n".join(line["text"] for line in songs[song_id]["lines"]))
        for term in item["trigger_terms"]:
            trigger_count += 1
            if not term or not any(term in text for text in linked):
                raise ValueError(f"{context_id} 的触发词未出现在关联歌词中：{term!r}")
    return {
        "cards": len(records),
        "a_tier": sum(item["evidence"] == "A" for item in records),
        "b_tier": sum(item["evidence"] == "B" for item in records),
        "trigger_terms": trigger_count,
    }


def matched_work_context_cards(data_dir: Path, draw: dict[str, Any]) -> list[dict[str, Any]]:
    """Match work context by song and exact terms present in the selected passage."""
    passage_text = "\n".join(line["text"] for line in draw["passage"])
    matches = []
    for card in work_context_records(data_dir):
        if draw["song_id"] not in card["song_ids"]:
            continue
        hit = [term for term in card["trigger_terms"] if term and term in passage_text]
        if not hit:
            continue
        item = dict(card)
        item["matched_trigger_terms"] = hit
        matches.append(item)
    # Strong evidence first. The skill normally reads at most two local cards.
    matches.sort(key=lambda item: (item.get("evidence") != "A", item.get("context_id", "")))
    return matches[:2]


def reading_context(data_dir: Path, library: dict[str, Any], refs: dict[str, Any], draw: dict[str, Any]) -> dict[str, Any]:
    song = next(song for song in library["songs"] if song["song_id"] == draw["song_id"])
    cards = matched_intertext_cards(data_dir, refs, song, draw)
    return {
        "song_context": {"song_id": song["song_id"], "title": song["title"], "lines": song["lines"]},
        "matched_intertext_cards": cards,
        "intertext_enrichments": enrichment_records(
            data_dir,
            {card["entry_id"] for card in cards},
            {card["claim_id"] for card in cards if card.get("claim_id")},
        ),
        "matched_work_context_cards": matched_work_context_cards(data_dir, draw),
    }


def print_draw(draw: dict[str, Any], include_text: bool,
               context: dict[str, Any] | None = None) -> None:
    base = {k: draw[k] for k in ("draw_id", "timestamp", "question", "song_id", "song_title", "line_range", "corpus_sha256")}
    if include_text:
        base["prior_context"] = draw["prior_context"]
        base["passage"] = draw["passage"]
    if context is not None:
        base["reading_context"] = context
    print(json.dumps(base, ensure_ascii=False, indent=2))


def command_draw(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).expanduser().resolve()
    library, refs = load_data(data_dir)
    eligible = [song for song in library["songs"] if len(song["lines"]) >= 4]
    if not eligible:
        raise ValueError("书库中没有至少四行的歌曲，无法抽取。")
    song = secrets.choice(eligible)
    passage = secrets.choice(chunks(song["lines"]))
    first = passage[0]["number"]
    prior = [line for line in song["lines"] if first - 2 <= line["number"] < first]
    source_hash = digest(paths(data_dir)["library"])
    draw = {"draw_id": secrets.token_hex(8), "timestamp": utc_now(), "question": args.question,
            "song_id": song["song_id"], "song_title": song["title"],
            "line_range": [first, passage[-1]["number"]], "prior_context": prior, "passage": passage,
            "corpus_sha256": source_hash}
    with paths(data_dir)["draws"].open("a", encoding="utf-8") as f:
        f.write(json.dumps(draw, ensure_ascii=False) + "\n")
    context = reading_context(data_dir, library, refs, draw) if args.with_reading_context else None
    print_draw(draw, include_text=True, context=context)


def command_show(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).expanduser().resolve()
    draw = get_draw(data_dir, args.draw_id)
    if args.with_reading_context:
        library, refs = load_data(data_dir)
        print_draw(draw, include_text=True, context=reading_context(data_dir, library, refs, draw))
    else:
        print_draw(draw, include_text=True)


def command_lookup(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).expanduser().resolve()
    draw = get_draw(data_dir, args.draw_id)
    _, refs = load_data(data_dir)
    cards = [r for r in refs["records"] if draw["song_id"] in r["song_ids"]]
    print(json.dumps({"draw_id": draw["draw_id"], "song": draw["song_title"],
                      "line_range": draw["line_range"], "intertext_cards": cards}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    subs = parser.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init")
    init.add_argument("--lyrics-docx", required=True)
    init.add_argument("--references-html", help="optional structured HTML intertext index")
    init.add_argument("--corpus-name", required=True)
    check = subs.add_parser("check")
    draw = subs.add_parser("draw")
    draw.add_argument("--question", required=True)
    draw.add_argument("--with-reading-context", action="store_true",
                      help="also return the full song plus intertext and work-context cards directly matched by the selected lines")
    show = subs.add_parser("show")
    show.add_argument("--draw-id", required=True)
    show.add_argument("--with-reading-context", action="store_true",
                      help="also return the full song plus intertext and work-context cards directly matched by the selected lines")
    lookup = subs.add_parser("lookup")
    lookup.add_argument("--draw-id", required=True)
    args = parser.parse_args()
    {"init": command_init, "check": command_check, "draw": command_draw,
     "show": command_show, "lookup": command_lookup}[args.command](args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(2)
