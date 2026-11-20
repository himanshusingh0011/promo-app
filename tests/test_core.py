"""Unit tests on made-up sample episodes (no confidential data, no network).

    python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from make_sample import EP1, EP2, render  # noqa: E402
from promo.check import validate  # noqa: E402
from promo.config import Config  # noqa: E402
from promo.parse import parse_text, compact_episode, fmt_ts  # noqa: E402
from promo.pipeline import run  # noqa: E402
from promo.score import _scores_from_reply, heuristic_score  # noqa: E402
from promo.search import snap_start, snap_end, find_candidates  # noqa: E402
from promo.llm import parse_json, items  # noqa: E402

E1 = parse_text(render(*EP1), "sample-episode-001.txt")
E2 = parse_text(render(*EP2), "sample-episode-002.txt")


class ParseTests(unittest.TestCase):
    def test_header_and_events(self):
        self.assertEqual(E1.number, 1)
        self.assertIn("waitress", E1.logline)
        kinds = {e.kind for e in E1.events}
        self.assertEqual(kinds, {"camera", "action", "sfx", "dialogue"})
        self.assertAlmostEqual(E1.duration, 68.0)

    def test_dialogue_speaker_tone_and_quotes(self):
        d = next(e for e in E1.events if e.kind == "dialogue")
        self.assertEqual(d.speaker, "VIVIAN")
        self.assertEqual(d.tone, "Mocking, Loud")
        self.assertFalse(d.text.startswith('"'))

    def test_voice_over_tag_is_not_the_tone(self):
        vo = next(e for e in E2.events if e.speaker == "UNKNOWN VOICE")
        self.assertEqual(vo.tone, "Calm, Menacing")

    def test_compact_hides_camera_lines(self):
        txt = compact_episode(E1)
        self.assertNotIn("CAMERA", txt)
        self.assertIn("[1.1 @00:01]", txt)

    def test_fmt_ts(self):
        self.assertEqual(fmt_ts(83.19), "01:23.19")


class SearchTests(unittest.TestCase):
    def test_snaps_never_split_dialogue(self):
        for ep in (E1, E2):
            for ev in ep.visible:
                for t in (snap_start(ep, ev), snap_end(ep, ev)):
                    if t is None:
                        continue
                    for d in ep.events:
                        if d.kind == "dialogue" and d is not ev:
                            self.assertFalse(d.start + 0.05 < t < d.end - 0.05, (ep.number, ev.text, t, d.text))

    def test_candidates_respect_rules(self):
        scored = {ep.number: {"scores": heuristic_score(ep)} for ep in (E1, E2)}
        cands = find_candidates([E1, E2], scored)
        self.assertTrue(cands)
        eps = {1: E1, 2: E2}
        for c in cands:
            self.assertTrue(20 <= c["duration"] <= 60, c["duration"])
            self.assertEqual(validate(c, eps), [], c["id"])

    def test_ai_ids_map_to_events_and_bad_ids_dropped(self):
        reply = {"episodes": [{"episode": 1, "lines": [
            {"id": "1.6", "hook": 9, "cliff": 1, "ctx": 0, "why": "champagne in the face"},
            {"id": "1.999", "hook": 9, "cliff": 9},       # hallucinated id
            {"id": "7.1", "hook": 9, "cliff": 9}]}]}       # episode not in batch
        out = _scores_from_reply(reply, [E1])
        self.assertEqual(out["_bad_ids"], 2)
        (idx, s), = out[1].items()
        self.assertEqual(E1.events[idx].lid, 6)
        self.assertEqual(s["hook"], 9)


class PipelineTests(unittest.TestCase):
    def test_offline_end_to_end(self):
        res = run([E1, E2], Config(), use_ai=False, log=lambda m: None)
        self.assertTrue(res["promos"])
        self.assertEqual(res["quality"]["validator"]["passed"], res["quality"]["validator"]["checked"])
        top = res["promos"][0]
        for k in ("segments", "hook", "cliffhanger", "why", "rank", "flags"):
            self.assertIn(k, top)

    def test_reply_without_episode_wrapper(self):
        out = _scores_from_reply([{"id": "1.6", "hook": 8, "cliff": 2}], [E1])
        self.assertEqual(len(out[1]), 1)

    def test_items_flattens_reply_shapes(self):
        for data in ({"clips": [{"id": "C1"}]}, [{"id": "C1"}], [{"clips": [{"id": "C1"}]}]):
            self.assertEqual(items(data, "clips"), [{"id": "C1"}])

    def test_parse_json_handles_fences_and_think(self):
        self.assertEqual(parse_json('<think>hmm</think>```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parse_json('Sure! {"a": 2} hope it helps'), {"a": 2})


if __name__ == "__main__":
    unittest.main()
