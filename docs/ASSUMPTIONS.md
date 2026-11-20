# Assumptions

The brief says to make assumptions rather than ask. Each one below is something the brief left open; the second column says why I chose it.

| # | Assumption | Why |
|---|---|---|
| A1 | Screenplay timestamps match the final video closely enough to cut on. | They come with every line. If the video drifts, an editor nudges by a second, and the hook and cliff lines stay the same. |
| A2 | The hook must start within the first 3 s, so the clip starts at most 2 s before the hook line, on a shot boundary. | The brief says "first 3 seconds". 2 s leaves room for the line to land. |
| A3 | A clip ends shortly after the cliff line: it holds up to 2.5 s on the reaction shot, then cuts. | Microdrama promos cut on the reaction, not on silence. |
| A4 | Never cut a line of dialogue in half, at the start or the end. | A half-line looks broken. A hard validator enforces this. |
| A5 | 20–60 s is a hard limit; 25–45 s gets a small bonus. | The brief's range. Shorter promos usually do better on Reels and TikTok. |
| A6 | Stitched promos join 2 segments at most, from the same or the next episode, and only when the hook and cliff are too far apart for one clip. They get a penalty. | The brief allows joins, but every cut risks confusion, so the tool only stitches when it's worth it. |
| A7 | Promos from early episodes rank higher. | A new viewer who taps the ad lands on Episode 1. Early clips need less backstory, don't spoil later twists, and match what the viewer watches next. |
| A8 | Don't post several clips of the same scene, so repeats of an episode are penalised in the ranking. | A promo calendar needs variety. |
| A9 | The script is the only input; there's no video or audio. | That's all the pack contains. Visual-only moments (a look, a silent slap) are under-scored, and the tool flags them. |
| A10 | Camera lines are used for cut points but hidden from the AI. | This halves the tokens. Action lines already describe what happens. |
| A11 | "Makes sense on its own" is judged from the clip transcript alone, by a cold-reader model that has no show context. | That's how a scrolling stranger sees it. |
| A12 | The AI scores lines and code builds clips; the AI never outputs timestamps. | Models hallucinate numbers. Line ids are checked, and bad ids are dropped and counted. |
| A13 | If the AI fails on an episode, that episode falls back to rules and the report says so. | A run should never silently lose an episode. |
| A14 | One show per run. Episode numbers come from the file header, or from the file name if the header is missing. | Matches the input pack. |
| A15 | The input pack is confidential, so the repo and hosted app are upload-only, and raw outputs are shared through a link-only folder. | The brief's confidentiality note. |
| A16 | "Best" means best for winning new viewers, not for existing fans. | The brief: "to pull new viewers in". |
