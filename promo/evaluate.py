"""Blind evaluation: is the AI pipeline actually better than simpler options, and by how much?

Three systems, mixed and shuffled so the rater can't tell which is which:
  ai        - top picks of the AI run
  rules     - top picks of the offline rule-based run (no AI)
  random    - random 20-60 s windows (the floor any tool must beat)

Outcome questions are about the clip as a real post, not about our internal scores:
  would_post (y/n), makes_sense_alone (y/n), hook_3s (1-5), ends_unresolved (y/n)

    python -m promo eval make  --input data/show1 --ai outputs/ai/promos.json --rules outputs/offline/promos.json
    (fill in eval/runs/blind_sheet.csv in Excel/Sheets)
    python -m promo eval score
    python -m promo eval judge   # same blind set, rated by a cold-reader model instead of a human
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from .parse import Episode, fmt_ts
from .search import transcript

RUNS = Path("eval/runs")
QUESTIONS = ["would_post (y/n)", "makes_sense_alone (y/n)", "hook_3s (1-5)", "ends_unresolved (y/n)", "notes"]


def random_windows(episodes: list[Episode], n: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    out = []
    while len(out) < n:
        ep = rng.choice(episodes)
        vis = ep.visible
        if not vis:
            continue
        s = rng.choice(vis)
        length = rng.uniform(20, 60)
        ends = [e for e in vis if e.end >= s.start + length - 3 and e.end - s.start <= 60]
        if not ends:
            continue
        e = ends[0]
        segs = [{"episode": ep.number, "start": s.start, "end": e.end, "start_ts": fmt_ts(s.start), "end_ts": fmt_ts(e.end)}]
        out.append({"segments": segs, "transcript": transcript(ep, s.start, e.end), "duration": round(e.end - s.start, 1)})
    return out


def make(episodes: list[Episode], ai_json: str, rules_json: str | None, n: int = 12, seed: int = 7) -> Path:
    pools = {"ai": json.loads(Path(ai_json).read_text(encoding="utf-8"))["promos"][:n]}
    if rules_json:
        pools["rules"] = json.loads(Path(rules_json).read_text(encoding="utf-8"))["promos"][:n]
    pools["random"] = random_windows(episodes, n, seed)
    items = [(sys, c) for sys, cs in pools.items() for c in cs]
    random.Random(seed).shuffle(items)
    RUNS.mkdir(parents=True, exist_ok=True)
    key, blind = {}, []
    for i, (sys, c) in enumerate(items, 1):
        cid = f"C{i:02d}"
        key[cid] = sys
        segs = " + ".join(f"E{s['episode']} {s['start_ts']}-{s['end_ts']}" for s in c["segments"])
        blind.append({"clip": cid, "segments": segs, "seconds": c["duration"],
                      "transcript": "\n".join(c["transcript"]), "_c": c})
    with open(RUNS / "blind_sheet.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clip", "segments", "seconds", "transcript"] + QUESTIONS)
        for b in blind:
            w.writerow([b["clip"], b["segments"], b["seconds"], b["transcript"]] + [""] * len(QUESTIONS))
    (RUNS / "blind_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    (RUNS / "blind_items.json").write_text(json.dumps(
        [{"clip": b["clip"], "transcript": b["_c"]["transcript"]} for b in blind], ensure_ascii=False), encoding="utf-8")
    return RUNS / "blind_sheet.csv"


def _yes(v) -> bool | None:
    v = str(v).strip().lower()
    return True if v in ("y", "yes", "1", "true") else False if v in ("n", "no", "0", "false") else None


def _bootstrap_diff(a: list[bool], b: list[bool], iters=4000, seed=1) -> tuple[float, float]:
    rng = random.Random(seed)
    diffs = []
    for _ in range(iters):
        sa = [rng.choice(a) for _ in a]
        sb = [rng.choice(b) for _ in b]
        diffs.append(sum(sa) / len(sa) - sum(sb) / len(sb))
    diffs.sort()
    return round(diffs[int(0.025 * iters)], 2), round(diffs[int(0.975 * iters)], 2)


def score(sheet: Path = RUNS / "blind_sheet.csv") -> dict:
    key = json.loads((RUNS / "blind_key.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(sheet, encoding="utf-8-sig")))
    by: dict[str, dict[str, list]] = {}
    for r in rows:
        sys = key.get(r["clip"])
        if not sys:
            continue
        d = by.setdefault(sys, {"post": [], "sense": [], "unres": [], "hook": []})
        for col, k in (("would_post (y/n)", "post"), ("makes_sense_alone (y/n)", "sense"), ("ends_unresolved (y/n)", "unres")):
            v = _yes(r.get(col, ""))
            if v is not None:
                d[k].append(v)
        try:
            d["hook"].append(float(r.get("hook_3s (1-5)", "")))
        except ValueError:
            pass
    rate = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    out = {sys: {"rated": len(d["post"]), "would_post": rate(d["post"]), "makes_sense_alone": rate(d["sense"]),
                 "ends_unresolved": rate(d["unres"]),
                 "hook_3s_avg": round(sum(d["hook"]) / len(d["hook"]), 2) if d["hook"] else None}
           for sys, d in by.items()}
    for other in ("rules", "random"):
        if "ai" in by and other in by and by["ai"]["post"] and by[other]["post"]:
            out[f"ai_minus_{other}_would_post_95ci"] = _bootstrap_diff(by["ai"]["post"], by[other]["post"])
    (RUNS / "blind_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def judge(cfg) -> dict:
    from .check import cold_reader
    key = json.loads((RUNS / "blind_key.json").read_text(encoding="utf-8"))
    items = json.loads((RUNS / "blind_items.json").read_text(encoding="utf-8"))
    cands = [{"id": it["clip"], "transcript": it["transcript"]} for it in items]
    cold_reader(cands, cfg, per_call=4)
    per: dict[str, list] = {}
    for c in cands:
        if c.get("cold"):
            per.setdefault(key[c["id"]], []).append(c["cold"])

    def avg(xs, k):
        v = []
        for x in xs:
            try:
                v.append(float(x.get(k)))
            except (TypeError, ValueError):
                pass
        return round(sum(v) / len(v), 2) if v else None

    out = {sys: {"judged": len(xs), "clear": avg(xs, "clear"), "hooked_in_3s": avg(xs, "hooked_in_3s"),
                 "keep_watching": avg(xs, "keep_watching"),
                 "ends_unresolved": round(sum(x.get("ends_unresolved") in (True, "true") for x in xs) / len(xs), 2)}
           for sys, xs in per.items()}
    out["judge_model"] = cfg.model
    (RUNS / "judge_results.json").write_text(json.dumps(
        {"summary": out, "clips": {c["id"]: {"system": key[c["id"]], **(c.get("cold") or {})} for c in cands}},
        indent=2, ensure_ascii=False), encoding="utf-8")
    return out


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blind Clip Rating</title><style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1f;--mut:#6b6b70;--line:#e2e0da;--acc:#9a5b2e;--sel:#f3e6dc}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1e;--ink:#eee;--mut:#9a9a9a;--line:#333;--acc:#d08a55;--sel:#3a2a1f}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
pre{white-space:pre-wrap;font:14px/1.55 ui-monospace,Consolas,monospace;margin:0}
.q{margin:14px 0}.q b{display:block;margin-bottom:6px}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:7px 14px;cursor:pointer;margin:0 6px 6px 0}
button.on{background:var(--sel);border-color:var(--acc)}button.main{background:var(--acc);color:#fff;border-color:var(--acc)}
.mut{color:var(--mut)}textarea{width:100%;box-sizing:border-box;font:inherit;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px}
.bar{height:6px;background:var(--line);border-radius:3px}.bar i{display:block;height:100%;background:var(--acc);border-radius:3px}
.nav{display:flex;justify-content:space-between;flex-wrap:wrap}
</style></head><body><main>
<h2 style="margin:0">Blind clip rating</h2>
<p class="mut">Each clip is a promo idea for a short drama. Imagine you are scrolling Instagram and know nothing about the show. Read the transcript (timestamps are seconds into the episode) and answer quickly, going with your first instinct.</p>
<div class="bar"><i id="bar"></i></div><p class="mut" id="pos"></p>
<div class="card"><div class="mut" id="meta"></div><pre id="tx"></pre></div>
<div class="card" id="qs"></div>
<div class="nav"><div><button id="prev">&larr; Back</button><button id="next" class="main">Next &rarr;</button></div>
<div><button id="dl">Download ratings CSV</button></div></div>
<p class="mut" id="msg"></p>
</main><script>
const ITEMS = __ITEMS__;
const Q = [["would_post (y/n)","Would you post this as an ad for the show?",["y","n"]],
 ["makes_sense_alone (y/n)","Does it make sense with no backstory?",["y","n"]],
 ["hook_3s (1-5)","Do the first 3 seconds make you stop scrolling? (1 = no, 5 = definitely)",["1","2","3","4","5"]],
 ["ends_unresolved (y/n)","Does it end on an unresolved moment (you want to know what happens next)?",["y","n"]]];
let R = {}; try { R = JSON.parse(localStorage.getItem("blind_ratings") || "{}"); } catch (e) {}
let i = 0;
const $ = id => document.getElementById(id);
function save(){ try { localStorage.setItem("blind_ratings", JSON.stringify(R)); } catch (e) {} }
function done(c){ const r = R[c] || {}; return Q.every(q => r[q[0]]); }
function show(){
  const it = ITEMS[i], r = R[it.clip] = R[it.clip] || {};
  $("pos").textContent = `Clip ${i+1} of ${ITEMS.length} · ${ITEMS.filter(x=>done(x.clip)).length} fully rated`;
  $("bar").style.width = (100*ITEMS.filter(x=>done(x.clip)).length/ITEMS.length) + "%";
  $("meta").textContent = `${it.clip} · ${it.seconds} s`;
  $("tx").textContent = it.transcript;
  $("qs").innerHTML = "";
  for (const [col, label, opts] of Q) {
    const d = document.createElement("div"); d.className = "q"; d.innerHTML = `<b>${label}</b>`;
    for (const o of opts) { const b = document.createElement("button"); b.textContent = o === "y" ? "Yes" : o === "n" ? "No" : o;
      if (r[col] === o) b.className = "on";
      b.onclick = () => { r[col] = o; save(); show(); }; d.appendChild(b); }
    $("qs").appendChild(d);
  }
  const n = document.createElement("div"); n.className = "q"; n.innerHTML = "<b>Notes (optional)</b>";
  const t = document.createElement("textarea"); t.rows = 2; t.value = r.notes || ""; t.oninput = () => { r.notes = t.value; save(); };
  n.appendChild(t); $("qs").appendChild(n);
  $("prev").disabled = i === 0; $("next").textContent = i === ITEMS.length-1 ? "Finish" : "Next →";
  window.scrollTo(0, 0);
}
$("prev").onclick = () => { if (i > 0) { i--; show(); } };
$("next").onclick = () => { if (!done(ITEMS[i].clip)) { $("msg").textContent = "Please answer all four questions first."; return; }
  $("msg").textContent = ""; if (i < ITEMS.length-1) { i++; show(); } else { $("msg").textContent = "All done. Click 'Download ratings CSV'."; } };
$("dl").onclick = () => {
  const cols = ["clip", ...Q.map(q => q[0]), "notes"];
  const esc = v => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  const lines = [cols.join(","), ...ITEMS.map(it => { const r = R[it.clip] || {}; return [it.clip, ...Q.map(q => r[q[0]] || ""), r.notes || ""].map(esc).join(","); })];
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["﻿" + lines.join("\n")], {type: "text/csv"}));
  a.download = "blind_sheet_rated.csv"; a.click();
  $("msg").textContent = `${ITEMS.filter(x=>done(x.clip)).length} of ${ITEMS.length} clips rated. Saved as blind_sheet_rated.csv in your Downloads folder.`;
};
show();
</script></body></html>"""


def rating_page(sheet: Path = RUNS / "blind_sheet.csv") -> Path:
    """Local, offline page to rate the blind sheet one clip at a time. No system labels inside."""
    rows = list(csv.DictReader(open(sheet, encoding="utf-8-sig")))
    items = [{"clip": r["clip"], "seconds": r["seconds"], "transcript": r["transcript"]} for r in rows]
    out = RUNS / "rate_clips.html"
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    out.write_text(PAGE.replace("__ITEMS__", data), encoding="utf-8")
    return out
