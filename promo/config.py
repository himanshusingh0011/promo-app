"""Settings. Everything comes from environment variables (or a local .env file),
so swapping the model is 3 values: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL.

Any OpenAI-compatible endpoint works: Cerebras, Gemini, Groq, OpenRouter,
OpenAI, a local Ollama / vLLM server, etc.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Tiny .env loader (no dependency). Real env vars win over the file."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    batch: int = 1            # episodes per call (use 5-10 for long-context models like Gemini)
    concurrency: int = 4      # parallel calls
    rpm: int = 0              # max requests per minute (0 = no client-side limit)
    max_tokens: int = 4000
    temperature: float = 0.2
    timeout: int = 120
    json_mode: bool = True    # send response_format=json_object (auto-disabled if the server rejects it)
    cache_dir: str = str(ROOT / ".cache" / "llm")

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)

    def label(self) -> str:
        return f"{self.model} @ {self.base_url}" if self.enabled else "offline heuristic"


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    judge: LLMConfig = field(default_factory=LLMConfig)  # cold-reader check; defaults to llm
    min_len: float = 20.0
    max_len: float = 60.0
    per_episode: int = 3          # promos kept per episode before global ranking
    early_episode_bonus: float = 1.0  # new viewers land on Ep 1, so early promos convert better


def from_env() -> Config:
    load_dotenv()
    llm = LLMConfig(
        base_url=os.environ.get("LLM_BASE_URL", "").rstrip("/"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        model=os.environ.get("LLM_MODEL", ""),
        batch=max(1, _int("LLM_BATCH", 1)),
        concurrency=max(1, _int("LLM_CONCURRENCY", 4)),
        rpm=_int("LLM_RPM", 0),
        max_tokens=_int("LLM_MAX_TOKENS", 4000),
        temperature=_float("LLM_TEMPERATURE", 0.2),
        timeout=_int("LLM_TIMEOUT", 120),
        json_mode=os.environ.get("LLM_JSON_MODE", "1") != "0",
    )
    if os.environ.get("LLM_CACHE_DIR"):
        llm.cache_dir = os.environ["LLM_CACHE_DIR"]
    judge = replace(
        llm,
        base_url=os.environ.get("JUDGE_BASE_URL", llm.base_url).rstrip("/"),
        api_key=os.environ.get("JUDGE_API_KEY", llm.api_key),
        model=os.environ.get("JUDGE_MODEL", llm.model),
    )
    return Config(llm=llm, judge=judge)
