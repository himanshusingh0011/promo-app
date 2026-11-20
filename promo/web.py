"""HTTP layer shared by Vercel functions (api/*.py) and the local server (serve.py).

POST /api/score   {files:[{name,text}], mode:"ai"|"offline", llm:{base_url,model,api_key,batch}}
                  -> line scores per episode (browser calls this in small chunks to avoid timeouts)
POST /api/promos  {files, scored, rerank, judge, llm} -> ranked promos + quality report
GET  /api/score   -> which model the server is configured with

Upload-only: no screenplay is stored or bundled. The server's API key is only ever sent to the
server's own LLM_BASE_URL; if a visitor supplies a different endpoint they must supply its key.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from dataclasses import replace
from http.server import BaseHTTPRequestHandler

from .config import from_env, Config
from .parse import parse_text
from .pipeline import promos_from_scores
from .score import score_episodes

MAX_FILES = 80
MAX_FILE_CHARS = 300_000


class BadRequest(Exception):
    pass


def _config(body: dict) -> tuple[Config, bool]:
    cfg = from_env()
    if os.environ.get("VERCEL"):
        cfg.llm.cache_dir = cfg.judge.cache_dir = "/tmp/promo-cache"
    o = body.get("llm") or {}
    server_key_used = True
    if o.get("base_url") and o["base_url"].rstrip("/") != cfg.llm.base_url:
        cfg.llm = replace(cfg.llm, base_url=o["base_url"].rstrip("/"), api_key=o.get("api_key", ""))
        server_key_used = False
    elif o.get("api_key"):
        cfg.llm = replace(cfg.llm, api_key=o["api_key"])
        server_key_used = False
    if o.get("model"):
        cfg.llm = replace(cfg.llm, model=o["model"])
    if o.get("batch"):
        cfg.llm = replace(cfg.llm, batch=max(1, min(10, int(o["batch"]))))
    if not server_key_used:  # visitor's own model also judges, unless they set nothing
        cfg.judge = replace(cfg.llm)
    return cfg, server_key_used


def _episodes(body: dict):
    files = body.get("files") or []
    if not files:
        raise BadRequest("no files uploaded")
    if len(files) > MAX_FILES:
        raise BadRequest(f"max {MAX_FILES} files per request")
    eps = []
    for f in files:
        text = str(f.get("text", ""))[:MAX_FILE_CHARS]
        ep = parse_text(text, str(f.get("name", "episode.txt")))
        if not ep.events:
            raise BadRequest(f"could not read any timed lines in {f.get('name')}")
        eps.append(ep)
    return sorted(eps, key=lambda e: e.number)


def _check_password(headers, cfg: Config, server_key_used: bool, wants_ai: bool):
    pw = os.environ.get("APP_PASSWORD")
    if pw and wants_ai and server_key_used and cfg.llm.enabled and headers.get("X-App-Password") != pw:
        raise PermissionError("this deployment needs the app password to use its AI key (or switch to offline / your own key)")


def api_score(body: dict, headers) -> dict:
    cfg, server_key = _config(body)
    wants_ai = body.get("mode", "ai") == "ai"
    _check_password(headers, cfg, server_key, wants_ai)
    eps = _episodes(body)
    t = time.time()
    scored = score_episodes(eps, cfg.llm if wants_ai and cfg.llm.enabled else None, log=lambda m: None)
    return {"seconds": round(time.time() - t, 2), "model": cfg.llm.label() if wants_ai and cfg.llm.enabled else "offline heuristic",
            "episodes": [{"number": ep.number, "name": ep.name, "scores": scored[ep.number]["scores"],
                          "scorer": scored[ep.number]["scorer"], "error": scored[ep.number]["error"]} for ep in eps]}


def api_promos(body: dict, headers) -> dict:
    cfg, server_key = _config(body)
    rerank, judge = bool(body.get("rerank")), bool(body.get("judge"))
    _check_password(headers, cfg, server_key, rerank or judge)
    eps = _episodes(body)
    scored = {int(s["number"]): {"scores": s.get("scores") or {}, "error": s.get("error"), "scorer": s.get("scorer")}
              for s in body.get("scored") or []}
    missing = [ep.number for ep in eps if ep.number not in scored]
    if missing:
        raise BadRequest(f"missing scores for episodes {missing}")
    t = time.time()
    res = promos_from_scores(eps, scored, cfg, rerank=rerank and cfg.llm.enabled, judge=judge, log=lambda m: None)
    res.pop("_rerank_raw", None)
    res["meta"] = {"episodes": len(eps), "seconds": round(time.time() - t, 2),
                   "rerank_model": cfg.llm.label() if rerank and cfg.llm.enabled else None,
                   "judge_model": cfg.judge.label() if judge and cfg.judge.enabled else None}
    return res


def api_info() -> dict:
    cfg = from_env()
    return {"ai_available": cfg.llm.enabled, "model": cfg.llm.model if cfg.llm.enabled else None,
            "batch": cfg.llm.batch, "password_required": bool(os.environ.get("APP_PASSWORD"))}


ROUTES = {"score": api_score, "promos": api_promos}


def handle(route: str, method: str, raw: bytes, headers) -> tuple[int, dict]:
    try:
        if method == "GET":
            return 200, api_info()
        body = json.loads(raw.decode("utf-8") or "{}")
        return 200, ROUTES[route](body, headers)
    except BadRequest as e:
        return 400, {"error": str(e)}
    except PermissionError as e:
        return 401, {"error": str(e)}
    except json.JSONDecodeError:
        return 400, {"error": "body must be JSON"}
    except Exception as e:  # pragma: no cover
        traceback.print_exc()
        return 500, {"error": f"{type(e).__name__}: {e}"}


def make_handler(route: str):
    class handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload: dict):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(*handle(route, "GET", b"", self.headers))

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self._send(*handle(route, "POST", self.rfile.read(n), self.headers))

        def log_message(self, *args):
            pass

    return handler
