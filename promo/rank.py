"""Global ranking: which promos to post first.

Rule-based rank (always): clip score + early-episode bonus (a new viewer who taps the ad lands
on Episode 1, so promos from early episodes need less context, spoil less, and match what they
watch next) + diversity (don't post five clips of the same scene).

Optional AI re-rank (--rerank): one call that reads the top N transcripts side by side and
orders them like an editor would, with a one-line reason.
"""
from __future__ import annotations

from .config import LLMConfig
from .llm import chat, parse_json, items, LLMError


def rule_rank(cands: list[dict], early_bonus: float = 1.0, n_episodes: int = 50) -> list[dict]:
    for c in cands:
        first = min(c["episodes"])
        bonus = early_bonus * max(0.0, 1 - (first - 1) / max(10, n_episodes * 0.4))
        c["parts"]["early_episode"] = round(bonus, 2)
        c["rank_score"] = round(c["score"] + bonus, 2)
    pool = sorted(cands, key=lambda c: -c["rank_score"])
    ranked, seen = [], {}
    while pool:  # greedy with a penalty for repeating an episode
        best = max(pool, key=lambda c: c["rank_score"] - 1.5 * sum(seen.get(e, 0) for e in c["episodes"]))
        pool.remove(best)
        for e in best["episodes"]:
            seen[e] = seen.get(e, 0) + 1
        ranked.append(best)
    for i, c in enumerate(ranked, 1):
        c["rank"] = i
    return ranked


RERANK_SYSTEM = """You are the head of performance marketing for a microdrama app. You choose which
promo clips to post first on TikTok/Reels to win NEW viewers who have never seen the show.
A great promo: hooks in the first 3 seconds, ends unresolved, and makes sense to a stranger.
Judge only from the clip transcripts given. Output JSON only."""

RERANK_USER = """Show premise (from Episode 1): {premise}

Candidate clips:
{clips}

Rank the best {k} clips to post first. Return JSON:
{{"ranking": [{{"id": "<clip id>", "why": "<one line, max 20 words, why post it this early>"}}]}}"""


def ai_rerank(ranked: list[dict], cfg: LLMConfig, premise: str, top_n: int = 20, k: int = 10, log=print) -> dict:
    top = ranked[:top_n]
    clips = "\n\n".join(f"[{c['id']}] ({c['duration']:.0f}s, episodes {c['episodes']})\n" + "\n".join(c["transcript"][:40])
                        for c in top)
    try:
        text, meta = chat(cfg, RERANK_SYSTEM, RERANK_USER.format(premise=premise, clips=clips, k=k), max_tokens=3000)
        order = [o for o in items(parse_json(text), "ranking", "clips") if "id" in o]
    except (LLMError, AttributeError, TypeError) as e:
        log(f"  AI re-rank failed ({e}); keeping rule ranking")
        return {"ok": False, "error": str(e)}
    ids = {c["id"]: c for c in top}
    picked = []
    for item in order:
        c = ids.get(str(item.get("id", "")).strip("[] "))
        if c and c not in picked:
            c["ai_why"] = str(item.get("why", ""))[:200]
            picked.append(c)
    rest = [c for c in ranked if c not in picked]
    ranked[:] = picked + rest
    for i, c in enumerate(ranked, 1):
        c["rule_rank"] = c.get("rank")
        c["rank"] = i
    log(f"  AI re-rank: {len(picked)} clips reordered ({meta.get('seconds', 'cache')}s)")
    return {"ok": True, "raw": text, "matched": len(picked), "returned": len(order)}
