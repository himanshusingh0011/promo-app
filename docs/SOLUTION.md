# Promo Finder
*Kuku AI Generalist Assignment · Problem 1: Find the Promos*

**Live app:** https://promo-app-olive.vercel.app · **Code:** https://github.com/himanshusingh0011/promo-app · **Raw outputs:** shared privately with the submission (it contains Kuku's confidential scripts)

**At a glance:** **161** promos found across 50 episodes · **161/161** pass the hard checks · **11/12** AI clips I'd post in a blind test (rules 9, random 4) · **$0.02–0.10** AI cost per show

## 1. The problem and why I picked it
Today an editor watches every episode to pick promo moments, and a new show ships every week. The work grows with every show, and it is mostly reading for two things: a hook and a cliffhanger. The screenplays already hold what an editor looks for: a timestamp, an emotion tag and action and sound cues on every line. A tool can read a 50-episode show in about 90 seconds and give the editor a ranked shortlist to check, instead of 2 hours of footage. The output is concrete (timestamps), so I can measure whether it is right.

**Scope:** find, rank and quality-check promos from the script alone. No video, editing or music. **Assumptions** (all 16 are in `docs/ASSUMPTIONS.md` in the repo): script timestamps are close enough to cut on; the hook starts within 3 s; clips are 20–60 s and never cut a line of dialogue in half; a stitched promo has at most 2 segments; earlier episodes rank higher, because a viewer who taps the ad lands on Episode 1; "best" means best at winning new viewers.

## 2. How it works: AI for judgment, code for everything checkable

| Step | Who | What |
|---|---|---|
| Parse | Code | Every line becomes a timed event: speaker, emotion, text, scene and camera-shot boundaries |
| Score | **AI**, 1 call per 10 episodes | Each notable line gets *hook* 0–10, *cliff* 0–10, *needs-context* 0–2 and a short reason. The AI sees numbered lines and returns **line ids, never timestamps**, so it cannot invent times |
| Search | Code | Builds every hook→cliff window of 20–60 s. Cuts snap to shot boundaries and never split dialogue. Adds 2-segment stitched clips and removes overlaps |
| Rank | Code + AI | Clip score + early-episode bonus + variety penalty. An optional AI call re-orders the top 20 |
| Check | Code + AI | Hard rules on every clip, warning flags, and a cold-reader check by a *different* model that sees only the transcript |
| Human | Editor | Reviews the top 10 with transcripts and flags, then sets the final cut |

**Swapping the model takes 3 environment variables** and works with any OpenAI-compatible API: Gemini, Groq, Cerebras, OpenRouter, or an open model on a self-hosted GPU through Ollama or vLLM. I used this for real when one Gemini model was retired mid-project. If an AI call fails, those episodes fall back to the rule scorer and the report says so. The code is standard-library Python with 12 unit tests. You can run it as a CLI or as the upload-only web app, and visitors can also plug in their own model and key there.

## 3. Results on all 50 episodes
`gemini-3.6-flash` on the free tier: 5 calls, about 59 s of scoring, 69k tokens in and 15k out. **161 promos; all 161 pass the hard checks.** The AI invented no line ids and no episode needed the fallback. The AI's top 3, with all 161 in `report.md`:
1. **E3 01:24–02:20:** a stranger knocks out a guard, then proposes in public. Instant action, and it ends on an unanswered proposal.
2. **E1 00:39–01:31:** the wedding betrayal, which is the whole premise of the show. The human test says the clip should start one line earlier (see section 5).
3. **E16 00:14–00:53:** the hero catches a thug's club mid-air, and the clip ends on a confession naming who paid them.

## 4. How I know it's good
No test asks the system to grade itself. AI, rules-only (no AI) and random 20–60 s windows were compared four ways:

| Test | AI | Rules only | Random |
|---|---|---|---|
| **Human blind rating:** "would post" (12 shuffled clips each) | **11/12** | 9/12 | 4/12 |
| Cold-reader model (different from the scorer): "keep watching" 5/5 | **11/12** | 6/12 | 4/12 |
| Reference picks (61 hand-marked moments): top 20 that match | **18/20** | 16/20 | 9.5/20 |
| Reference picks: episodes where the #1 clip is a pick | **72%** | 52% | 53% |

- **The tool clearly beats random:** 11 vs 4 in the human test (p ≈ 0.005), and every other test agrees.
- **AI vs rules-only leans AI in every test, but no single test proves it.** In the human test the 95% interval for the AI's advantage is −8 to +50 points, because 12 clips per system is too few to separate them. Settling it would need more raters and more clips per system.
- **The judges were checked against each other.** The human agreed with the reference picks on 81% of clips but with the model judge on only 69%. The model judge is generous: it gave 5/5 to random clips the human rejected. So I trust the human and the reference results more.
- **Hard checks:** 161/161 clips pass the length, order, no-split-dialogue and hook-within-3 s rules. These checks also caught 2 real bugs during development.
- **Caveats:** there was one rater: me, blind to the labels, but I had seen some of the output before rating. The reference picks were marked from the scripts by a different model family (Claude), after it had seen the AI's top 20. Both could favour the AI.

## 5. Where it picks badly
- **Right moment, cut too late.** The AI's #2 is the Episode 1 wedding betrayal. The rules-only version ranks that moment #28, but the human gave the AI's cut a hook of 1/5. The clip opens on an answer that starts with *"Because…"*, and the question it answers is cut off. Then it runs 52 s and ends on a silent reaction that reads as an ending. My "opens on a pronoun" flag checks *he/she/that* but not *because/and/but/so*. **Fix:** when the hook line answers something, start one line earlier.
- **Is the ending a cliffhanger? Judges disagree.** On #4, which ends on a dignified speech, the model judge said "resolved" but the human said "unresolved, would post". Ending quality is subjective, so the editor keeps the final say on it.
- **Needs backstory:** 59 of 161 clips come from late episodes and are flagged for it. The model judge was confused by unnamed characters in 4 of the top 20.
- **Stitched clips** (50 flagged) can jump awkwardly at the join. 19 clips open on a pronoun.
- **The rules-only version already finds strong hooks** (5 of 12 rated 5/5, against the AI's 4). The AI's gain is mostly in endings and clarity.
- **Top picks run long** (50–60 s), and silent visual beats are under-scored, because a script can't show how a moment plays on screen.

## 6. Scale and cost
One show is about 70k input and 15k output tokens: **about $0.02–0.10 per show** on flash or open models, so about $2–10 for 100 shows a week, or about $0.50 per show on a frontier model. Scoring takes about 1.5 min per show on the free tier, and cached re-runs are free. For confidential scripts, the same code can point at an open model (e.g. Qwen3-30B-A3B) on Kuku's own GPU server through Ollama or vLLM: no per-token cost, no daily limits, and the scripts never leave the company. That is a settings change; I did not test it here. Editor time should drop from about 2 hours of watching to about 10 minutes of review per show. **Next:** add the "because…" fix and a resolved-ending check; use editor approve/reject decisions as labels to tune the weights; add audio and video signals; A/B test the top picks with real ad spend, using click-through and Episode-1 completion as the true metric.

## 7. AI tools used
I used Claude Code for pair-programming, doc drafts and the reference labels, and Gemini (API) inside the product as the scorer and the judge. **Where AI got it wrong:** its first cut-snapping code split dialogue whenever 2 lines overlapped, and a stitched clip ran 0.2 s past the end of an episode. My validator caught both. The judge model also changed its JSON shape and crashed a run, which I fixed with a tolerant parser. And the scorer's #2 pick (section 5) was the right moment, cut badly. The full list is in `docs/AI_USAGE.md` in the repo.
