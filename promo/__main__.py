"""CLI.

    python -m promo run --input <folder|zip|files...> --out outputs/run1 [--offline] [--rerank] [--judge]
    python -m promo check-llm            # one tiny call to confirm the key/model work
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from pathlib import Path

from . import pipeline, report
from .config import from_env
from .parse import parse_file, parse_text


def load_inputs(paths: list[str]):
    eps = []
    for p in map(Path, paths):
        if p.is_dir():
            files = sorted(p.rglob("*.txt"))
            eps.extend(parse_file(f) for f in files)
        elif p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                for n in sorted(z.namelist()):
                    if n.lower().endswith(".txt") and not n.startswith("__MACOSX"):
                        eps.append(parse_text(z.read(n).decode("utf-8", "replace"), Path(n).name))
        elif p.exists():
            eps.append(parse_file(p))
        else:
            sys.exit(f"not found: {p}")
    eps = [e for e in eps if e.events]
    seen, uniq = set(), []
    for e in sorted(eps, key=lambda e: e.number):
        if e.number not in seen:
            seen.add(e.number)
            uniq.append(e)
    return uniq


def main(argv=None):
    ap = argparse.ArgumentParser(prog="promo", description="Find promo clips in microdrama screenplays")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="find and rank promos")
    r.add_argument("--input", nargs="+", required=True, help="folder(s), .zip or .txt files")
    r.add_argument("--out", default="outputs/run")
    r.add_argument("--offline", action="store_true", help="no AI: rule-based scorer only")
    r.add_argument("--rerank", action="store_true", help="one extra AI call to order the top 20")
    r.add_argument("--judge", action="store_true", help="cold-reader AI check on the top clips")
    r.add_argument("--judge-top", type=int, default=20)
    r.add_argument("--episodes", default="", help="subset, e.g. 1-5 or 1,3,7")
    r.add_argument("--model", help="override LLM_MODEL"); r.add_argument("--batch", type=int, help="episodes per AI call")
    r.add_argument("--no-cache", action="store_true")
    sub.add_parser("check-llm", help="send one tiny request to test your settings")
    ev = sub.add_parser("eval", help="blind evaluation: ai vs rules vs random")
    ev.add_argument("action", choices=["make", "page", "score", "judge", "reference"])
    ev.add_argument("--input", nargs="+", help="episodes (for random baseline windows)")
    ev.add_argument("--ai", default="outputs/ai/promos.json")
    ev.add_argument("--rules", default="outputs/offline/promos.json")
    ev.add_argument("-n", type=int, default=12, help="clips per system")
    ev.add_argument("--sheet", default="eval/runs/blind_sheet.csv", help="rated sheet for eval score")
    a = ap.parse_args(argv)

    cfg = from_env()
    if a.cmd == "check-llm":
        from .llm import chat
        if not cfg.llm.enabled:
            sys.exit("LLM_BASE_URL / LLM_MODEL not set (see .env.example)")
        t = time.time()
        text, meta = chat(cfg.llm, "Reply with JSON only.", 'Return {"ok": true}', max_tokens=50, use_cache=False)
        print(f"{cfg.llm.label()} -> {text.strip()[:80]!r} in {time.time() - t:.1f}s, usage {meta.get('usage')}")
        return

    if a.cmd == "eval":
        from . import evaluate
        if a.action == "make":
            if not a.input:
                sys.exit("--input is required for eval make")
            rules = a.rules if Path(a.rules).exists() else None
            print("wrote", evaluate.make(load_inputs(a.input), a.ai, rules, a.n))
        elif a.action == "reference":
            from . import reference
            if not a.input:
                sys.exit("--input is required for eval reference")
            res = reference.run(load_inputs(a.input), a.ai, a.rules)
            Path("eval/runs").mkdir(parents=True, exist_ok=True)
            Path("eval/runs/reference_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
            print(json.dumps(res, indent=2))
        elif a.action == "page":
            print("open in your browser:", evaluate.rating_page().resolve())
        elif a.action == "score":
            print(json.dumps(evaluate.score(Path(a.sheet)), indent=2))
        else:
            if not cfg.judge.enabled:
                sys.exit("set JUDGE_* or LLM_* in .env")
            print(json.dumps(evaluate.judge(cfg.judge), indent=2))
        return

    if a.model:
        cfg.llm.model = a.model
    if a.batch:
        cfg.llm.batch = a.batch
    if a.no_cache:
        cfg.llm.cache_dir = str(Path(cfg.llm.cache_dir) / f"nocache-{int(time.time())}")
    eps = load_inputs(a.input)
    if a.episodes:
        want = set()
        for part in a.episodes.split(","):
            lo, _, hi = part.partition("-")
            want.update(range(int(lo), int(hi or lo) + 1))
        eps = [e for e in eps if e.number in want]
    if not eps:
        sys.exit("no episodes parsed")
    if not a.offline and not cfg.llm.enabled:
        print("No LLM configured -> running offline heuristic (set LLM_* in .env to use AI).")

    lines: list[str] = []

    def log(msg):
        print(msg, flush=True)
        lines.append(msg)

    res = pipeline.run(eps, cfg, use_ai=not a.offline, rerank=a.rerank, judge=a.judge, judge_top=a.judge_top, log=log)
    out = Path(a.out)
    report.write(res, out, lines)
    q = res["quality"]
    log(f"Done in {res['meta']['seconds_total']}s -> {out.resolve()}")
    log(f"  {len(res['promos'])} promos, hard checks passed {q['validator']['passed']}/{q['validator']['checked']}")
    (out / "run_log.txt").write_text("\n".join(lines), encoding="utf-8")
    for c in res["promos"][:5]:
        segs = " + ".join(f"E{s['episode']} {s['start_ts']}-{s['end_ts']}" for s in c["segments"])
        print(f"  #{c['rank']} {segs} ({c['duration']:.0f}s)  {c['hook']['text'][:60]!r} -> {c['cliffhanger']['text'][:50]!r}")


if __name__ == "__main__":
    main()
