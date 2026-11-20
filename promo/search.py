"""Window search: turn line scores into concrete 20-60 s promo clips. Pure code.

Single clip  = start just before a strong HOOK line, end just after a strong CLIFF line.
Stitched clip = a hook moment + a later cliff moment (same or next episode) when they are
                too far apart for one continuous clip.

Cut points snap to camera-shot boundaries (cleaner edits) and never cut a line of dialogue
in half. All timestamps come from the screenplay, never from the AI.
"""
from __future__ import annotations

from .parse import Episode, Event, fmt_ts

H_MIN, C_MIN = 4.0, 4.0     # minimum scores to be considered as a start / end
HOOK_LEAD = 2.0             # clip may start up to 2 s before the hook line (still inside the first 3 s)
END_HOLD = 2.5              # hold up to 2.5 s on the reaction shot after the cliff line


def _sc(scores: dict, ev: Event) -> dict:
    return scores.get(ev.idx) or scores.get(str(ev.idx)) or {"hook": 0, "cliff": 0, "ctx": 1, "why": ""}


def _cuts_dialogue(ep: Episode, t: float, ignore: Event | None = None) -> Event | None:
    for d in ep.events:
        if d.kind == "dialogue" and d is not ignore and d.start + 0.05 < t < d.end - 0.05:
            return d
    return None


def snap_start(ep: Episode, ev: Event) -> float | None:
    """Clip start for a hook line, or None if every option would cut into someone's line."""
    cands = [s.start for s in ep.shots if ev.start - HOOK_LEAD <= s.start <= ev.start]
    t = max(cands) if cands else max(0.0, ev.start - 0.2)
    for _ in range(3):  # never start in the middle of someone's line
        d = _cuts_dialogue(ep, t, ignore=ev)
        if d is None:
            break
        if ev.start - d.start > 2.9:  # hook sits inside a long line: no clean start
            return None
        t = d.start
    if _cuts_dialogue(ep, t, ignore=ev):
        return None
    return round(t, 2)


def snap_end(ep: Episode, ev: Event) -> float:
    covering = [s for s in ep.shots if s.start <= ev.end <= s.end]
    t = ev.end + 0.8
    if covering:
        shot_end = max(s.end for s in covering)
        if shot_end - ev.end <= END_HOLD:
            t = shot_end
    t = min(t, ep.duration)
    for _ in range(3):  # never cut someone off mid-line
        d = _cuts_dialogue(ep, t, ignore=ev)
        if d is None:
            break
        if d.start > ev.end:
            t = max(ev.end + 0.05, d.start - 0.05)     # end before they start talking
        else:
            t = min(ep.duration, d.end + 0.1)          # overlapping line: let it finish
    return round(t, 2)


def transcript(ep: Episode, start: float, end: float) -> list[str]:
    rows = []
    for e in ep.visible:
        if e.start >= start - 0.05 and e.start < end:
            body = f'"{e.text}"' if e.kind == "dialogue" else e.text
            rows.append(f"E{ep.number} {fmt_ts(e.start)} {e.label()}: {body}")
    return rows


def _seg(ep: Episode, st: float, en: float) -> dict:
    return {"episode": ep.number, "start": st, "end": en, "start_ts": fmt_ts(st), "end_ts": fmt_ts(en),
            "seconds": round(en - st, 2)}


def _line(ep: Episode, ev: Event, scores: dict) -> dict:
    s = _sc(scores, ev)
    return {"episode": ep.number, "at": fmt_ts(ev.start), "who": ev.label(), "text": ev.text,
            "kind": ev.kind, "why": s.get("why", ""), "idx": ev.idx}


def _body(ep: Episode, scores: dict, t0: float, t1: float, exclude: set[int]) -> float:
    vals = sorted((max(_sc(scores, e)["hook"], _sc(scores, e)["cliff"]) for e in ep.visible
                   if t0 < e.start < t1 and e.idx not in exclude), reverse=True)[:3]
    return sum(vals) / 3 if vals else 0.0


def _len_adj(d: float) -> float:
    return 0.5 if 25 <= d <= 45 else (-(d - 50) * 0.05 if d > 50 else 0.0)


def _candidate(kind, segments, hook_ep, hook_ev, cliff_ep, cliff_ev, scores_h, scores_c, parts, eps) -> dict:
    total = round(sum(parts.values()), 2)
    h, c = _line(hook_ep, hook_ev, scores_h), _line(cliff_ep, cliff_ev, scores_c)
    hw = (h["why"] or "a strong beat").strip().rstrip(".")
    cw = (c["why"] or "an unresolved beat").strip().rstrip(".")
    why = f"Opens on {hw}; cuts on {cw}."
    tr = []
    for sg in segments:
        tr.extend(transcript(eps[sg["episode"]], sg["start"], sg["end"]))
    cid = "-".join(f"E{s['episode']}@{s['start_ts']}" for s in segments)
    return {"id": cid, "type": kind, "segments": segments,
            "duration": round(sum(s["seconds"] for s in segments), 2),
            "episodes": sorted({s["episode"] for s in segments}),
            "hook": h, "cliffhanger": c, "why": why, "score": total,
            "parts": {k: round(v, 2) for k, v in parts.items()}, "transcript": tr}


def single_windows(ep: Episode, scores: dict, min_len=20.0, max_len=60.0) -> list[dict]:
    vis = ep.visible
    starts = sorted((e for e in vis if _sc(scores, e)["hook"] >= H_MIN), key=lambda e: -_sc(scores, e)["hook"])[:25]
    ends = [e for e in vis if _sc(scores, e)["cliff"] >= C_MIN]
    eps = {ep.number: ep}
    out = []
    for s in starts:
        st = snap_start(ep, s)
        if st is None:
            continue
        ss = _sc(scores, s)
        for e in ends:
            if e.start <= s.start:
                continue
            en = snap_end(ep, e)
            d = en - st
            if not (min_len <= d <= max_len):
                continue
            ce = _sc(scores, e)
            scenes = len({x.scene for x in ep.events if st <= x.start < en}) - 1
            parts = {"hook": ss["hook"], "cliff": 1.2 * ce["cliff"],
                     "body": 0.35 * _body(ep, scores, s.start, e.start, {s.idx, e.idx}),
                     "context_penalty": -0.8 * ss.get("ctx", 1), "scene_jumps": -0.6 * scenes,
                     "length": _len_adj(d)}
            out.append(_candidate("single", [_seg(ep, st, en)], ep, s, ep, e, scores, scores, parts, eps))
    return out


def _seg_a(ep: Episode, s: Event, scores: dict) -> tuple[float, float] | None:
    """Hook segment: hook line + the next 6-15 s, ending on a line end."""
    st = snap_start(ep, s)
    if st is None:
        return None
    best, best_v = None, -1.0
    for e in ep.visible:
        if e.idx < s.idx or not (st + 6 <= e.end <= st + 15):
            continue
        if _cuts_dialogue(ep, e.end + 0.2, ignore=e):
            continue
        v = max(_sc(scores, e)["hook"], _sc(scores, e)["cliff"]) - abs(e.end - st - 10) * 0.1
        if v > best_v:
            best, best_v = min(ep.duration, e.end + 0.2), v
    return (st, round(best, 2)) if best else None


def _seg_b(ep: Episode, e: Event, scores: dict) -> tuple[float, float] | None:
    """Cliff segment: 10-35 s of build-up ending on the cliff line."""
    en = snap_end(ep, e)
    best, best_v = None, -1e9
    for b in ep.visible:
        if b.idx > e.idx:
            break
        st = snap_start(ep, b)
        if st is None or not (10 <= en - st <= 35):
            continue
        v = 0.5 * _sc(scores, b)["hook"] - abs(en - st - 20) * 0.08
        if v > best_v:
            best, best_v = st, v
    return (best, en) if best is not None else None


def stitched_windows(ep: Episode, nxt: Episode | None, scores: dict, scores_next: dict,
                     min_len=20.0, max_len=60.0) -> list[dict]:
    hooks = sorted((e for e in ep.visible if _sc(scores, e)["hook"] >= 7), key=lambda e: -_sc(scores, e)["hook"])[:3]
    pools = [(ep, scores, [e for e in ep.visible if _sc(scores, e)["cliff"] >= 7])]
    if nxt is not None:
        pools.append((nxt, scores_next, [e for e in nxt.visible if _sc(scores_next, e)["cliff"] >= 7]))
    eps = {ep.number: ep, **({nxt.number: nxt} if nxt else {})}
    out = []
    for s in hooks:
        a = _seg_a(ep, s, scores)
        if not a:
            continue
        ss = _sc(scores, s)
        for cep, cscores, cliffs in pools:
            for e in cliffs:
                if cep is ep and e.start < a[1] + 45:  # close enough for a single clip -> not needed
                    continue
                b = _seg_b(cep, e, cscores)
                if not b:
                    continue
                d = (a[1] - a[0]) + (b[1] - b[0])
                if not (min_len <= d <= max_len):
                    continue
                ce = _sc(cscores, e)
                parts = {"hook": ss["hook"], "cliff": 1.2 * ce["cliff"],
                         "body": 0.35 * _body(cep, cscores, b[0], e.start, {e.idx}),
                         "context_penalty": -0.8 * ss.get("ctx", 1), "stitch_penalty": -1.0,
                         "cross_episode": -0.5 if cep is not ep else 0.0, "length": _len_adj(d)}
                segs = [_seg(ep, *a), _seg(cep, *b)]
                out.append(_candidate("stitched", segs, ep, s, cep, e, scores, cscores, parts, eps))
    return out


def overlap(a: dict, b: dict) -> float:
    """Share of the shorter clip that overlaps the other (0-1)."""
    inter = 0.0
    for x in a["segments"]:
        for y in b["segments"]:
            if x["episode"] == y["episode"]:
                inter += max(0.0, min(x["end"], y["end"]) - max(x["start"], y["start"]))
    return inter / max(1e-6, min(a["duration"], b["duration"]))


def nms(cands: list[dict], keep: int, max_overlap: float = 0.3) -> list[dict]:
    kept: list[dict] = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        if all(overlap(c, k) <= max_overlap for k in kept):
            kept.append(c)
        if len(kept) >= keep:
            break
    return kept


def find_candidates(episodes: list[Episode], scored: dict[int, dict], per_episode=3,
                    min_len=20.0, max_len=60.0) -> list[dict]:
    by_num = {ep.number: ep for ep in episodes}
    out = []
    for ep in sorted(episodes, key=lambda e: e.number):
        sc = scored[ep.number]["scores"]
        singles = nms(single_windows(ep, sc, min_len, max_len), per_episode)
        nxt = by_num.get(ep.number + 1)
        stitched = nms(stitched_windows(ep, nxt, sc, scored[nxt.number]["scores"] if nxt else {},
                                        min_len, max_len), 1)
        # keep a stitched clip only if it beats this episode's weakest single
        if stitched and (len(singles) < per_episode or stitched[0]["score"] > singles[-1]["score"]):
            singles.append(stitched[0])
        out.extend(singles)
    return out
