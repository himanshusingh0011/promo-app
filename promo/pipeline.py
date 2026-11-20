"""End-to-end pipeline used by both the CLI and the web app.

parse (code) -> score lines (AI or rules) -> search windows (code) -> rank (code, optional AI)
-> quality checks (code, optional cold-reader AI)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from .check import validate, flags, cold_reader
from .config import Config
from .parse import Episode
from .rank import rule_rank, ai_rerank
from .score import score_episodes
from .search import find_candidates


def promos_from_scores(episodes: list[Episode], scored: dict[int, dict], cfg: Config, rerank: bool = False,
                       judge: bool = False, judge_top: int = 20, log=print) -> dict:
    eps = {ep.number: ep for ep in episodes}
    n = max(eps) if eps else 0
    cands = find_candidates(episodes, scored, cfg.per_episode, cfg.min_len, cfg.max_len)
    ranked = rule_rank(cands, cfg.early_episode_bonus, n)
    log(f"  {len(ranked)} promo candidates from {len(episodes)} episodes")

    rerank_info = None
    if rerank and cfg.llm.enabled:
        first = eps[min(eps)]
        rerank_info = ai_rerank(ranked, cfg.llm, first.logline, log=log)

    errors_total = 0
    for c in ranked:
        c["errors"] = validate(c, eps, cfg.min_len, cfg.max_len)
        c["flags"] = flags(c, eps, n)
        errors_total += bool(c["errors"])

    cold = None
    if judge and cfg.judge.enabled:
        log(f"  cold-reader check on top {judge_top} with {cfg.judge.model} ...")
        cold = cold_reader(ranked[:judge_top], cfg.judge, log=log)

    flag_counts: dict[str, int] = {}
    for c in ranked:
        for f in c["flags"]:
            key = f.split("(")[0].strip() if not f[0].isdigit() else "many speakers"
            flag_counts[key] = flag_counts.get(key, 0) + 1
    return {
        "promos": ranked,
        "quality": {
            "validator": {"checked": len(ranked), "passed": len(ranked) - errors_total},
            "flags": dict(sorted(flag_counts.items(), key=lambda kv: -kv[1])),
            "cold_reader": cold,
            "rerank": {k: v for k, v in (rerank_info or {}).items() if k != "raw"} or None,
            "episodes_on_fallback": [num for num, s in scored.items() if s.get("error")],
        },
        "_rerank_raw": (rerank_info or {}).get("raw", ""),
    }


def run(episodes: list[Episode], cfg: Config, use_ai: bool = True, rerank: bool = False, judge: bool = False,
        judge_top: int = 20, log=print) -> dict:
    t0 = time.time()
    episodes = sorted(episodes, key=lambda e: e.number)
    llm = cfg.llm if (use_ai and cfg.llm.enabled) else None
    log(f"Scoring {len(episodes)} episodes with {llm.label() if llm else 'offline heuristic'} ...")
    scored = score_episodes(episodes, llm, log=log)
    t_score = time.time() - t0
    res = promos_from_scores(episodes, scored, cfg, rerank=rerank and bool(llm), judge=judge,
                             judge_top=judge_top, log=log)

    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    seen = set()
    for s in scored.values():
        m = s.get("meta") or {}
        key = id(m)
        if key in seen or m.get("cached"):
            continue
        seen.add(key)
        for k in usage:
            usage[k] += int((m.get("usage") or {}).get(k, 0) or 0)

    res["meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scorer": llm.label() if llm else "offline heuristic",
        "judge": cfg.judge.label() if judge and cfg.judge.enabled else None,
        "episodes": len(episodes),
        "seconds_total": round(time.time() - t0, 1),
        "seconds_scoring": round(t_score, 1),
        "new_tokens": usage,
        "ai_replies_from_cache": f"{sum(1 for s in scored.values() if (s.get('meta') or {}).get('cached'))}/{len(scored)} episodes",
        "settings": {"min_len": cfg.min_len, "max_len": cfg.max_len, "per_episode": cfg.per_episode,
                     "batch": cfg.llm.batch, "rerank": rerank, "judge": judge},
    }
    res["episodes"] = [{"number": ep.number, "name": ep.name, "duration": round(ep.duration, 2),
                        "logline": ep.logline, "scorer": scored[ep.number].get("scorer"),
                        "error": scored[ep.number].get("error")} for ep in episodes]
    res["_scored"] = scored
    return res
