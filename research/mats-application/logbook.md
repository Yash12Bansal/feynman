# Research Logbook — fill as you go; this becomes your appendix

Why this file exists: Nanda scores truth-seeking and shows-your-work. A successful
10.0 applicant said keeping a logbook was what made the write-up possible. The
prediction table is the single most legible taste signal you can produce.

## 0. Prediction table (FILL BEFORE ANY EXPERIMENT — Hour 0–1)

| # | Hypothesis | My prediction (prob) | Why I believe this | Outcome | What I learned |
|---|---|---|---|---|---|
| H1 | Linear probe decodes user competence at mid layers, generalizes to held-out topics | __% | | | |
| H1b | Accuracy rises with turn index (evidence accumulation) | __% | | | |
| H1c | Explicit↔implicit probe transfer is high (shared representation, not keyword) | __% | | | |
| H2 | Estimate crosses 0.5 within ≤3 turns of evidence flip | __% | | | |
| H2b | Asymmetry: expert→novice updates FASTER than novice→expert | __% | | | |
| H2c | Anchoring gap > 0.1 (first impression persists) | __% | | | |
| H3 | Truth probe (trained on bare statements) works in-dialogue, held-out topics ≥ 65% | __% | | | |
| H3b | P(validate false claim): confident voice ≥ 2x hedged voice | __% | | | |
| H3c | Internal truth score is NOT corrupted by confident voice (stays low for false) | __% | | | |
| H4 | Steering shifts FK grade / judged level beyond random-direction control | __% | | | |
| H4b | Steering adapts covertly (no acknowledgment), unlike system-prompting | __% | | | |

Suggested priors if you have no idea: H1 ~80, H2 ~50 per direction, H3b ~40, H4 ~65.
Write YOUR numbers and YOUR reasons — the point is calibration, not correctness.

## 1. Time log (Toggl running; screenshot at the end)
| Session | Start | End | Hours | What |
|---|---|---|---|---|

Running total: __ / 20  (+ __ / 2 exec summary)

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
      judge gamed? — and checked the plausible ones
- [ ] Noted in this file WHAT I verified (goes in the write-up)

## 4. Human-read QC verdicts (from 02_qc_dialogues.py)
| Dialogue id | Feels like its level? | Notes |
|---|---|---|

Blind judge agreement: __ %   |  Length audit passed: yes/no  |  Leaks fixed: yes/no

## 5. E3 hand-verification (30 random judge verdicts)
| id | Judge said | I say | Agree? |
|---|---|---|---|
Agreement: __ / 30

## 6. Pivots & dead ends (write them down — "I got stuck, so I found a new angle
or identified why it didn't work" is scored ABOVE a clean success)
