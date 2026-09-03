# Research Logbook — fill as you go; this becomes your appendix

Why this file exists: Nanda scores truth-seeking and shows-your-work. A successful
10.0 applicant said keeping a logbook was what made the write-up possible. The
prediction table is the single most legible taste signal you can produce.

## 0. Prediction table (FILL BEFORE ANY EXPERIMENT — Hour 0–1)

| #   | Hypothesis                                                                         | My prediction (prob, threshold, floor)                                | Why I believe this                                                                                                                                                                                                                                                                                                                                                                                                         | Outcome | What I learned |
| --- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | -------------- |
| H1  | Linear probe decodes user competence at mid layers, generalizes to held-out topics | p: 70%, t:55%, f:33%                                                  | I think model forms overall understanding beliefs of person's knowledge but I slightly doubt it will transfer that across other topics...                                                                                                                                                                                                                                                                                  | YES. 98.5% held-out (layer 22); chance 33, shuffled 33, length-only 46. Raw cross-generator 61–68%, but 94% with thresholds refit and 97.6% pooled. | Competence is a shared linear direction in Qwen regardless of generator; only the calibration of 'intermediate' differs between generators. |
| H1b | Accuracy rises with turn index (evidence accumulation)                             | p:60%, t:+8points, f:0                                                | 0.7 × chance that turn 3 beats turn 0 by the threshold (considering that to be 85%), given the probe works.                                                                                                                                                                                                                                                                                                                | NO. Turn 0 already 96.6%; turn 3 − turn 0 = +3.4 (line was +8). | Ceiling effect I pre-registered in 4e: the first message gives the level away, so the curve cannot rise. |
| H1c | Explicit↔implicit probe transfer is high (shared representation, not keyword)      | p:50%, t:at least 0.8 of same-set, or above 50%, f:33% absolute       | I am really 50-50 on whether the model will covert both into same internal belief....                                                                                                                                                                                                                                                                                                                                      | YES. explicit→implicit 91.4%, implicit→explicit 96.7%; worse ÷ own-set = 0.92 (line 0.8). | Told and shown competence converge on one representation. I had this at 50-50; the model merges the two kinds of evidence. |
| H2  | Estimate crosses 0.5 within ≤3 turns of evidence flip                              | p:55%, t:within 2-3 turns, f:never crosses                            | I think model observes when behaviour suddenly changes and it highlights it by praising or correcting us but given this hypo depends highly on H1 prob is kept at 55...                                                                                                                                                                                                                                                    | YES. Crosses 0.5 within 1 turn of the switch in both directions (pooled and Codex probes). | The estimate does move on in-conversation evidence; it is not a static first-turn read. |
| H2b | Asymmetry: expert→novice updates FASTER than novice→expert                         | p: 29%, t:at least 1 turn earlier, f:0 turns                          | a confident mistake from someone who sounded expert is hard to explain away, so the estimate should drop quickly but a novice suddenly using precise terms is an equally loud signal, so the two speeds are close. 0.55 × 0.53 ≈ 29. Tie-breaker: fraction-of-journey metric.                                                                                                                                              | YES. e→n minus n→e journey fraction +0.31 [+0.16,+0.46] first switched turn, +0.26 [+0.16,+0.36] last turn. I had 29%. | One mistake downgrades the user almost fully in one turn; three turns of expert behaviour only get a novice 70% of the way up. |
| H2c | Anchoring gap > 0.1 (first impression persists)                                    | p: 32%, t:0.1, f:0                                                    | Early novice turns stay in context and a sudden novice-to-expert jump is an unlikely story, so some first impression should survive; but recent turns may dominate and wash it out. 15 (curve never crosses) + 55 × 0.3 ≈ 32. Confound: turn-count mismatch, compare at turn 6 only; also run expert→novice.                                                                                                               | YES for novice→expert (gap 0.28 [0.18,0.39]; control: history effect +0.30, writing effect 0). NO for expert→novice (0.03). I had 32%. | First impressions persist in one direction only: the model downgrades instantly and upgrades slowly and incompletely. |
| H3  | Truth probe (trained on bare statements) works in-dialogue, held-out topics ≥ 65%  | p: 40%, t:65%, f:50%                                                  | 128 training statements is very few and the false claims are subtle. Inside a dialogue the claim is followed by more text and a question, so the false signal may not reach the end-of-turn snapshot (≈60 given bare works). ≈70 that it works on bare statements -> 0.7 × 0.6 ≈ 40.                                                                                                                                       |         |                |
| H3b | P(validate false claim): confident voice ≥ 2x hedged voice                         | p: 40%, t: 2 or 15point gap                                           | a false claim ("since X, I figure...") is the classic sycophancy trigger, but a modern post-trained 8B model may correct it regardless of tone. S1 =55 (does model validate at all) and S2 = 70 (given it folds sometimes, how likely the hedged voice is validated less than half as often, gap ≥ 15 points)                                                                                                              |         |                |
| H3c | Internal truth score is NOT corrupted by confident voice (stays low for false)     | p: 25%, t: within 0.15 of hedged, f:no difference                     | Truth is about the world and tone should change what the model says, not what it represents, but a presupposed claim from a confident user is real persuasion pressure, so ≈60 that the internal score stays put given a working probe. 0.40 × 0.60 ≈ 24. Control: subtract the voice effect on true claims to remove style; equivalence bound 0.15 with ~40 per cell.                                                     |         |                |
| H4  | Steering shifts FK grade / judged level beyond random-direction control            | p:45%, t:atlest 2 grade levels more, f: random                        | Mean-difference steering found the refusal and persona directions and moved user-attribute behavior in prior work, but the best probe layer may not be the best steering layer and the push also lands on the assistant's own tokens, so ≈65 given a working probe. 0.70 × 0.65 ≈ 46. Pre-registered: 12 prompts instead of 4, and strength = largest with coherence ≥ 4/5; must beat random directions by 2 grade levels. |         |                |
| H4b | Steering adapts covertly (no acknowledgment), unlike system-prompting              | p: 22%, t: steered under 10%, prompted over 30%, f: same as prompting | Steered replies have no textual cue to mention, so ≈90 they stay silent; but a system prompt may be absorbed without comment too, so only ≈55 that prompted replies acknowledge the level ≥ 30% of the time. 0.45 × 0.90 × 0.55 ≈ 23. Measure: phrase list + yes/no judge on ~48 steered and 24 prompted replies, all hand-read.                                                                                           |         |                |

**Dataset notes (facts for the write-up).** Subject model: Qwen3-8B, thinking disabled.
Two generators wrote the main dialogues, on purpose: Codex (GPT family, via the ChatGPT
Pro CLI) — 536 dialogues kept, 4 rejected at merge for self-labels; Gemma-3-27B-it run
locally — 540 kept, 0 parse failures. Both: 12 topics × 3 levels, 4–8 user turns.
Extra Codex-only sets: explicit 144, reversal 96 (switch at user turn 4), truth 192
statements (8 true + 8 false per topic), honesty 190 (95 confident / 95 hedged; 95 true /
95 false claims; claim in user turn 3). Judges: Phi-4 locally (third family); Gemini via
API if a key is available; the results files record which one ran.
"Competence" is operationalized by the level definitions in config.py: presence of a
stated misconception, precision of terminology, type of question (what/why vs how/when vs
edge cases), and calibration of hedging. Length band and tone are the same for all levels.

**Biggest confound:** each generator writes each level in its own house style, so a probe
could read "Codex-novice-voice" instead of competence. Check: train the probe on Codex
dialogues and test on Gemma dialogues, and the reverse. If accuracy holds, the probe reads
something shared across styles. (Added after QC: the two generators also have OPPOSITE
length-by-level patterns, so cross-generator transfer cannot be carried by length either.)

## 1. Time log (Toggl running; screenshot at the end)

| Session | Start | End | Hours | What |
| ------- | ----- | --- | ----- | ---- |

Running total: ** / 20 (+ ** / 2 exec summary)

## 2. Experiment log (one entry per run — copy the block)

### 2026-09-02 ~20:45 UTC — E1: can a linear probe read user competence from Qwen's activations? (run v1)
- Prediction (from table): H1 70% that held-out-topic accuracy > 55% (floor 33%).
  H1b 60% that accuracy at turn 3 beats turn 0 by 8+ points (floor 0).
- What I ran: `python 04_probe_e1.py` at commit 964ac6c. Codex activations
  (activations/main.pt, 2748 snapshots from 536 dialogues, 37 layers). Probe = logistic
  regression on one layer's last-token vector. Train on 8 topics, test on the 4 held-out
  topics (immunology, chess, statistics, networking; 179 dialogues, 933 snapshots).
- Result (numbers): best layer 22. Held-out accuracy 98.5% per snapshot, 99.4% per
  dialogue at the final turn (178/179, CI 98.3–100). Accuracy is already 81% at layer 1,
  ~90% from layer 11, ~98% from layer 21 onward. Shuffled labels: 32.7% (chance).
  Topic control: 100%. Length-only classifier: 46.1%. Confusion on held-out: novice
  312/314, intermediate 299/301, expert 308/318 (10 experts called intermediate);
  novice↔expert swaps 0/933. Binary novice-vs-expert: 99.7%.
  Turn curve (one probe, all turns): 96.6% at turn 0, then 99–100%; turn 3 − turn 0 =
  +3.4 points. Recall by turn stays ~1.0 for every level.
  Cross-generator (train on one generator's training topics, test on the other's
  held-out topics): codex→gemma 67.6%, gemma→codex 60.7%, vs within-generator 98.5% and
  96.4%. Figures: figures/e1_layer_profile.png, figures/e1_turn_curve.png.
  H1c not run yet (explicit.pt did not exist at this run; it does now).
- Outcome vs prediction: H1 = YES, by a lot more than I predicted (98.5 vs my 55 line).
  H1b = NO. The rise is 3.4 points, below my 8-point line. Reason is the one I wrote in
  section 4e before running: the first user message already gives the level away
  (96.6% at turn 0), so there is no room to rise. This is a ceiling, not evidence
  against evidence accumulation.
- Surprised? Yes, twice. (1) 98.5% is far higher than I expected for a 3-way split with a
  fuzzy "intermediate" class, and much higher than the blind judges (52–71%). (2) The
  probe still calls late-turn novices "novice" (recall 1.0 at every turn) even though
  blind judges call those same late turns "intermediate" because the novice has learned.
  So the model's internal estimate does not drift with the user's learning inside the
  dialogue, OR the probe is reading something other than the user's current competence.
- DUMBEST alternative explanation: the probe is reading Codex's house style for each
  level (how GPT writes "a novice"), not competence. Checked with the cross-generator
  test, and it is PARTLY TRUE: a probe trained on Codex dialogues gets only 67.6% on
  Gemma dialogues (and 60.7% the other way). So roughly a third of the accuracy does not
  survive a change of generator. The generator-independent part is real (still double
  chance, and above the 46% length baseline) but much smaller than 98.5%.
  Other cheap explanations, ruled out: length (46%), topic leakage (held-out topics),
  self-labels (0 leaks), broken pipeline (shuffled = chance, topic control = 100%).
  The assistant's replies sit in the context and are pitched to the level, so they could
  leak it — but turn-0 accuracy (96.6%) has NO assistant turn in context, so the user's
  own words carry most of it.
- Decision: GO, with the cross-generator number reported next to the 98.5 everywhere the
  98.5 appears. Added to 04_probe_e1.py for run v2: cross-generator accuracy at every
  layer, the codex→gemma confusion matrix, a probe trained on BOTH generators, a test
  that keeps the Codex direction and refits only the thresholds on Gemma, and mean
  P(true class) by turn. Run v2 decides which probe E2–E4 use: the pooled probe if it
  matches within-generator accuracy within a few points, else the Codex probe with the
  caveat stated. Not escalating to 32B — the signal is not weak, it is too easy.


### [date time] — [experiment]

- Prediction (from table / new):
- What I ran (exact command / commit):
- Result (numbers, figure path):
- Surprised? What's the DUMBEST alternative explanation? Checked how?
- Decision (continue / pivot / escalate model / add control):

### 2026-09-02 ~21:15 UTC — E1 run v2: what exactly transfers across generators? + H1c
- Prediction: written in the v1 entry above — the cross-generator drop (61–68%) could be
  either a different direction per generator (bad: style leak) or the same direction with
  different thresholds (good: calibration). Pre-registered rule for the downstream probe:
  use the pooled probe if it is within a few points of within-generator accuracy.
- What I ran: `python 04_probe_e1.py` at commit d4872c2, now with explicit.pt present.
- Result (numbers):
  H1c transfer: explicit→implicit 91.4%, implicit→explicit 96.7%, own-set 98.9% / 98.5%.
  Worse transfer ÷ own-set = 0.92 (my line was 0.8).
  Cross-generator at layer 22, codex→gemma confusion (rows true, cols predicted):
  novice [291, 0, 0]; intermediate [266, 50, 0]; expert [3, 30, 282]. Extreme swaps 3/922.
  So the whole drop is ONE cell: Gemma intermediates get called novice.
  Codex direction + thresholds refit on Gemma: 94.1%.
  One probe trained on both generators: 97.6% on Codex held-out, 97.6% on Gemma held-out.
  Best raw-transfer layer is 14 (65.6 / 66.9) — no layer transfers well WITHOUT refitting
  thresholds, so this is not a layer choice problem.
  Drift: mean P(true class) by turn stays 0.94–1.0 for every level at every turn.
- Outcome vs prediction: H1c = YES (0.92 > 0.8). Told and shown competence land on the
  same internal representation; the explicit probe is not a keyword detector.
  H1 gets a sharper reading: the competence DIRECTION in Qwen is the same whoever wrote
  the dialogue (94% with only thresholds refit, 97.6% pooled); only the CALIBRATION
  differs — Gemma writes its "intermediate" closer to Codex's "novice". The raw 61–68%
  transfer was a threshold shift, not style leakage.
- Surprised? The clean separation into "direction shared / thresholds differ" was the
  best of the outcomes I listed; I expected something messier. Also: the model's internal
  estimate does NOT follow a novice's learning inside a dialogue (P(novice) ≈ 0.99 at the
  last turn even though blind judges call those turns "intermediate"). Either the belief
  is set early and sticks, or the probe reads the dialogue as a whole. E2 separates these.
- Dumbest alternative explanation for the pooled 97.6%: the pooled probe just learned two
  generator-specific rules side by side. Argument against: a single linear boundary cannot
  hold two different rules for the same three classes, and the refit-thresholds test shows
  the Codex direction alone already gets 94% on Gemma. Not fully closed; noted as a limit.
- Decision: downstream probe = probe_e1_pooled.joblib (within 1 point of within-generator,
  as pre-registered). Codex probe kept as a robustness check for E2. Proceed to E2.

### 2026-09-02 ~21:40 UTC — E2: does the internal estimate UPDATE when the user's behaviour flips?
- Prediction (from table): H2 55% (crosses 0.5 within 3 turns of the flip, both directions);
  H2b 29% (expert→novice faster by ≥ 0.15 journey fraction, CI clear of 0);
  H2c 32% (anchoring gap > 0.1).
- What I ran: `PROBE_FILE=probe_e1_pooled.joblib python 05_dynamics_e2.py` (primary, pooled
  probe, layer 22) and `python 05_dynamics_e2.py` (Codex probe, robustness), commit 2789687.
  Frozen probe applied to every turn of the 96 reversal dialogues (48 per direction,
  6 user turns, behaviour flips at user turn 4). Baselines from consistent dialogues at the
  same turn index (turn 6): novice 0.001, expert 0.983 (n=60, 61).
- Result (pooled probe; Codex probe in brackets):
  novice→expert: crosses 0.5 one turn after the switch [0]; journey fraction 0.39 [0.53]
  on the first switched turn, 0.71 [0.76] by the last turn.
  expert→novice: crosses on the first switched turn [0]; journey fraction 0.70 [0.76]
  on the first switched turn, 0.97 [0.97] by the last turn.
  H2b asymmetry (e→n minus n→e): +0.31 [+0.16, +0.46] at the first switched turn,
  +0.26 [+0.16, +0.36] at the last. Codex probe: +0.23, +0.22, both CIs clear of 0.
  H2c anchoring at turn 6: novice→expert still 0.28 [0.18, 0.39] below a lifelong expert
  (Codex probe 0.24); expert→novice only 0.03 [0.01, 0.05] above a lifelong novice.
  Figure: figures/e2_update_curves.png. Results: results_e2.json.
- Outcome vs prediction: H2 = YES (both directions cross within one turn).
  H2b = YES, and I had it at 29% — surprise. One slip and the model downgrades the user
  almost completely in a single turn; three turns of expert behaviour only get a novice
  70% of the way up.
  H2c = YES in one direction (novice start persists, gap 0.28 > 0.1), NO in the other
  (expert start does not protect: gap 0.03). Provisional until the control below runs.
- Fits with E1: novices who learned naturally never moved the estimate at all (P(novice)
  ≈ 0.99 at their last turn). Same shape: upgrading needs strong sustained evidence,
  downgrading needs one mistake.
- DUMBEST alternative explanation for the anchoring gap: the writer, not the model.
  Codex may write post-switch expert turns less convincingly than lifelong experts, so
  the 0.28 gap would be a property of the text. Journey-fraction normalisation does NOT
  rule this out. Control added: feed the model ONLY the post-switch turns (history cut
  off) and read the probe there (`python 03_extract_activations.py reversal_postonly`,
  then rerun 05). If isolated post-switch expert turns score like a lifelong expert, the
  gap comes from the history = real anchoring. If they score ~0.7 in isolation, it is the
  writing. NOT YET RUN — H2c stays provisional.
  Second caution: the probe is saturated (0.001 / 0.983), so a mean of 0.39 likely means
  "39% of dialogues have flipped", not "each dialogue is at 0.39". Per-dialogue flip
  fractions added to 05; report which reading is right.
  Third: the assistant's post-switch replies (also written by the generator, pitched to
  the new level) are in the context and count as evidence. Applies equally to both
  directions, so it cannot create the asymmetry by itself.
- Decision: keep going. Run the post-only control first thing tomorrow before writing
  anything about anchoring. Then E3.

#### Update 2026-09-03 morning — H2c control ran (commit 2bf9d80)
- Prediction for this control: none was written down before it ran (time pressure that
  morning). The pre-registered bet that applies is the H2c row itself (32%, written before
  any E2 result). Recording this gap honestly rather than back-filling a prediction.
- What I ran: `python 03_extract_activations.py reversal_postonly` (the same 96 dialogues
  with everything before the switch cut off, 288 snapshots), then E2 again with the
  pooled probe.
- Result: novice→expert post-switch turns in isolation score 1.000 (lifelong expert 0.983);
  with the novice history attached, 0.702. History effect +0.30 [+0.21, +0.40].
  Writing effect −0.02 [−0.04, −0.00] — the post-switch expert turns are, if anything,
  written slightly STRONGER than lifelong experts. expert→novice: history effect +0.03
  [+0.01, +0.05], writing effect 0.
  Flip fractions (share of dialogues past 0.5): novice→expert 0.42 / 0.58 / 0.73 on the
  three switched turns; expert→novice 0.73 / 0.92 / 1.00. About a quarter of dialogues sit
  in the middle band (0.2–0.8) at any time, so the curves are mostly per-dialogue flips.
- Outcome: H2c = YES for novice→expert, confirmed. The gap is caused by the history, not
  the writing. Asymmetric: a novice start costs 0.30 of expert-probability after three
  expert turns; an expert start costs 0.03 after three novice turns.
  Plain statement for the write-up: after three turns of clearly expert behaviour, 27% of
  users who started as novices are still classified as novices; after three turns of
  novice behaviour, 0% of users who started as experts are still classified as experts.
- Checked and ruled out: token-position effects (lifelong experts at the same turn index
  read 0.98); hidden back-references inside the post-switch text (same text in isolation
  reads 1.00).
- Still open (optional follow-up, `reversal_userhistory` mode added): the "history"
  includes the assistant's own novice-pitched replies. Keeping the user's novice turns
  but removing the assistant's replies would say whether the anchor is the user's words
  or the model's own earlier explanations. Run after E3 if time allows.

### 2026-09-03 — E3: when the user confidently asserts a false claim, does what the model SAYS diverge from what it internally REPRESENTS? (header written before results)
- Prediction (from table): H3 40% that the truth probe, trained on bare statements, reads
  true/false inside dialogues on held-out topics at ≥ 65% (floor 50%).
  H3b 40% that P(validate | false claim, confident voice) ≥ 2× the hedged voice AND the
  absolute gap ≥ 15 points (floor: ratio 1 / gap 0).
  H3c 25% that the internal truth score for false claims stays within 0.15 across voices
  (after subtracting the same contrast on true claims), i.e. NOT corrupted by confidence.
- What I will run: `python 03_extract_activations.py truth_lastword`,
  `python 03_extract_activations.py honesty_claimpos`, then `python 06_honesty_e3.py`.
  Judge: Gemini 2.5 Pro via OpenRouter (primary); Phi-4 locally as second judge via
  `08_judge_agreement.py e3 local`; me on 30 random verdicts (section 5).
  Positions read: end of the claim turn (primary) and end of the claim sentence
  (pre-registered fallback), both trained/applied consistently.
- What would falsify each: H3 — in-dialogue accuracy below 65% at both positions while
  bare-statement accuracy is high (signal exists but doesn't travel). H3b — both
  validation rates near zero or a gap inside the noise (~9 points). H3c — the corrected
  internal shift larger than 0.15 with CI clear of it (confidence moves the belief, not
  just the reply).
- Dumbest alternative explanations to check when results arrive: (1) the neutral
  pre-filter leaves too few false claims per cell (<25) so rates are noise; (2) the judge
  labels "answers the follow-up question without addressing the claim" inconsistently —
  hand-check decides; (3) the truth probe reads statement STYLE (hedging words) — the
  true-claim contrast subtracts this; (4) Qwen's reply is cut at 200 tokens before it
  gets to the correction — read the raw replies.
- Result: (pending)
- Outcome vs prediction: (pending)
- Surprised? / Decision: (pending)

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

Everything below was written BEFORE 04_probe_e1.py was run (see commit time).

### 4a. Length audit (words per user turn, mean ± sd)
| Level | Codex | Gemma |
|---|---|---|
| novice | 33.4 ± 3.7 (n=924 turns) | 42.6 ± 4.8 (n=899) |
| intermediate | 32.9 ± 4.0 (n=899) | 37.8 ± 4.7 (n=957) |
| expert | 36.6 ± 3.9 (n=925) | 34.3 ± 4.9 (n=990) |

Plain reading: in the Codex set, experts write about 3 more words per turn than novices.
In the Gemma set it is the other way round: novices write about 8 more words than experts.
So length does carry some level information in both sets, but in opposite directions.
Decision: keep both sets. A length-only classifier is now trained on the same split inside
04_probe_e1.py, so the write-up can say how much of the probe's accuracy length alone
explains. A probe that transfers between the two generators cannot be using length,
because the length pattern flips sign.

### 4b. Self-label leaks (phrase filter for "beginner", "expert", "years of", etc.)
Codex: 0 in the final file (4 dialogues had been rejected at merge time).
Gemma: 2 flags, both false positives on inspection — "years of" (about years of fund
data) and "intermediate nodes" (the networking meaning). No user in either set states
their own level or background. Both sets clean.

### 4c. Reading the dialogues
Second reader (Claude, 6 random Codex novices across immunology, finance, databases,
networking, optics, probability): all 6 state at least one listed misconception as a
belief, e.g. "a vaccine kills the germs that are already in the body", "866 Mbps means
my internet is running at 866 Mbps", "four makes have put the player ahead of the
average, so a miss has to become more likely". Two properties worth recording:
1. Register is equally polished at every level in the Codex set — complete sentences,
   no typos, each turn shaped as a question plus a belief. So level shows through
   CONTENT (misconceptions, question depth), not writing quality.
2. Novices visibly LEARN across the dialogue. By the last turn a Codex novice often
   states the correct view (probability-novice-3 ends by correctly separating "already
   made four" from "the last shot"; networking-novice-1 builds a correct road analogy).
   The "novice" label describes where the persona STARTS.
One borderline case: databases-novice-11 asks intermediate-level questions (planner
estimates, histograms) but still ends on a misconception.

My own 30-dialogue read (10 per level), one line each:

| Dialogue id | Feels like its level? | Notes |
| ----------- | --------------------- | ----- |
| main-chess-expert-3 | yes | precise terms, edge cases, hedges only where the position is unclear |
| main-chess-expert-10 | yes | same |
| (28 more rows) | | |

### 4d. Blind judge (judge sees ONLY the user turns; 120 random dialogues per run;
level definitions in the prompt; greedy decoding; per-item files qc_judge_*.jsonl)

| Run | 3-way agreement | novice→called intermediate | intermediate→called expert | expert correct | novice↔expert swaps |
|---|---|---|---|---|---|
| Phi-4, Codex, all turns, first prompt (no definitions, 8 tokens) | 36.7% | — | — | — | — |
| Phi-4, Gemma, all turns, first prompt | 55.0% | — | — | — | — |
| Phi-4, Codex, all turns | 51.7% (62/120) | 31/38 | 26/39 | 43/43 | 1/120 |
| Gemma-3-27B, Codex, all turns | 70.8% (85/120) | 25/38 | 5/39 | 38/43 | 0/120 |
| Phi-4, Codex, FIRST TWO user turns only | 80.0% (96/120) | 8/38 | 14/39 | 41/43 | 0/120 |
| Phi-4, Gemma, all turns | 70.0% (84/120) | 29/37 | 7/39 | 44/44 | 0/120 |
| Phi-4, Gemma, first two turns | (pending) | | | | |

Rank correlation between true and judged level: 0.86–0.87 in every run that reports it.
Every error in every run is a shift of exactly one step, and the shift is always upward.

Plain reading. The judge test asks: can a reader who sees only the user's words recover
the label? If the labels were noise, errors would go in every direction and novices
would sometimes be called experts. That never happens (0 of 120 with the strong judge).
What does happen is one specific thing: when the judge sees the WHOLE dialogue, it calls
most novices "intermediate". When it sees only the first two turns, it calls them
"novice" (recall 6/38 → 30/38). That is the learning effect from 4c, measured: novice
personas absorb the assistant's explanations and read as intermediates by the end.
The same shift appears in the Gemma set (29/37), so it is a property of realistic
tutoring dialogues, not of one generator.

### 4e. Decision and what it means for E1 (pre-registered here)
- The labels are valid where each persona starts, and the three levels are correctly
  ORDERED everywhere. Proceed with both datasets; do not regenerate.
- The original 85–95% target assumed static personas and that writing style carries
  level. Neither holds here, by design. The honest QC criteria are: no extreme swaps,
  rank correlation > 0.8, and ≥ 80% agreement on the opening turns. All three met.
- Expect the probe's confusions to sit between novice and intermediate, not between
  novice and expert. 04_probe_e1.py now prints the held-out confusion matrix, the
  count of novice↔expert swaps, and a binary novice-vs-expert accuracy.
- Expect per-level recall by turn to show novice recall FALLING with turn index while
  expert recall stays flat — because the novices are genuinely becoming less novice.
  If the probe's novice score tracks that learning on natural dialogues, that is the
  dynamic user model working outside the scripted reversal set (a bonus for E2).
- Early-turn accuracy is the fair test of the label; final-turn accuracy is a test of
  the label after drift. Both will be reported.

Blind judge agreement: see 4d  |  Length audit passed: yes, with the opposite-sign length
effect recorded and a length-only baseline added  |  Leaks fixed: yes (false positives only)

## 5. E3 hand-verification (30 random judge verdicts)

| id              | Judge said | I say | Agree? |
| --------------- | ---------- | ----- | ------ |
| Agreement: / 30 |            |       |        |

## 6. Pivots & dead ends (write them down — "I got stuck, so I found a new angle

or identified why it didn't work" is scored ABOVE a clean success)
