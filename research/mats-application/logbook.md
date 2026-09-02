# Research Logbook — fill as you go; this becomes your appendix

Why this file exists: Nanda scores truth-seeking and shows-your-work. A successful
10.0 applicant said keeping a logbook was what made the write-up possible. The
prediction table is the single most legible taste signal you can produce.

## 0. Prediction table (FILL BEFORE ANY EXPERIMENT — Hour 0–1)

| #   | Hypothesis                                                                         | My prediction (prob, threshold, floor)                                | Why I believe this                                                                                                                                                                                                                                                                                                                                                                                                         | Outcome | What I learned |
| --- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | -------------- |
| H1  | Linear probe decodes user competence at mid layers, generalizes to held-out topics | p: 70%, t:55%, f:33%                                                  | I think model forms overall understanding beliefs of person's knowledge but I slightly doubt it will transfer that across other topics...                                                                                                                                                                                                                                                                                  |         |                |
| H1b | Accuracy rises with turn index (evidence accumulation)                             | p:60%, t:+8points, f:0                                                | 0.7 × chance that turn 3 beats turn 0 by the threshold (considering that to be 85%), given the probe works.                                                                                                                                                                                                                                                                                                                |         |                |
| H1c | Explicit↔implicit probe transfer is high (shared representation, not keyword)      | p:50%, t:at least 0.8 of same-set, or above 50%, f:33% absolute       | I am really 50-50 on whether the model will covert both into same internal belief....                                                                                                                                                                                                                                                                                                                                      |         |                |
| H2  | Estimate crosses 0.5 within ≤3 turns of evidence flip                              | p:55%, t:within 2-3 turns, f:never crosses                            | I think model observes when behaviour suddenly changes and it highlights it by praising or correcting us but given this hypo depends highly on H1 prob is kept at 55...                                                                                                                                                                                                                                                    |         |                |
| H2b | Asymmetry: expert→novice updates FASTER than novice→expert                         | p: 29%, t:at least 1 turn earlier, f:0 turns                          | a confident mistake from someone who sounded expert is hard to explain away, so the estimate should drop quickly but a novice suddenly using precise terms is an equally loud signal, so the two speeds are close. 0.55 × 0.53 ≈ 29. Tie-breaker: fraction-of-journey metric.                                                                                                                                              |         |                |
| H2c | Anchoring gap > 0.1 (first impression persists)                                    | p: 32%, t:0.1, f:0                                                    | Early novice turns stay in context and a sudden novice-to-expert jump is an unlikely story, so some first impression should survive; but recent turns may dominate and wash it out. 15 (curve never crosses) + 55 × 0.3 ≈ 32. Confound: turn-count mismatch, compare at turn 6 only; also run expert→novice.                                                                                                               |         |                |
| H3  | Truth probe (trained on bare statements) works in-dialogue, held-out topics ≥ 65%  | p: 40%, t:65%, f:50%                                                  | 128 training statements is very few and the false claims are subtle. Inside a dialogue the claim is followed by more text and a question, so the false signal may not reach the end-of-turn snapshot (≈60 given bare works). ≈70 that it works on bare statements -> 0.7 × 0.6 ≈ 40.                                                                                                                                       |         |                |
| H3b | P(validate false claim): confident voice ≥ 2x hedged voice                         | p: 40%, t: 2 or 15point gap                                           | a false claim ("since X, I figure...") is the classic sycophancy trigger, but a modern post-trained 8B model may correct it regardless of tone. S1 =55 (does model validate at all) and S2 = 70 (given it folds sometimes, how likely the hedged voice is validated less than half as often, gap ≥ 15 points)                                                                                                              |         |                |
| H3c | Internal truth score is NOT corrupted by confident voice (stays low for false)     | p: 25%, t: within 0.15 of hedged, f:no difference                     | Truth is about the world and tone should change what the model says, not what it represents, but a presupposed claim from a confident user is real persuasion pressure, so ≈60 that the internal score stays put given a working probe. 0.40 × 0.60 ≈ 24. Control: subtract the voice effect on true claims to remove style; equivalence bound 0.15 with ~40 per cell.                                                     |         |                |
| H4  | Steering shifts FK grade / judged level beyond random-direction control            | p:45%, t:atlest 2 grade levels more, f: random                        | Mean-difference steering found the refusal and persona directions and moved user-attribute behavior in prior work, but the best probe layer may not be the best steering layer and the push also lands on the assistant's own tokens, so ≈65 given a working probe. 0.70 × 0.65 ≈ 46. Pre-registered: 12 prompts instead of 4, and strength = largest with coherence ≥ 4/5; must beat random directions by 2 grade levels. |         |                |
| H4b | Steering adapts covertly (no acknowledgment), unlike system-prompting              | p: 22%, t: steered under 10%, prompted over 30%, f: same as prompting | Steered replies have no textual cue to mention, so ≈90 they stay silent; but a system prompt may be absorbed without comment too, so only ≈55 that prompted replies acknowledge the level ≥ 30% of the time. 0.45 × 0.90 × 0.55 ≈ 23. Measure: phrase list + yes/no judge on ~48 steered and 24 prompted replies, all hand-read.                                                                                           |         |                |

## 1. Time log (Toggl running; screenshot at the end)

| Session | Start | End | Hours | What |
| ------- | ----- | --- | ----- | ---- |

Running total: ** / 20 (+ ** / 2 exec summary)

## 2. Experiment log (one entry per run — copy the block)

### [date time] — [experiment]

- Prediction (from table / new):
- What I ran (exact command / commit):
- Result (numbers, figure path):
- Surprised? What's the DUMBEST alternative explanation? Checked how?
- Decision (continue / pivot / escalate model / add control):

## 3. Agent verification checklist (do EVERY session — Nanda: "the most important

advice in this doc"; applications died because write-up claims contradicted the
applicant's own numbers)

- [ ] Read ≥10 raw transcripts/data points the agent processed this session
- [ ] Re-derived one headline number independently (fresh one-liner)
- [ ] Read the code path that produced today's key result
- [ ] Asked: data leakage? trivial baseline? metric measuring something else?
  ```
  judge gamed? — and checked the plausible ones
  ```
- [ ] Noted in this file WHAT I verified (goes in the write-up)

## 4. Human-read QC verdicts (from 02_qc_dialogues.py)

| Dialogue id | Feels like its level? | Notes |
| ----------- | --------------------- | ----- |

Blind judge agreement: % | Length audit passed: yes/no | Leaks fixed: yes/no

## 5. E3 hand-verification (30 random judge verdicts)

| id              | Judge said | I say | Agree? |
| --------------- | ---------- | ----- | ------ |
| Agreement: / 30 |            |       |        |

## 6. Pivots & dead ends (write them down — "I got stuck, so I found a new angle

or identified why it didn't work" is scored ABOVE a clean success)
