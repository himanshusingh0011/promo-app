"""Score systems against a reference set of hand-picked promo moments.

Reference file (eval/runs/reference_labels.json): for each episode, picks of
{"hook": line id, "cliff": line id, "tier": "A"|"B"}. Line ids are the numbers parse.py gives
visible lines (the same ids shown to the AI). A = "post it", B = "usable".

A system clip MATCHES a reference pick when they share the same episode and overlap by at least
half of the shorter of the two. HOOK-EXACT means the clip also opens within 5 s of the reference hook.

    python -m promo eval reference --input data/show1
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from .parse import Episode

REF = Path("eval/runs/reference_labels.json")


def load_reference(episodes: list[Episode], path: Path = REF) -> tuple[list[dict], list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    eps = {e.number: e for e in episodes}
    refs, problems = [], []
    for k, picks in data.items():
        if k.startswith("_"):
            continue
        ep = eps.get(int(k))
        if ep is None:
            continue
        by = ep.by_lid()
        for p in picks:
            h, c = by.get(p["hook"]), by.get(p["cliff"])
            if not h or not c:
                problems.append(f"E{k}: unknown line id in {p}")
                continue
            start, end = max(0.0, h.start - 0.5), min(ep.duration, c.end + 1.0)
            if not (18 <= end - start <= 62):
                problems.append(f"E{k}: reference pick is {end - start:.0f}s long")
            refs.append({"episode": ep.number, "start": start, "end": end, "hook_t": h.start,
                         "tier": p["tier"], "note": p.get("note", "")})
    return refs, problems


def _overlap(clip: dict, ref: dict) -> float:
    inter, clen = 0.0, 0.0
    for s in clip["segments"]:
        clen += s["end"] - s["start"]
        if s["episode"] == ref["episode"]:
            inter += max(0.0, min(s["end"], ref["end"]) - max(s["start"], ref["start"]))
    return inter / max(1e-6, min(clen, ref["end"] - ref["start"]))


def _matches(clip: dict, ref: dict) -> bool:
    return _overlap(clip, ref) >= 0.5


def _hook_exact(clip: dict, ref: dict) -> bool:
    first = clip["segments"][0]
    return first["episode"] == ref["episode"] and abs(first["start"] - ref["hook_t"]) <= 5.0


def score_system(clips: list[dict], refs: list[dict], top_n: int = 20) -> dict:
    """clips must be in rank order."""
    a_refs = [r for r in refs if r["tier"] == "A"]
    found = [r for r in refs if any(_matches(c, r) for c in clips)]
    found_a = [r for r in a_refs if any(_matches(c, r) for c in clips)]
    hook_exact = [r for r in refs if any(_matches(c, r) and _hook_exact(c, r) for c in clips)]
    top = clips[:top_n]
    p_any = sum(any(_matches(c, r) for r in refs) for c in top) / max(1, len(top))
    p_a = sum(any(_matches(c, r) for r in a_refs) for c in top) / max(1, len(top))
    # best clip per episode (the one ranked highest) hits a reference pick?
    best: dict[int, dict] = {}
    for c in clips:
        e = c["segments"][0]["episode"]
        best.setdefault(e, c)
    eps_with_refs = {r["episode"] for r in refs}
    ep_hits = sum(any(_matches(best[e], r) for r in refs if r["episode"] == e) for e in eps_with_refs if e in best)
    return {
        "clips": len(clips),
        "recall_all_picks": round(len(found) / max(1, len(refs)), 3),
        "recall_A_picks": round(len(found_a) / max(1, len(a_refs)), 3),
        "recall_hook_exact": round(len(hook_exact) / max(1, len(refs)), 3),
        f"top{top_n}_match_any": round(p_any, 3),
        f"top{top_n}_match_A": round(p_a, 3),
        "episode_best_clip_hits": round(ep_hits / max(1, len(eps_with_refs)), 3),
    }


def random_system(episodes: list[Episode], per_episode: dict[int, int], seed: int) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for ep in episodes:
        vis = ep.visible
        for _ in range(per_episode.get(ep.number, 3)):
            for _try in range(50):
                s = rng.choice(vis)
                length = rng.uniform(20, 60)
                ends = [e for e in vis if s.start + 20 <= e.end <= s.start + 60]
                if ends:
                    e = min(ends, key=lambda x: abs(x.end - s.start - length))
                    out.append({"segments": [{"episode": ep.number, "start": s.start, "end": e.end}]})
                    break
    rng.shuffle(out)
    return out


def run(episodes: list[Episode], ai_json: str, rules_json: str, seeds: int = 200) -> dict:
    refs, problems = load_reference(episodes)
    ai = json.loads(Path(ai_json).read_text(encoding="utf-8"))["promos"]
    rules = json.loads(Path(rules_json).read_text(encoding="utf-8"))["promos"]
    res = {"reference": {"picks": len(refs), "A_picks": sum(r["tier"] == "A" for r in refs),
                         "episodes_with_picks": len({r["episode"] for r in refs}), "problems": problems}}
    res["ai (after AI re-rank)"] = score_system(ai, refs)
    if any("rule_rank" in c for c in ai):
        res["ai (rule rank only)"] = score_system(sorted(ai, key=lambda c: c.get("rule_rank") or c["rank"]), refs)
    res["rules only (no AI)"] = score_system(rules, refs)
    per_ep: dict[int, int] = {}
    for c in ai:
        e = c["segments"][0]["episode"]
        per_ep[e] = per_ep.get(e, 0) + 1
    runs = [score_system(random_system(episodes, per_ep, s), refs) for s in range(seeds)]
    res[f"random (avg of {seeds})"] = {k: (round(sum(r[k] for r in runs) / seeds, 3) if k != "clips" else runs[0][k])
                                       for k in runs[0]}
    return res
