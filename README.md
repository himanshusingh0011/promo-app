# Promo Finder

Reads microdrama screenplays and finds the best **20–60 second promo clips** in them. For each clip you get the episode and the start/end timestamps of every segment, the hook (first 3 s), the cliffhanger (last beat), one line on why it works, a rank, and warning flags that show where the tool may have picked badly.

- **Model-agnostic.** Any OpenAI-compatible API works: Cerebras, Gemini, Groq, OpenRouter, OpenAI, or your own GPU through Ollama or vLLM. Swapping models means changing 3 settings.
- **Fast and cheap.** One AI call per episode (or per 5–10 episodes on long-context models), and the AI sees about 1.2k tokens per episode. The whole 50-episode show is about 50k tokens in. Responses are cached, so re-runs are free.
- **The AI never writes timestamps.** It scores numbered lines. Code turns those scores into clips, snaps cuts to camera-shot boundaries and never cuts a line of dialogue in half.
- **Works with no AI at all.** `--offline` uses keyword and emotion-tag rules. This mode is the baseline in the evaluation.
- **No dependencies.** Python 3.10+ standard library only.

```
screenplay.txt ─► parse (code) ─► score lines: hook / cliff / context (AI or rules)
               ─► search 20–60 s windows + stitched clips (code) ─► rank (code, optional AI)
               ─► quality checks: hard rules + warning flags (code), cold-reader (optional AI)
```

## Run it

```bash
cp .env.example .env        # fill in ONE provider block (or skip and use --offline)
python -m promo check-llm   # one tiny call to confirm the key/model work

# put the episode .txt files (or the .zip) anywhere, e.g. data/show1/  (data/ is git-ignored)
python -m promo run --input data/show1 --out outputs/ai --rerank --judge
python -m promo run --input data/show1 --out outputs/offline --offline     # no-AI baseline
```

Each run writes these files to `--out`:

| File | What it is |
|---|---|
| `report.md` | Top 15 to post first, flag summary, every promo listed by episode |
| `promos.csv` | One row per promo, for an editor (open in Sheets or Excel) |
| `promos.json` | Everything: segments, hook, cliffhanger, why, score breakdown, flags, cold-reader notes, clip transcript |
| `raw/episode-NNN.json` | The unedited model reply and line scores for each episode |
| `run_log.txt` | Timings, cache hits, errors |

Useful flags: `--episodes 1-5` (run a subset), `--model <name>`, `--batch 10` (episodes per call), `--no-cache`.

## Web app (local or Vercel)

```bash
python serve.py           # http://localhost:8000
```

Upload `.txt` files or a `.zip`, choose AI or offline, and optionally paste your own base URL, model and key. The page also has a **Load made-up sample** button that loads 2 invented episodes. It never contains real show content. Screenplays are processed in memory and never stored.

**Deploy to Vercel:** push this repo to GitHub, then go to vercel.com → Add New Project → import the repo. Framework preset: **Other**. No build command is needed. Under Settings → Environment Variables, add `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` (optionally also `LLM_BATCH`, `JUDGE_*`, and `APP_PASSWORD` so strangers can't spend your quota). Then deploy. **Free-tier note:** Gemini's free tier allows about 20 requests per model per day. With `LLM_BATCH=10`, one 50-episode show is 5 requests, so set `JUDGE_MODEL` to a different model (e.g. `gemini-3-flash-preview`) to give the judge its own quota. If a model's daily quota runs out, the app fails fast and that upload falls back to rules, and it says so on screen. `public/` is served as static files, and `api/score.py` and `api/promos.py` are Python functions. The browser sends episodes in small chunks, so no single request hits the function time limit.

## Evaluation

```bash
python -m promo eval make --input data/show1 --ai outputs/ai/promos.json --rules outputs/offline/promos.json
python -m promo eval page      # local page to rate the shuffled clips (labels hidden); downloads blind_sheet_rated.csv
python -m promo eval score --sheet path/to/blind_sheet_rated.csv   # would-post rate per system + 95% CI
python -m promo eval judge     # same blind set rated by a cold-reader model
python -m promo eval reference --input data/show1   # AI vs rules vs random against eval/runs/reference_labels.json
python -m unittest discover -s tests -v
```

## Repo map

| Path | Role |
|---|---|
| `promo/parse.py` | Screenplay → timed events. Builds the compact prompt text without camera lines |
| `promo/score.py` | AI line scorer (prompt is here) and the offline rule scorer |
| `promo/search.py` | Window search, shot snapping, stitched clips, overlap removal |
| `promo/rank.py` | Rule ranking (early-episode bonus, diversity) and optional AI re-rank |
| `promo/check.py` | Hard validators, warning flags, cold-reader judge |
| `promo/llm.py` | OpenAI-compatible client: cache, retries, rate limit |
| `promo/evaluate.py` | Blind evaluation: AI vs rules vs random |
| `promo/web.py`, `api/`, `public/`, `serve.py` | Web app and Vercel functions |
| `docs/` | Solution doc, assumptions, models and speed, AI-usage notes |

**Confidentiality:** `data/`, `outputs/`, `eval/runs/` and every `.txt`/`.zip` file are git-ignored. The only exception is the made-up samples in `public/sample/`. Share raw outputs through a link-only Drive folder, not the public repo.
