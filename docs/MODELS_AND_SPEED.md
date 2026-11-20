# Models, speed and cost

## Why this is fast

| Choice | Effect |
|---|---|
| The AI sees only dialogue, action and sound lines, with no camera lines | ~50k tokens for the whole 50-episode show instead of ~130k |
| The AI outputs only scores for the 8–20 notable lines per episode | ~300–600 output tokens per episode, the slow part of any LLM |
| Code builds the clips | Timestamps and duration rules cost no tokens, and the model can't break them |
| Reasoning effort set to `low` for reasoning models | Avoids thousands of hidden "thinking" tokens |
| Disk cache keyed on prompt and model | Re-runs and evaluation iterations are free |
| Parallel calls plus an optional requests-per-minute limit | Uses the full free-tier limit without 429 errors |
| `LLM_BATCH` (episodes per call) | Gets around per-day request caps on long-context models like Gemini |

## Measured on the real pack (50 episodes)

| Run | Time | Tokens |
|---|---|---|
| Gemini 3.6 Flash, free tier, `LLM_BATCH=10`, 5 scoring calls | **59 s scoring**, ~88 s with re-rank and cold reader | 69k in / 15k out |
| Same, served from cache (re-run) | < 1 s | 0 |
| Offline rules | 0.3 s | 0 |

Free-tier gotchas I hit: `gemini-2.5-flash` is closed to new keys (404); `gemini-3.8-flash` was overloaded (503); `gemini-3.5-flash` ran out of daily quota after about 10 calls (429). The client retries and then falls back, and each model has its own quota, so the judge runs on a different model.

## Estimated time for one 50-episode show

| Option | Time | Setup | Notes |
|---|---|---|---|
| Offline rules | < 5 s | none | Baseline. Weaker picks (see the evaluation) |
| Cerebras free | ~2–4 min | 2 min, key only | Very fast generation. Cap is about 1M tokens a day, enough for ~15 shows |
| Gemini free, `LLM_BATCH=10` | **~1.5 min (measured)** | 2 min, key only, no card | 5 calls in total. Free limits change often |
| Self-hosted 32 GB GPU, Ollama, `qwen3:30b-a3b-instruct-2507-q4_K_M` (not tested) | ~6–10 min one call at a time, ~3–5 min with 4 parallel | ~20 min | No rate limits. Data never leaves the company's servers |
| Groq free | ~12–25 min | key only | Per-minute token cap is the bottleneck |

These are estimates based on token counts and typical speeds, not benchmarks. The real run time is printed in `run_log.txt` and `report.md`.

## Is self-hosting worth it?

- **For one show:** a free Cerebras or Gemini key is quicker to set up and about as fast.
- **Where a company GPU server wins:** (1) confidentiality, because the screenplays never leave the company; (2) no daily caps, so you can re-run as often as you like while tuning or evaluating; (3) cost at scale, because one GPU can process roughly 300–500 shows a day, far more than Kuku releases.

**Self-hosted setup (Ollama). I did not test this; it is how the same code would run on a GPU server:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
# allow 4 parallel requests and a longer context (needed if LLM_BATCH > 1)
sudo systemctl edit ollama   # add: Environment="OLLAMA_NUM_PARALLEL=4" "OLLAMA_CONTEXT_LENGTH=16384"
sudo systemctl restart ollama
ollama pull qwen3:30b-a3b-instruct-2507-q4_K_M     # ~19 GB, fits in 32 GB with room for 4 requests
# alternatives: gpt-oss:20b (~14 GB), qwen2.5:32b-instruct-q4_K_M (stronger writing, ~3x slower)
```

Either run the CLI on the server, or tunnel the port from your PC with `ssh -L 11434:localhost:11434 user@server` and set `LLM_BASE_URL=http://localhost:11434/v1`. Older GPUs without bfloat16 or FlashAttention 2 work too: Ollama handles that automatically, and with vLLM use `--dtype half`.

The Vercel app can't reach a GPU behind your network. Use a hosted key there, or expose the server through a tunnel with a password.

## Cost at Kuku's volume (paid APIs)

One show uses ≈ 50k input and ≈ 15k output tokens, plus ≈ 10k for the re-rank and cold-reader calls.

| Model class | ≈ cost per 50-episode show | 100 shows a week |
|---|---|---|
| Open model on a fast host (gpt-oss-120b class) | ~$0.02–0.05 | ~$2–5 |
| Flash-class (Gemini Flash) | ~$0.05–0.10 | ~$5–10 |
| Frontier (Claude Sonnet / GPT-class) | ~$0.40–0.80 | ~$40–80 |

Prices are rough list prices; check them before quoting. The human comparison: an editor watching 50 × 2-minute episodes is about 2 hours per show before picking anything. With this tool, the editor reviews the top 10 clips with their transcripts in about 10 minutes.
