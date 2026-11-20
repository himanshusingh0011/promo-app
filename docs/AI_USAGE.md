# How I used AI tools

| Tool | Used for |
|---|---|
| Claude Code (Claude Opus) | Pair-programming the pipeline, tests and web app; drafting docs that I then edited |
| Gemini 3.6 Flash (scorer, re-rank) and Gemini 3 Flash preview (cold-reader judge), free tier, through the OpenAI-compatible API | The product itself |

**What I kept for myself:** the problem framing, every assumption in `ASSUMPTIONS.md`, which parts go to AI and which stay as code, and the evaluation design (blind comparison against rules and random clips, rather than letting the model grade itself).

## Where the AI got it wrong (caught and fixed)

1. **Cuts that split dialogue.** The first version of the cut-snapping code (written with Claude) moved the end of a clip to "just before the next line". That fails when 2 characters' lines overlap in the script. The hard validator caught 2 of 25 clips cutting someone mid-sentence. Fix: when lines overlap, let the overlapping line finish. When a hook sits inside someone else's long line, drop that start entirely. Now 0 clips fail.
2. **Rule scorer too strict.** The first keyword and emotion-tag thresholds produced only 25 candidates across 50 episodes, and many episodes got none. I rescaled the scores to the 0–10 range the AI uses and added the tones that actually appear in these scripts ("Cold", "Scornful", "Betrayed"...). That gave 118 candidates.
3. **A wrong test.** One generated unit test expected the tone "Loud" for a line tagged `(Mocking, Loud)`. The parser was right and the test was wrong.
4. **Model-output risks the design guards against:** invented line ids (dropped and counted as `bad ids` in the log), JSON wrapped in prose or code fences (handled by the extractor), and models that reject `response_format` (the client retries without it).

5. **A stitched clip ran past the end of its episode.** The hook segment ended "0.2 s after the last line", which was beyond the end of Episode 8 (78 s long). The validator flagged 1 of 161 clips in the real run. Fix: clamp the end to the episode length.
6. **A judge model changed its JSON shape.** `gemini-3-flash-preview` sometimes returned `[{"clips": [...]}]` instead of `{"clips": [...]}`, and that crashed the run. Fix: one tolerant parser for all model replies, plus a unit test covering the 3 shapes.
7. **A retired model.** The default `gemini-2.5-flash` returned 404 for new keys, and `gemini-3.8-flash` returned 503 (overloaded). Switching to `gemini-3.6-flash` was a one-line `.env` change, which shows that swapping models really is easy.

## One bad pick the AI made (from the real run)
Promo **#4** (E2 00:53–01:48) ends on Juliana's dignified *"...I will not leave it believing I was the one who should be ashamed."* The AI scored that line 9/10 as a cliffhanger, but it resolves the scene: the cold reader marked it `ends_unresolved: false`, and none of my flags caught it. The model confuses a satisfying emotional win with suspense. Next step: add a "does the next line answer this?" check, or ask the scorer separately whether a line resolves tension.
