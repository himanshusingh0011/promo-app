"""Minimal OpenAI-compatible chat client (standard library only).

- Works with any /chat/completions endpoint (Cerebras, Gemini, Groq, OpenRouter,
  OpenAI, Ollama, vLLM...).
- Disk cache: the same prompt + model is never paid for twice, so re-runs are instant.
- Retries 429 / 5xx with backoff, honours Retry-After, optional requests-per-minute limit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import LLMConfig


class LLMError(RuntimeError):
    pass


_lock = threading.Lock()
_last_call = [0.0]


def _throttle(rpm: int) -> None:
    if rpm <= 0:
        return
    gap = 60.0 / rpm
    with _lock:
        wait = _last_call[0] + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()


def _post(url: str, body: dict, key: str, timeout: int) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "promo-finder/1.0")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chat(cfg: LLMConfig, system: str, user: str, max_tokens: int | None = None,
         use_cache: bool = True) -> tuple[str, dict]:
    """Returns (text, meta). meta has usage, seconds, cached flag."""
    if not cfg.enabled:
        raise LLMError("No model configured (set LLM_BASE_URL and LLM_MODEL).")
    body: dict = {
        "model": cfg.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": cfg.temperature,
        "max_tokens": max_tokens or cfg.max_tokens,
    }
    if cfg.json_mode:
        body["response_format"] = {"type": "json_object"}
    effort = os.environ.get("LLM_REASONING_EFFORT", "low" if "gpt-oss" in cfg.model else "")
    if effort:
        body["reasoning_effort"] = effort  # thinking tokens are slow and not needed for scoring

    key = hashlib.sha256(json.dumps([cfg.base_url, body], sort_keys=True).encode()).hexdigest()[:24]
    cache = Path(cfg.cache_dir) / f"{key}.json"
    if use_cache and cache.exists():
        hit = json.loads(cache.read_text(encoding="utf-8"))
        return hit["text"], {**hit.get("meta", {}), "cached": True}

    url = cfg.base_url + "/chat/completions"
    t0 = time.time()
    delay = 4.0
    last_err = ""
    net_fails = 0
    for attempt in range(6):
        _throttle(cfg.rpm)
        try:
            resp = _post(url, body, cfg.api_key, cfg.timeout)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:2000]
            last_err = f"HTTP {e.code}: {msg}"
            if e.code == 400 and ("response_format" in body or "reasoning_effort" in body):
                # some servers reject optional params; drop them and retry
                body.pop("response_format", None)
                body.pop("reasoning_effort", None)
                continue
            if e.code == 429 and ("PerDay" in msg or "per day" in msg.lower()):
                # daily quota is gone: waiting won't help, fail fast (episode falls back to rules)
                raise LLMError(f"daily quota exhausted for {cfg.model}: {msg[:200]}") from None
            if e.code in (429, 500, 502, 503, 504, 529):
                ra = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait = float(ra) if ra else delay
                except ValueError:
                    wait = delay
                time.sleep(min(wait, 60))
                delay *= 2
                continue
            raise LLMError(last_err) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = f"network: {e}"
            net_fails += 1
            if net_fails >= 2:  # endpoint is down or wrong: fail fast instead of waiting minutes
                raise LLMError(last_err) from None
            time.sleep(2)
    else:
        raise LLMError(f"gave up after retries: {last_err}")

    try:
        text = resp["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        raise LLMError(f"unexpected response: {str(resp)[:300]}") from None
    meta = {"usage": resp.get("usage", {}), "seconds": round(time.time() - t0, 2), "model": cfg.model, "cached": False}
    if use_cache and text.strip():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"text": text, "meta": meta}), encoding="utf-8")
    return text, meta


def parse_json(text: str):
    """Pull the JSON object out of a model reply (handles ```fences``` and <think> blocks)."""
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    t = re.sub(r"^```(?:json)?|```$", "", t.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a != -1 and b > a:
        try:
            return json.loads(t[a: b + 1])
        except json.JSONDecodeError:
            pass
    raise LLMError(f"model did not return valid JSON: {text[:200]!r}")


def items(data, *keys: str) -> list[dict]:
    """Normalise model replies to a flat list of dicts. Models wrap lists differently:
    {"clips": [...]}, [...], or [{"clips": [...]}]; this accepts all of them."""
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return items(data[k], *keys)
        return [data]
    out: list[dict] = []
    if isinstance(data, list):
        for x in data:
            if isinstance(x, dict) and any(isinstance(x.get(k), list) for k in keys):
                out.extend(items(x, *keys))
            elif isinstance(x, dict):
                out.append(x)
    return out

