# Promo Finder — Solution doc (Problem 1: Find the Promos)

## 1. Problem and why I picked it
Today an editor watches every episode to pick promo moments, and Kuku releases new shows every week, so this work grows with every show. The screenplays already contain what an editor looks for: timestamps, dialogue, an emotion tag on every line, and action and sound cues. A tool can read a 50-episode show in about 90 seconds and hand the editor a ranked shortlist to check instead of 2 hours of footage. The output is concrete (timestamps), so it is possible to measure whether the tool is right.

**Scope:** find, rank and quality-check promos from the script alone. No video, editing, music or captions. **Main assumptions** (full list in `ASSUMPTIONS.md`): screenplay timestamps are close enough to cut on; the hook line starts in the first 3 s; clips are 20–60 s and never cut a line of dialogue in half; promos from early episodes rank higher, because a new viewer who taps the ad lands on Episode 1; stitched promos use at most 2 segments; "best" means best at winning new viewers.

## 2. How it works: AI for judgment, code for everything checkable

| Step | Who | What |
|---|---|---|
| Parse | Code | Every line becomes a timed event (speaker, emotion tag, text, scene, camera-shot boundaries) |
| Score | **AI**, 1 call per 10 episodes | Each notable line gets *hook* 0–10, *cliff* 0–10, *needs-context* 0–2 and a 12-word reason. The AI sees numbered lines with no camera lines (~1.4k tokens per episode) and returns **line ids, never timestamps** |
| Search | Code | Every hook line → cliff line window that is 20–60 s long. Starts snap to the shot just before the hook; ends hold briefly on the reaction shot; no dialogue line is split. A 2-segment stitched clip is added when hook and cliff are too far apart. Overlaps are removed |
| Rank | Code + AI | Clip score + early-episode bonus + a variety penalty. One extra AI call re-orders the top 20 the way a marketing lead would and writes the "why" |
| Check | Code + AI | Hard rules on 100% of clips; warning flags; a cold-reader model (a *different* model) that sees only the clip transcript |
| Human | Editor | Reviews the top 10 with transcripts and flags, and approves the final cut points |

**Model swap is 3 environment variables** for any OpenAI-compatible API (Gemini, Groq, Cerebras, OpenRouter, Ollama or vLLM on our own GPU). This was tested for real: Gemini 2.5 Flash is closed to new keys, so I moved to 3.6 Flash with a one-line change. If an episode's AI call fails, that episode falls back to rules and the report says so. The prototype is a CLI plus a web app (Vercel, upload-only), written in standard-library Python, with 12 unit tests.

## 3. Results on the full pack (50 episodes)
- **Run:** `gemini-3.6-flash` (free tier). Scoring took 59 s in 5 calls; 69k tokens in, 15k out; 0 invented line ids; 0 episodes on fallback. **161 promos, 161/161 pass the hard checks.**
- **Post first** (full list in `report.md`):
  1. **E3 01:24.0–02:20.5:** a stranger knocks out the guard → *"Lady Juliana... accept my hand."* Instant action, ends on an unanswered public proposal.
  2. **E1 00:39.0–01:30.9:** *"Because he is marrying me."* → her father refuses to look at her. The show's premise (betrayed at the altar) in one clip.
  3. **E16 00:14.3–00:52.8:** Alexander catches a thug's club mid-air → *"Harrington! Gerald Harrington paid us!"* Action hook, ends on a confession.
- **Outputs** (link-only folder): `report.md`, `promos.csv`, `promos.json`, `raw/` (unedited model replies), `run_log_first_uncached.txt`.

## 4. How I know it's good, and where it picks badly
The system is not allowed to grade itself on the rubric it optimises.
1. **Hard rules (code):** 161/161 pass: 20–60 s, segments inside the episode and in order, hook within 3 s, no split dialogue. These rules caught 2 real bugs during development (see `AI_USAGE.md`).
2. **Known-answer check:** the show's strongest hook is the Ep 1 altar reveal. The AI opens a promo on that exact line and ranks it **#2**. The rules-only version ranks its best Ep 1 clip **#28** and never opens on the reveal, because it rewards shouting and exclamation marks rather than meaning.
3. **Blind comparison.** The top 12 clips each from AI, rules-only and random 20–60 s windows were shuffled under neutral ids and rated by a cold-reader model (`gemini-3-flash-preview`, not the scorer) that sees only the transcript:

| Rated 5/5 by the cold reader | AI | Rules only | Random |
|---|---|---|---|
| "Would keep watching" | **11/12** | 6/12 | 4/12 |
| "Hooked in first 3 s" | **10/12** | 8/12 | 2/12 |
| Clear without backstory (≥4/5) | **9/12** | 8/12 | 8/12 |

   Only 1 of the AI's top 12 also appears in the rules top 12, so the AI step changes *what* gets picked. **Caveats:** 12 clips per system is small, and a model judge is generous (random clips still average 4.2/5 on keep-watching). The real test is the human blind sheet in `eval/runs/blind_sheet.csv`, scored with `python -m promo eval score`.
4. **Reference set (a "ground truth" for all 50 episodes).** Working only from the raw scripts, a separate model (Claude, a different family from the Gemini scorer) marked the best promo moments in every episode: 61 picks, 26 of them tier A ("post it"), and none in 4 episodes. A clip counts as a match when it covers at least half of a reference pick. Run it with `python -m promo eval reference --input <scripts>`; results are saved to `eval/runs/reference_results.json`.

| Against the reference set | AI | Rules only | Random (avg of 200) |
|---|---|---|---|
| Top 20 that are a reference pick | **18/20** | 16/20 | 9.5/20 |
| Top 20 that are a tier-A pick | **13/20** | 9/20 | 4.6/20 |
| Episodes where the #1 clip is a reference pick | **72%** | 52% | 53% |
| Tier-A picks found anywhere in the list | **26/26** | 22/26 | 21/26 |
| Picks found that also open on the same line (±5 s) | **57%** | 39% | 30% |

   What this shows: the AI's top of the list is mostly the moments an independent picker chose. Without the AI, the rules pick each episode's best clip no better than chance (52% vs 53%). The AI re-rank only reorders the top 20, so it can't change the top-20 numbers, but it moves tier-A matches in the top 10 from 7 to 9. "Found anywhere" is a lenient test, since even random windows cover 75% of picks, so the top-20 and #1-per-episode rows matter most. **Caveats:** this is a silver reference, not a human editor's. One labeller, no second opinion. I had seen the AI's top ~20 before labelling, which could bias the set towards it. A human editor's picks would replace this file directly, in the same format.
5. **Where it picks badly**, from the real run:
   - **#4 doesn't end on a cliffhanger.** E2 ends on Juliana's dignified *"...I will not leave it believing I was the one who should be ashamed."* The cold reader marked it "resolved", and no flag caught it. The AI scored a satisfying win as suspense.
   - **Needs backstory:** 4 of the top 20 confused the cold reader (e.g. "who is the Bearded Man?"). 59 of 161 clips come from late episodes and get flagged for it.
   - **Stitched clips** (50 flagged): the jump between segments can confuse a stranger. 19 clips open on a pronoun ("he/she/that").
   - **Top picks run long** (52–56 s), so an editor may want to trim them for Reels. Visual-only beats (a silent look) are under-scored, because the script can't show how a moment plays on screen.

## 5. Scale and cost
One show ≈ 70k input + 15k output tokens. That's **~$0.02–0.10 per show** on flash or open models (~$2–10 for 100 shows a week) and ~$0.50 on a frontier model. It takes ~1.5 min per show on the Gemini free tier, and the cache makes re-runs free. On our own V100 (Ollama, Qwen3-30B-A3B): a few minutes per show, no per-token cost, and the scripts never leave our servers. The editor stays in the loop for the final cut: ~10 minutes of review per show instead of ~2 hours of watching. **Next steps:** use editor approve/reject decisions as labels to tune weights and prompts; add a "resolved ending" check (the #4 failure); add video and audio signals; A/B test the top picks with real ad spend, using click-through and Episode-1 completion as the true metric.

## 6. AI tools used
Claude Code for pair-programming and doc drafts; Gemini through its API inside the product. Where AI went wrong: the first cut-snapping code split dialogue whenever 2 lines overlapped, and a stitched clip ran past the end of its episode (both caught by my validator); the judge model returned a different JSON shape and crashed the run (fixed with a tolerant parser). Details are in `AI_USAGE.md`.
