"""Writes run outputs: promos.json (everything), promos.csv (for editors), report.md (readable),
raw/ (the unedited AI replies and line scores per episode)."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def _segs(c: dict) -> str:
    return " + ".join(f"E{s['episode']} {s['start_ts']}-{s['end_ts']}" for s in c["segments"])


def public_result(res: dict) -> dict:
    return {k: v for k, v in res.items() if not k.startswith("_")}


def write(res: dict, out: Path, log_lines: list[str] | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "promos.json").write_text(json.dumps(public_result(res), indent=2, ensure_ascii=False), encoding="utf-8")

    with open(out / "promos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "type", "segments", "duration_s", "hook_at", "hook", "cliffhanger_at", "cliffhanger",
                    "why", "score", "flags", "errors"])
        for c in res["promos"]:
            w.writerow([c["rank"], c["type"], _segs(c), c["duration"],
                        f"E{c['hook']['episode']} {c['hook']['at']}", f"{c['hook']['who']}: {c['hook']['text']}",
                        f"E{c['cliffhanger']['episode']} {c['cliffhanger']['at']}",
                        f"{c['cliffhanger']['who']}: {c['cliffhanger']['text']}",
                        c.get("ai_why") or c["why"], c["rank_score"], "; ".join(c["flags"]), "; ".join(c["errors"])])

    raw = out / "raw"
    raw.mkdir(exist_ok=True)
    for num, s in res.get("_scored", {}).items():
        (raw / f"episode-{num:03d}.json").write_text(json.dumps(
            {"episode": num, "scorer": s.get("scorer"), "error": s.get("error"), "meta": s.get("meta"),
             "line_scores": s["scores"], "model_reply": s.get("raw", "")}, indent=2, ensure_ascii=False),
            encoding="utf-8")
    if res.get("_rerank_raw"):
        (raw / "rerank_reply.txt").write_text(res["_rerank_raw"], encoding="utf-8")
    if log_lines:
        (out / "run_log.txt").write_text("\n".join(log_lines), encoding="utf-8")
    (out / "report.md").write_text(markdown(res), encoding="utf-8")


def markdown(res: dict, top: int = 15) -> str:
    m, q = res["meta"], res["quality"]
    L = [f"# Promo finder report", "",
         f"- Scorer: **{m['scorer']}**  |  episodes: {m['episodes']}  |  runtime: {m['seconds_total']}s "
         f"(scoring {m['seconds_scoring']}s)  |  new tokens: {m['new_tokens']}  |  from cache: {m.get('ai_replies_from_cache', '-')}",
         f"- Candidates: {len(res['promos'])}  |  pass hard checks: {q['validator']['passed']}/{q['validator']['checked']}",
         f"- Episodes that fell back to rules: {q['episodes_on_fallback'] or 'none'}"]
    if q.get("cold_reader") and q["cold_reader"].get("judged"):
        cr = q["cold_reader"]
        L.append(f"- Cold-reader ({cr.get('model')}, top {cr['judged']}): clear {cr['clear_avg']}/5, "
                 f"hooked {cr['hooked_avg']}/5, keep watching {cr['keep_watching_avg']}/5, "
                 f"ends unresolved {int(cr['ends_unresolved_rate'] * 100)}%")
    L += ["", f"## Top {top} — post these first", "",
          "| # | Segments | Len | Hook (first 3 s) | Cliffhanger (last beat) | Why | Flags |",
          "|---|---|---|---|---|---|---|"]
    esc = lambda s: str(s).replace("|", "/").replace("\n", " ")
    for c in res["promos"][:top]:
        L.append(f"| {c['rank']} | {_segs(c)} | {c['duration']:.0f}s | {esc(c['hook']['who'])}: {esc(c['hook']['text'])[:110]} "
                 f"| {esc(c['cliffhanger']['who'])}: {esc(c['cliffhanger']['text'])[:110]} | {esc(c.get('ai_why') or c['why'])[:160]} "
                 f"| {esc('; '.join(c['flags'])) or '-'} |")
    L += ["", "## Warning flags across all candidates (where the tool may pick badly)", ""]
    L += [f"- {k}: {v}" for k, v in q["flags"].items()] or ["- none"]
    L += ["", "## All promos by episode", ""]
    for c in sorted(res["promos"], key=lambda c: (min(c["episodes"]), c["segments"][0]["start"])):
        L.append(f"- **#{c['rank']}** {_segs(c)} ({c['duration']:.0f}s, {c['type']}) — hook: "
                 f"\"{esc(c['hook']['text'])[:90]}\" → cliff: \"{esc(c['cliffhanger']['text'])[:90]}\"")
    return "\n".join(L) + "\n"
