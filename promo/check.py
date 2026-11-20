"""Quality checks.

1. Hard validators (code): every clip is 20-60 s, segments are in order and inside the episode,
   the hook line starts within the first 3 s, and no cut lands mid-dialogue.
2. Warning flags (code): known ways the tool picks badly, shown next to each promo so a human
   editor knows what to look at.
3. Cold-reader check (optional AI, ideally a DIFFERENT model): reads ONLY the clip transcript,
   no show context, and says what is happening and whether it would keep watching. This tests
   "makes sense on its own", which the scorer never sees directly.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from .config import LLMConfig
from .llm import chat, parse_json, items, LLMError
from .parse import Episode

PRONOUN_OPEN = re.compile(r"^(he|she|they|him|her|it|that|this|those|these|then|so)\b", re.I)


def validate(c: dict, eps: dict[int, Episode], min_len=20.0, max_len=60.0) -> list[str]:
    errs = []
    if not (min_len - 0.01 <= c["duration"] <= max_len + 0.01):
        errs.append(f"duration {c['duration']:.1f}s outside {min_len:.0f}-{max_len:.0f}s")
    prev = (0, -1.0)
    for s in c["segments"]:
        ep = eps.get(s["episode"])
        if ep is None:
            errs.append(f"unknown episode {s['episode']}")
            continue
        if not (0 <= s["start"] < s["end"] <= ep.duration + 0.01):
            errs.append(f"segment E{s['episode']} {s['start_ts']}-{s['end_ts']} outside episode")
        if (s["episode"], s["start"]) < prev:
            errs.append("segments out of order")
        prev = (s["episode"], s["end"])
        for t in (s["start"], s["end"]):
            for d in ep.events:
                if d.kind == "dialogue" and d.start + 0.05 < t < d.end - 0.05:
                    errs.append(f"cut at {t:.1f}s splits a dialogue line")
                    break
    first = c["segments"][0]
    hook = eps[first["episode"]].events[c["hook"]["idx"]] if first["episode"] in eps else None
    if hook and not (first["start"] - 0.01 <= hook.start <= first["start"] + 3.0):
        errs.append("hook line does not start within the first 3 s")
    return errs


def flags(c: dict, eps: dict[int, Episode], n_episodes: int) -> list[str]:
    out = []
    first = c["segments"][0]
    ep = eps[first["episode"]]
    vis = [e for e in ep.visible if first["start"] - 0.05 <= e.start < first["end"]]
    lines = [e for e in vis if e.kind == "dialogue"]
    if lines and PRONOUN_OPEN.match(lines[0].text):
        out.append("opens on a pronoun (who is 'he/she/that'?)")
    speakers = {e.speaker for s in c["segments"] for e in eps[s["episode"]].visible
                if e.kind == "dialogue" and s["start"] - 0.05 <= e.start < s["end"]}
    if len(speakers) >= 5:
        out.append(f"{len(speakers)} speakers in one clip (hard to follow)")
    talk = sum(min(e.end, first["end"]) - e.start for e in vis if e.kind in ("dialogue", "action"))
    if first["end"] - first["start"] > 0 and talk / (first["end"] - first["start"]) < 0.35:
        out.append("mostly camera/visual time; script can't show if it plays")
    if c["cliffhanger"].get("kind") == "dialogue" and not re.search(r"[?!.]{1}$|\.\.\.$", c["cliffhanger"]["text"].strip()):
        out.append("cliff line may be cut mid-thought")
    if c["parts"].get("context_penalty", 0) <= -1.2:
        out.append("hook needs backstory")
    if n_episodes >= 10 and min(c["episodes"]) > n_episodes * 0.6:
        out.append("late episode: may spoil twists / need context")
    if c["type"] == "stitched":
        out.append("stitched: check the jump between segments reads naturally")
    if c["parts"]["cliff"] < 1.2 * 6:
        out.append("weak cliffhanger")
    return out


COLD_SYSTEM = """You are a viewer scrolling TikTok. You have NEVER seen this show. You get the transcript of
one short clip (dialogue, actions, sounds). Answer honestly as that stranger. Output JSON only."""

COLD_USER = """Clips:
{clips}

For EACH clip return:
{{"clips": [{{"id": "<id>", "what_happens": "<one sentence>", "clear": 1-5, "hooked_in_3s": 1-5,
"ends_unresolved": true/false, "keep_watching": 1-5, "confusing": "<what was unclear, or empty>"}}]}}
(clear: 5 = fully understood without any backstory)"""


def cold_reader(cands: list[dict], cfg: LLMConfig, per_call: int = 5, log=print) -> dict:
    """Adds c['cold'] = {...} to each candidate. Returns a summary."""
    batches = [cands[i: i + per_call] for i in range(0, len(cands), per_call)]

    def run(batch):
        # ids are neutral (C1, C2...) so the judge can't see ranks or scores
        local = {f"C{i + 1}": c for i, c in enumerate(batch)}
        clips = "\n\n".join(f"[{k}]\n" + "\n".join(re.sub(r"^E\d+ \S+ ", "", t) for t in c["transcript"][:40])
                            for k, c in local.items())
        try:
            text, _ = chat(cfg, COLD_SYSTEM, COLD_USER.format(clips=clips), max_tokens=2500)
            for item in items(parse_json(text), "clips", "results"):
                c = local.get(str(item.get("id", "")).strip("[] "))
                if c is not None:
                    c["cold"] = {k: item.get(k) for k in
                                 ("what_happens", "clear", "hooked_in_3s", "ends_unresolved", "keep_watching", "confusing")}
            return None
        except (LLMError, AttributeError, TypeError, ValueError) as e:
            return f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        errors = [e for e in pool.map(run, batches) if e]
    if errors:
        log(f"  cold-reader: {len(errors)} batch(es) failed: {errors[0][:120]}")
    return summarize_cold(cands) | {"model": cfg.model, "errors": errors}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def summarize_cold(cands: list[dict]) -> dict:
    got = [c["cold"] for c in cands if c.get("cold")]
    if not got:
        return {"judged": 0}

    def avg(k):
        v = [_num(g.get(k)) for g in got if _num(g.get(k)) is not None]
        return round(sum(v) / len(v), 2) if v else None

    unresolved = [g.get("ends_unresolved") in (True, "true", "True") for g in got]
    return {"judged": len(got), "clear_avg": avg("clear"), "hooked_avg": avg("hooked_in_3s"),
            "keep_watching_avg": avg("keep_watching"),
            "ends_unresolved_rate": round(sum(unresolved) / len(got), 2),
            "clear_rate_4plus": round(sum((_num(g.get("clear")) or 0) >= 4 for g in got) / len(got), 2)}
