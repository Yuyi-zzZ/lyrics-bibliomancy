import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lyrics.py"
SPEC = importlib.util.spec_from_file_location("lyrics_bibliomancy_tool", SCRIPT)
lyrics = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(lyrics)


class LyricsToolTests(unittest.TestCase):
    def test_chunks_are_always_four_lines_and_cover_tail(self):
        lines = [{"number": index, "text": f"line-{index}"} for index in range(1, 11)]
        groups = lyrics.chunks(lines)
        self.assertTrue(all(len(group) == 4 for group in groups))
        self.assertEqual([line["number"] for line in groups[-1]], [7, 8, 9, 10])

    def test_multiline_slash_anchor_matches_drawn_lines(self):
        song = {
            "song_id": "demo-001",
            "title": "demo",
            "lines": [
                {"number": 1, "text": "前の行"},
                {"number": 2, "text": "本当はいらなかったものも"},
                {"number": 3, "text": "ソファも本も捨てよう"},
                {"number": 4, "text": "町へ出よう"},
            ],
        }
        refs = {"records": [{
            "entry_id": "e1", "song_ids": ["demo-001"], "title": "demo",
            "section": "demo", "confidence": "curated", "notes": [],
            "lyric_excerpts": ["歌词"],
            "quotes": ["「本当はいらなかったものも／ソファも本も捨てよう／町へ出よう」"],
            "sources": [],
        }]}
        draw = {"song_id": "demo-001", "passage": song["lines"]}
        with tempfile.TemporaryDirectory() as temp:
            cards = lyrics.matched_intertext_cards(Path(temp), refs, song, draw)
        self.assertEqual(cards[0]["relation_type"], "line_direct")
        self.assertIn("ソファも本も捨てよう", cards[0]["matched_lyric_fragments"])

    def test_title_source_surfaces_without_claiming_line_quote(self):
        song = {
            "song_id": "demo-002", "title": "アルジャーノン",
            "lines": [{"number": index, "text": text} for index, text in enumerate(
                ["貴方はどうして", "僕に心をくれた", "目を描いた", "変わっていく"], 1
            )],
        }
        refs = {"records": [{
            "entry_id": "e2", "song_ids": ["demo-002"], "title": "アルジャーノン",
            "section": "demo", "confidence": "curated",
            "notes": ["《献给阿尔吉侬的花束》（アルジャーノンに花束を）。"],
            "lyric_excerpts": [], "quotes": [], "sources": [],
        }]}
        draw = {"song_id": "demo-002", "passage": song["lines"]}
        with tempfile.TemporaryDirectory() as temp:
            cards = lyrics.matched_intertext_cards(Path(temp), refs, song, draw)
        self.assertEqual(cards[0]["relation_type"], "title_source")
        self.assertEqual(cards[0]["matched_lyric_fragments"], [])
        self.assertTrue(cards[0]["requires_local_relevance_check"])

    def test_unanchored_association_is_not_auto_loaded(self):
        song = {
            "song_id": "demo-003", "title": "demo",
            "lines": [{"number": index, "text": text} for index, text in enumerate(
                ["一", "二", "三", "四"], 1
            )],
        }
        refs = {"records": [{
            "entry_id": "e3", "song_ids": ["demo-003"], "title": "demo",
            "section": "作者个人联想到的文学作品", "confidence": "curated",
            "notes": ["只有宽泛联想。"], "lyric_excerpts": [], "quotes": [], "sources": [],
        }]}
        draw = {"song_id": "demo-003", "passage": song["lines"]}
        with tempfile.TemporaryDirectory() as temp:
            cards = lyrics.matched_intertext_cards(Path(temp), refs, song, draw)
        self.assertEqual(cards, [])

    def test_enrichment_addendum_is_loaded(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            base = {"entry_id": "e4", "value": "base"}
            addendum = {"entry_id": "e5", "value": "addendum"}
            (data_dir / "intertext_enrichment.jsonl").write_text(
                json.dumps(base, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            (data_dir / "intertext_enrichment_addendum.jsonl").write_text(
                json.dumps(addendum, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            records = lyrics.enrichment_records(data_dir, {"e5"})
        self.assertEqual(records[0]["value"], "addendum")
        self.assertEqual(records[0]["_source_file"], "intertext_enrichment_addendum.jsonl")


if __name__ == "__main__":
    unittest.main()
