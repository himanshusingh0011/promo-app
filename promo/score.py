"""Line scoring: how good is each line as a HOOK (first 3 s) and as a CLIFFHANGER (last moment)?

Two interchangeable scorers with the same output:
  - llm_score(): one AI call per episode (or per batch of episodes). The AI only gives
    numbers + a short reason for line ids; it never writes timestamps.
  - heuristic_score(): keyword + emotion-tag rules, no AI. Used as the offline mode and as
    the baseline the AI version is compared against.

Output per episode: {event_idx: {"hook": 0-10, "cliff": 0-10, "ctx": 0-2, "why": str}}
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from .config import LLMConfig
from .llm import chat, parse_json, LLMError
from .parse import Episode, compact_episode

SYSTEM = """You are a senior promo editor for vertical microdrama ads (TikTok, Reels, Shorts).
You read numbered screenplay lines and mark the moments that could start or end a 20-60 second promo clip.

For each notable line give:
- hook (0-10): if this line is in the FIRST 3 SECONDS of a clip, would a stranger scrolling past stop?
  High: slap or violence, public humiliation, shocking reveal, cruel or explosive line, kiss, arrest, collapse.
  Low: calm talk, travel, setup, lines that only make sense with backstory.
- cliff (0-10): is this a strong LAST moment to cut on? High: unresolved threat, question, reveal or decision
  that makes a viewer need the next part. A line that resolves or relaxes the tension gets 0-2.
- ctx (0-2): prior knowledge a stranger needs to follow this line (0 none, 1 some, 2 a lot).
- why: at most 12 plain words on what makes it work (e.g. "sister reveals she is marrying the groom").

Rules: list the 8-20 most notable lines per episode, skip the rest (they count as 0).
Use the exact ids shown in brackets, like "12.34". Output JSON only, no commentary."""

USER_TMPL = """{episodes}

Return JSON exactly like:
{{"episodes": [{{"episode": <number>, "lines": [{{"id": "<ep>.<line>", "hook": 0, "cliff": 0, "ctx": 0, "why": "..."}}]}}]}}"""


def _clip(x, lo, hi, default=0.0) -> float:
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return default


def _scores_from_reply(data, episodes: list[Episode]) -> dict[int, dict]:
    """Map the AI's ids back to events. Unknown ids are dropped (and counted)."""
    by_ep = {ep.number: ep for ep in episodes}
    out: dict[int, dict] = {ep.number: {} for ep in episodes}
    items = []
    blocks = data.get("episodes") or [] if isinstance(data, dict) else data if isinstance(data, list) else []
    for block in blocks:
        if isinstance(block, dict) and "lines" in block:
            items.extend(block.get("lines") or [])
        elif isinstance(block, dict) and "id" in block:   # model skipped the episode wrapper
            items.append(block)
    if isinstance(data, dict) and "lines" in data:
        items.extend(data["lines"])
    bad = 0
    for it in items:
        try:
            ep_s, lid_s = str(it.get("id", "")).split(".", 1)
            ep = by_ep[int(ep_s)]
            ev = ep.by_lid()[int(lid_s)]
        except (ValueError, KeyError, AttributeError, TypeError):
            bad += 1
            continue
        out[ep.number][ev.idx] = {
            "hook": _clip(it.get("hook"), 0, 10),
            "cliff": _clip(it.get("cliff"), 0, 10),
            "ctx": _clip(it.get("ctx"), 0, 2, 1.0),
            "why": str(it.get("why", ""))[:120],
        }
    out["_bad_ids"] = bad
    return out


def llm_score(episodes: list[Episode], cfg: LLMConfig, log=print) -> dict[int, dict]:
    """Returns {episode_number: {"scores": {...}, "raw": str, "meta": {...}, "error": str|None}}."""
    batches = [episodes[i: i + cfg.batch] for i in range(0, len(episodes), cfg.batch)]
    results: dict[int, dict] = {}

    def run(batch: list[Episode]):
        prompt = USER_TMPL.format(episodes="\n\n".join(compact_episode(ep) for ep in batch))
        max_tok = min(cfg.max_tokens * len(batch), 32000)
        try:
            text, meta = chat(cfg, SYSTEM, prompt, max_tokens=max_tok)
            parsed = _scores_from_reply(parse_json(text), batch)
            err = None
        except (LLMError, AttributeError, TypeError) as e:
            text, meta, parsed, err = "", {}, {ep.number: {} for ep in batch}, str(e)
        nums = ", ".join(str(ep.number) for ep in batch)
        tag = "cache" if meta.get("cached") else f"{meta.get('seconds', 0)}s"
        log(f"  episodes {nums}: {'ERROR ' + err if err else 'ok'} ({tag}, bad ids: {parsed.get('_bad_ids', 0)})")
        return batch, text, meta, parsed, err

    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        for batch, text, meta, parsed, err in pool.map(run, batches):
            for ep in batch:
                scores = parsed.get(ep.number, {})
                ep_err = err
                if ep_err or not scores:
                    # never leave an episode empty: fall back to rules and say so
                    scores = heuristic_score(ep)
                    ep_err = ep_err or "AI returned no usable lines"
                results[ep.number] = {"scores": scores, "raw": text, "meta": meta, "error": ep_err,
                                      "scorer": "heuristic-fallback" if ep_err else "ai"}
    return results


# ---------------------------------------------------------------- heuristic (no AI)

HOT_TONES = set("""outraged furious enraged livid screaming shouting yelling roaring gloating mocking cruel venomous
menacing threatening desperate shocked horrified stunned sobbing gasping contemptuous smug sneering accusing
defiant icy vicious hysterical panicked terrified frantic seething explosive savage murderous triumphant
humiliated disgusted bitter dangerous lethal ruthless commanding cold scornful arrogant
betrayed heartbroken devastated incredulous raging fierce hostile shaking trembling pleading begging
unforgiving merciless sinister condescending dismissive possessive protective alarmed urgent""".split())
HOOK_WORDS = re.compile(r"\b(slap\w*|strik\w*|punch\w*|kiss\w*|grab\w*|shov\w*|throw\w*|threw|collaps\w*|faint\w*|"
                        r"blood\w*|knife|blade|dagger|sword|gun|pistol|poison\w*|chok\w*|shatter\w*|smash\w*|"
                        r"scream\w*|arrest\w*|chain\w*|gallows|noose|burn\w*|drag\w*|pregnan\w*|dead|die|kill\w*|"
                        r"murder\w*|witch\w*|betray\w*|whore|liar|traitor|thief|bastard|divorce|disown\w*|"
                        r"gasp\w*|duke|heir|crown|hang\w*|execut\w*)\b", re.I)
CLIFF_WORDS = re.compile(r"\b(will|unless|before|tonight|tomorrow|never|nobody|pay|regret|take|who|what|why|"
                         r"secret|truth|know|find out|or else|dare|end|destroy|ruin|lose)\b", re.I)
CLIFF_SFX = re.compile(r"cliffhanger|ominous|cut to black|swell|silence|freeze|sting|thunder|slam|gasp", re.I)
PRONOUN_START = re.compile(r"^(he|she|they|him|her|it|that|this|those|these|then)\b", re.I)


def heuristic_score(ep: Episode) -> dict[int, dict]:
    out: dict[int, dict] = {}
    dur = ep.duration or 1.0
    for e in ep.visible:
        text = e.text
        tones = {t.strip().lower() for t in re.split(r"[,/]| and ", e.tone) if t.strip()}
        hot = len(tones & HOT_TONES)
        hook = 1.5 * hot + 1.6 * len(HOOK_WORDS.findall(text))
        cliff = 0.0
        if e.kind == "dialogue":
            words = len(text.split())
            hook += 1.2 * text.count("!") + (1.0 if words <= 8 else 0) + (0.5 if re.search(r"\byou\b", text, re.I) else 0)
            cliff += 2.0 * ("?" in text) + 1.5 * ("..." in text or "…" in text) + 0.8 * len(CLIFF_WORDS.findall(text))
            cliff += 0.8 * hot
        elif e.kind == "sfx":
            cliff += 3.0 * bool(CLIFF_SFX.search(text))
            hook += 1.0 * bool(re.search(r"slap|crash|scream|gasp|shot|smash", text, re.I))
        else:  # action
            cliff += 1.0 * bool(CLIFF_SFX.search(text)) + 0.5 * len(HOOK_WORDS.findall(text))
        if e.end >= dur - 8:      # episodes are written to end on a cliffhanger
            cliff += 3.0
        ctx = 1.0 if PRONOUN_START.match(text) else 0.5
        h, c = min(10.0, 1.6 * hook), min(10.0, 1.5 * cliff)  # scale to the 0-10 range the AI uses
        if h >= 2 or c >= 2:
            why = []
            if hot:
                why.append(", ".join(sorted(tones & HOT_TONES)) + " delivery")
            kw = sorted({w.lower() for w in HOOK_WORDS.findall(text)})[:3]
            if kw:
                why.append("/".join(kw))
            if "?" in text and e.kind == "dialogue":
                why.append("open question")
            if e.end >= dur - 8:
                why.append("episode-ending beat")
            out[e.idx] = {"hook": round(h, 1), "cliff": round(c, 1), "ctx": ctx,
                          "why": "; ".join(why) or "emotional beat"}
    return out


def score_episodes(episodes: list[Episode], cfg: LLMConfig | None, log=print) -> dict[int, dict]:
    if cfg is not None and cfg.enabled:
        return llm_score(episodes, cfg, log=log)
    return {ep.number: {"scores": heuristic_score(ep), "raw": "", "meta": {}, "error": None, "scorer": "heuristic"}
            for ep in episodes}
