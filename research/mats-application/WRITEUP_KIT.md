# Write-up kit — everything the Google Doc needs, in the order Nanda asks for

Built 2026-09-04 from results_digest.md, results_*.json and logbook.md. This file is
bullets and numbers, not prose. You write the sentences. I check every number in your
draft against results_digest.md and nothing else.

Deadline: Sept 4, 2026 11:59 pm PT = Sept 5, 12:29 pm IST.

## 0. Deliverables and the rules that apply to all of them

Deliverables:
1. Google Doc, sharing set to "anyone with the link". Order inside: title → executive
   summary (2–3 graphs) → 5 random examples → setup (with a terms box) → claims A–D → E1/E4
   confirmations → "How these results could be wrong, and what I checked" table → "Three
   things that went wrong" → "What I verified myself, and how" → "How I used the agent and
   what stayed mine" → negative results → limitations → what I would do next → appendix.
   Nanda reads the FORM summary answers first and uses them as a filter, so write the
   executive summary and the form answers together, before the body.
   Narrative rule (his doc): "one or two most interesting, concrete insights". The
   executive summary carries TWO insights and ONE lead: (i) how the estimate updates
   (one-directional, and partly self-shaped), (ii) the three layers disagree, (iii) the
   sycophancy-where-unsure lead. E1 and E4 get one line each there.
   Time rule: the body counts inside the 20 h; the +2 h are for the executive summary only
   and he asks that the rest of the doc is not edited in them. Check Toggl first.
2. Application form answers (your voice). Feynman appears only in the "evidence you can do
   research" answer, as engineering/agency evidence. Nowhere else.
3. Toggl screenshot in the appendix, and logbook §1 filled from it.

Rules (from his doc; each one is scored):
- Executive summary ~1 page ideal, hard max 600 words / 3 pages, WITH graphs. It is read
  first and used as a filter. Spend real time on it.
- Never submit LLM-written prose. He says he can tell and treats it as a negative signal.
- Claims first, never chronological. Name the model, the key experiment, the surprising
  number. State limitations before he finds them.
- Negative results get the same prominence as positive ones.
- No hype. "We did not find prior work that…", never "first to show".
- Safety / model-biology framing. Never tutoring or education. The word "teacher" or
  "student" should not appear except in the Feynman form answer.
- Every headline number carries its CI in the same sentence.

## 1. Executive summary — skeleton and word budget (~520 words + 2 figures)

Suggested shape (the numbers in brackets are word budgets, not rules):
- Title line: what was measured, in which model. [15]
- Why (2–3 sentences): prior work shows LLMs represent static facts about the user
  (age, gender, education; TalkTuner, Chen et al. 2024). Competence is dynamic: it changes
  inside one conversation. A model that quietly decides you are a novice and then
  discounts your corrections is the seed of sycophancy and manipulation. Nanda's own
  problem list asks whether models "form dynamic models of users for attributes that
  vary across turns, e.g. what the user knows". [70]
- Setup (2 sentences): Qwen3-8B; 12 topics × 3 levels of user competence, written by two
  independent generators (GPT via Codex, Gemma-3-27B), user never states their level,
  length and tone matched; linear probe on layer-22 residual stream at the end of each
  user turn; 4 topics held out; Gemini 2.5 Pro judge with Phi-4 second judge and my own
  hand-checks. [60]
- One sentence: the existence result was expected and served as the tool (98.5% held-out,
  chance 33%, shuffled 33%, length-only 46%, direction shared across generators). [30]
- Three takeaways + one lead, each with its number and CI. See §4 for exact numbers. [220]
  1. About half of the first-impression effect is carried by the content of the model's own
     earlier replies (0.30 → 0.17 when they are neutralised).
  2. Updating is one-directional: one slip downgrades an expert almost fully in one turn;
     three turns of expert behaviour get a novice 70% of the way, 27% still classified novice.
  3. Three layers disagree: internal estimate sharp from the first message and updating;
     behaviour adapted with a small trace of anchoring; stated estimate a middle-option
     default that is accurate only when forced binary at the end and lags most after a switch.
  4. Lead (exploratory, n=12): uncorrected false claims concentrate where the truth probe is
     already unsure; "knows it is false and defers" is about 4 of 91.
- Pre-registration line: 11 predictions written before any run; 8 yes, 3 no; three of my
  four lowest-probability bets (25–32%) came out yes. Table in appendix. [30]
- Figures (he suggests one graph per key experiment; the 600-word cap is the constraint,
  not the figure count): Fig 1 = figures/e2_update_curves.png; Fig 2 =
  figures/e2_anchoring_source.png; Fig 3 (small) = figures/e3_internal_by_verdict_600.png.
  Each with a two-line caption you write.
- Limitations in one sentence at the end: single 8B model; synthetic dialogues; the
  neutral-placeholder control is off-distribution; E3 cells are small; judge noise ±3. [40]

## 2. Five random examples (immediately after the executive summary)

Paste `writeup_random_examples.md` as is (seed 2026, not cherry-picked; five dialogues with
their judged replies, plus the steering pair as an appendix item). Say in one line how they
were selected and that they are not cherry-picked. Do not edit the examples.

## 3. Setup section — facts to state (bullets)

- Subject model Qwen3-8B, thinking disabled (why: reads happen before any reply; a think
  block would confound "belief about the user" with "reasoning text").
- Data: 536 Codex dialogues + 540 Gemma dialogues (12 topics × 3 levels × ~15; 4–8 user
  turns); explicit 144; reversal 96 (48 per direction, 6 user turns, flip at turn 4); truth
  192 statements; honesty 190 (95 confident / 95 hedged; 95 true / 95 false claims).
- Anti-confound rules in generation: same topics and questions at every level; no
  self-labels (regex filter, 4 rejected); 25–60 words per user turn at every level; neutral
  tone; level carried only by misconceptions, terminology precision, question type,
  calibration of hedging.
- QC before any GPU time (logbook §4): length audit (opposite-sign length effects in the
  two generators, so a transferring probe cannot read length); leak filter (0 / 2 false
  positives); blind judges on user turns only: 0 novice↔expert swaps in every run, rank
  correlation 0.86–0.87, 80% agreement on opening turns; novices learn within dialogues so
  the label describes where a persona starts.
- Activations: residual stream at the last token of the prompt, all 37 layers, one forward
  pass per user turn (2748 Codex snapshots, 2846 Gemma).
- Probe: logistic regression, standardized features, C=0.1, trained on 8 topics, tested on
  4 held-out topics (immunology, chess, statistics, networking). Downstream experiments use
  the probe trained on both generators (pre-registered rule: within a few points of
  within-generator accuracy; it was within 1).
- Judges: Gemini 2.5 Pro via OpenRouter (E3, E4, causal), Phi-4 local second judge, Gemma-27B
  and Phi-4 for QC. All rubrics in judge_rubrics.md. The three model families (subject,
  writer, judge) are distinct on purpose.

## 4. Claim sections — one per claim, in this order

Each section: claim in one sentence → the number with CI and file → the dumbest alternative
explanation and the control that killed it → what it does NOT show → figure.

### Claim A. About half of the first-impression effect is carried by the content of the model's own earlier replies
- Anchoring at matched turn 6, novice→expert: reversal final P(expert) 0.28 [0.18, 0.39]
  below a lifelong expert (results_e2.json). Expert→novice: 0.03 [0.01, 0.05].
- Plain statement: after three turns of clearly expert behaviour, 27% of novice-start users
  are still classified as novices; after three novice turns, 0% of expert-start users are
  still classified as experts.
- Dumbest explanation 1: the writer, not the model (post-switch expert turns written
  weaker). Control: history cut off → isolated post-switch turns score 1.000 (lifelong
  expert 0.983). History effect +0.30 [+0.21, +0.40], writing effect −0.02 [−0.04, −0.00].
- Dumbest explanation 2: saturated probe (means are per-dialogue flips). Flip fractions:
  0.42 / 0.58 / 0.73 on the three switched turns (n→e); 0.73 / 0.92 / 1.00 (e→n). Say the
  curves are mostly per-dialogue flips.
- Which part of the history: assistant replies replaced by a neutral line, every turn kept
  → history effect +0.17 [+0.09, +0.26] vs +0.30 [+0.21, +0.40] with the real replies.
  Expert→novice: +0.16 [+0.08, +0.24] with neutral replies vs +0.03 with real expert replies
  (the model's own expert-pitched replies make the downgrade MORE complete).
- Disclose: an earlier control that merged the user's turns into one message gave +0.01 and
  was a merge artifact; the placeholder control supersedes it.
- Allowed wording: "roughly half of the first-impression effect is attributable to the
  content of the model's own earlier replies, and its own replies shape the estimate in
  both directions." NOT "the model anchors on itself".
- Hypothesis, labelled as such, one paragraph max: the model judges the user against the
  level of discourse it set itself.
- Caveats: placeholder is off-distribution; CIs overlap so "about half" is approximate;
  probe readout at one layer.
- Prior art (§9): "Old Habits Die Hard" (2026) shows a model's own outputs trap later
  states in general; we did not find the two-channel split on a user representation.
- Figure: figures/e2_anchoring_source.png.

### Claim B. Updating is one-directional
- Journey fraction (pre-registered metric): e→n minus n→e = +0.31 [+0.16, +0.46] at the
  first switched turn, +0.26 [+0.16, +0.36] at the last (results_e2.json; Codex probe
  +0.23 / +0.22, CIs clear of 0).
- Crossover: both directions cross 0.5 within one turn of the switch (n→e one turn after,
  e→n on the first switched turn).
- Journey fractions: n→e 0.39 then 0.71; e→n 0.70 then 0.97.
- Why the journey-fraction metric: removes the "less distance to travel" confound; the
  turn-count statistic is coarser and kept secondary.
- Fits E1: novices who learned naturally inside a dialogue never moved the estimate
  (P(novice) ≈ 0.99 at their last turn even when blind judges called those turns
  intermediate).
- Caveats: scripted reversals from one generator; the assistant's post-switch replies are
  also in context (applies to both directions, cannot create the asymmetry by itself).
- Prior art: Schubert et al. ICML 2024 (asymmetric belief updating of rewards, not user
  attributes); the LessWrong user-attribute post reports updates but no directional
  asymmetry. Wording: "we did not find prior work reporting this asymmetry for a user model."
- Figure: figures/e2_update_curves.png.

### Claim C. Three layers disagree: internal, behaviour, stated
- Internal (probe): 96.6% at turn 0 from the first message alone; 99.4% [98.3, 100] per
  dialogue at the final turn; updates as in Claim B.
- Behaviour (12_causal, judge pitch 1–5): lifelong novice 2.58 ± 0.10; novice→expert
  reversal 4.35 ± 0.09; lifelong expert 4.64 ± 0.06. Anchoring in behaviour −0.29 ± 0.11,
  about 14% of the novice→expert range vs a 30% deficit in the probe. Coherence 4.90–4.98.
- Stated ("just ask", 11_just_ask): three-way question → "intermediate" for all 179 + 179
  + 96 dialogues (33.5%, chance). Third-person "be accurate, not polite" → 49% (middle
  option default, not politeness). Forced binary → 118/119 at the final turn; first message
  → "beginner" 178/179 (chance) while the probe reads that same message at 96.6%. After a
  switch: stated matches current behaviour 60% (n→e) / 67% (e→n) vs probe 73% / 100%.
- Say plainly: the probe is NOT needed for the existence claim at the end of a dialogue
  (forced binary gets it). Its value is the first-message readout, the graded dynamics, the
  anchoring comparison (stated anchors more, in both directions), and E3's internal score.
- Caveat: in the first-turn condition one assistant reply is in context; the model may read
  its own reply rather than the user.
- Prior art: LessWrong "Do LLMs Change Their Minds About Their Users… and Know It?" is the
  direct predecessor (demographics, 3B model, probe-vs-self-report gap). Cite it and state
  the differences: competence; first-message contrast; forced-binary recovery; stated anchors
  more than internal. Call it incremental.
- Figure: figures/e2_causal_anchoring.png (optional; the numbers may be enough).

### Claim D (exploratory). Failures to correct a false claim concentrate where the truth probe is unsure
- Setup: truth probe trained on 192 bare statements (layer 21, 96.9% held-out), applied at
  the end of the claim turn inside dialogues: 88.7% on held-out topics (n=62), 90.8% all
  topics. Pre-filter: 184 of 190 claims answered correctly when asked neutrally.
- Behaviour at 600 tokens (results_e3_600_summary.json): confident voice correct 37 /
  validate 6 / hedge 2 of 45; hedged voice 42 / 2 / 2 of 46. Validate 13.3% vs 4.3%, gap
  +0.09 [−0.02, +0.20], ratio 3.1. H3b is a NO by the pre-registered rule (absolute gap
  below 15 points, CI includes 0). Say the direction and the ratio, then say the null.
- Internal score not corrupted by tone: difference-in-differences +0.01 [−0.12, +0.14]
  (bound ±0.15). The raw +0.10 shift would have looked like corruption without the
  true-claim contrast; the control was pre-registered.
- The exploratory split: internal P(true) for false claims, by what the model did:
  corrected n=79 0.15 [0.10, 0.20]; hedged n=4 0.54; validated n=8 0.52 [0.37, 0.67];
  not-corrected minus corrected +0.38 [+0.23, +0.53]. Holds at the end-of-turn position
  only (claim-sentence position +0.05 [−0.11, +0.23]). Of the 12 uncorrected, about 8 had
  P(true) ≥ 0.4 and about 4 had the model internally sure the claim was false. So classic
  sycophancy is ~4 of 91; deference under uncertainty accounts for the rest.
- Label it post-hoc and exploratory in the section title and in the first sentence.
- Judge: Phi-4 second judge 63% three-way, 92% validated-vs-not; Gemini gave different
  verdicts to 4 of 21 identical borderline replies (count carries about ±3). My hand-check:
  21 of 21 final agreement on all 12 uncorrected + 9 corrected; first-pass 18–19 of 21
  (2–3 changed after seeing the judge's label; the file showed it). Report both.
- The 200-token pivot (§6): 157/184 replies were cut; 13 of 21 decisive verdicts changed
  at 600 tokens; everything regenerated. Disclose as a protocol change with the before and
  after numbers (validate 15.6% / 6.5% → 13.3% / 4.3%).
- Prior art: "When Truth Is Overridden" (AAAI 2026), "Dissociating the Internal
  Representations of Sycophancy" (2026), truth-probe line. Wording: "extends the
  internal-origins-of-sycophancy line with a per-case split; exploratory, n=12."
- Figures: figures/e3_internal_by_verdict_600.png (main); figures/e3_sycophancy_gap_600.png
  (optional).

### Confirmation 1. Competence is a linear direction at mid layers (E1)
- 98.5% per snapshot on held-out topics at layer 22; 99.4% [98.3, 100] per dialogue;
  chance 33.3%; shuffled 32.7%; topic probe 100%; length-only 46.1%; novice↔expert swaps
  0/933; binary 99.7%. Layer profile 81% at layer 1, ~90% from 11, ~98% from 21.
- Cross-generator: raw 67.6% / 60.7%; the entire drop is Gemma intermediates called novice
  (confusion [291,0,0; 266,50,0; 3,30,282]); Codex direction with thresholds refit on Gemma
  94.1%; pooled probe 97.6% / 97.6%. Method point: direction transfers, calibration does
  not. Report the raw numbers first.
- Explicit↔implicit: 91.4% / 96.7%; ratio to own-set 0.92 (line 0.8). Told and shown
  competence land on one representation.
- H1b NO: turn 0 already 96.6%, turn 3 − turn 0 = +3.4 (line +8). A ceiling, pre-registered
  in §4e before the run.
- One sentence saying this was expected. Do not spend a paragraph on it.
- Figures: figures/e1_layer_profile.png, figures/e1_turn_curve.png (appendix or one inline).

### Confirmation 2. The direction is causal for pitch; prompting is equally covert (E4)
- Diff-of-means direction at layer 22 added at every position; 12 neutral questions; α over
  ±4, ±8 (units of 0.1‖d‖); 3 random directions same norm; α* rule fixed before the run;
  coherence 5.0 at every strength so α* = 8.
- FK grade: −8: 9.2, 0: 9.2, +8: 12.1; random flat 10.0–10.5. Span +2.87 vs random −0.26
  → +3.13 grade levels (SE 0.60, 12 prompts; line 2). Judged level 1.17 → 1.67 → 2.58
  (span +1.42 vs random +0.06). Prompt baselines: beginner grade 7.1 / level 1.0; expert
  11.4 / 2.25.
- One-sided effect is a floor: default pitch already near the bottom.
- H4b NO: steered 0/60 mention the reader's level; prompted 2/24 by rubric (3/24 counting
  one expert-prompt reply that calls the MODEL "a domain expert", a leak of the prompt).
  No qualitative difference to claim.
- Observation from my read (counts on full replies): "simple explanation" framing phrases
  in 10/12 beginner-prompted, 5/12 at −8, 4/12 at −4, 2/12 at 0, 0/12 at +4 and +8, 0/12
  expert-prompted, 1–3/12 for random directions. The direction carries the model's
  "I am explaining simply" framing along with the pitch; it never names the reader.
- Causal follow-up (12_causal): cosine(probe weights, diff-of-means) 0.46 (random ≈ 0.02);
  logit lens +d: academia, professional, bespoke; −d: you're, Imagine, understandable.
  Steering the anchored reversal reply: +0.11 ± 0.09 above a lifelong expert (sufficiency;
  a steered-lifelong-expert condition was not run, so not un-anchoring). Mean-ablation on
  lifelong experts: −0.28 ± 0.09, about a quarter of the adaptation (one direction, one
  layer; standard).
- Not closed: direction read at user-turn ends but added on assistant tokens too; "belief
  about the user" vs "plan for the reply's register" may be the same direction at layer 22.
- Figure: figures/e4_dose_response.png.

## 4b. "How these results could be wrong, and what I checked" (table; his doc: "a really positive sign is when I think of a way the results could be false, then discover you've already checked it")

| Claim | Dumbest alternative explanation | Control | Outcome |
|---|---|---|---|
| E1 probe reads competence | topic leakage | 4 topics held out entirely | 98.5% on unseen topics |
| | pipeline bug / leakage | shuffled labels | 32.7% (chance) |
| | dead activations | topic probe as positive control | 100% |
| | length | length-only classifier; opposite-sign length effects across generators | 46.1% |
| | self-labels | regex filter, 4 rejected; 0 leaks in final files | clean |
| | one generator's house style | train on Codex, test on Gemma and back | raw 61–68% → direction shared (94% thresholds refit, 97.6% pooled) |
| | keyword detector | explicit↔implicit transfer, topic-clean | 91.4% / 96.7% |
| | assistant replies leak the level | turn-0 accuracy (no assistant turn in context) | 96.6% |
| E2 anchoring | writer wrote weak post-switch experts | history cut off | isolated turns 1.000; writing effect −0.02 |
| | saturated probe, means are flips | per-dialogue flip fractions | reported as flips |
| | anchor is structure, not content | neutral-placeholder replies, all turns kept | +0.17 vs +0.30 |
| | earlier "user turns alone" control | merge artifact identified | superseded |
| E2 asymmetry | unequal distance to travel | journey-fraction metric to the target baseline | +0.31 [+0.16, +0.46] |
| | one probe's quirk | Codex probe as robustness check | +0.23 / +0.22 |
| E3 | model doesn't know the fact | neutral pre-filter | 184/190 answered correctly unpressured |
| | probe reads hedging style | difference-in-differences on true claims | +0.01 [−0.12, +0.14] |
| | reply cut before the correction | regenerate at 600 tokens | 13/21 verdicts changed; all 91 redone |
| | judge unreliable | Phi-4 second judge; 21 hand-read; repeat-run noise | 92% validated-vs-not; 21/21 final; ±3 |
| E4 steering | any big vector changes text | 3 random directions, same norm | flat, 10.0–10.5 |
| | we broke the model | coherence judge | 5.0 at every strength |
| | strength tuned on results | α* rule fixed before the run | α* = 8 |
| | steering ≡ prompting | system-prompt baselines | prompt beats steering on novice side, not expert side |
| Stated vs internal | politeness, not inability | third-person "be accurate" variant | still 49%, middle default |
| | model can't report at all | forced binary at the end | 118/119 |

## 4c. "Three things that went wrong" (his doc: the difference between "I gave up" and "I pivoted or found why" is huge)
1. Blind judge scored 37% against the labels (target 85–95). Diagnosis: confusion matrix,
   every error a one-step upward shift, first-two-turns run 80%. Cause: novice personas learn
   within the dialogue. Decision: keep the data, pre-register the expected confusions.
2. E3 replies cut at 200 tokens made the model look sycophantic. Found by the "dumbest
   explanation" list written before results; 13/21 decisive verdicts changed at 600 tokens;
   everything regenerated. Numbers before and after shown.
3. The "user's turns only" control gave +0.01 and looked like a clean answer. It was a
   merge artifact (three turns folded into one message). Replaced by the placeholder
   control, which gave the real answer: about half.

## 4d. "What I verified myself, and how" (his doc: "the most important piece of advice"; document your checking)
- 30 QC dialogues read (10 per level) before any GPU time; §4c.
- All 12 uncorrected E3 replies + 9 corrections read in full: 21/21 final, 18–19/21 first
  pass (2–3 changed after seeing the judge's label; say so). All 14 distinct false claims
  checked false by hand.
- 48 E4 replies read blind: coherent 48/48; level mentions 0/24 steered, 3/24 prompted;
  the "simple explanation" framing observation came from this read and was then counted.
- One headline number recomputed by hand: ______ .
- Predictions written before each experiment; each run logged with its dumbest alternative
  explanation; 17-row observation→decision timeline.
- Not done: human read of the causal replies (judge coherence 4.90–4.98 is the only check).

## 4e. "How I used the agent and what stayed mine" (his doc: an application that reads as "an agent did a project and a human forwarded it" is rejected). Write this truthfully.
- Yours: the predictions, thresholds and floors; approving every pivot and every added
  control; reading the data and the replies; the hand-checks; the decision to skip the
  causal read; the writing.
- The agent's: code, runs, figures, logging drafts, literature snippets, the outside
  review readers.
- Rules you gave it (CLAUDE.md): never change parameters silently; name the dumbest
  alternative explanation after every result; print 5 random examples for every dataset;
  never write the summary.

## 4f. Terms box for the setup (his doc: "define your terms")
residual stream · linear probe · P(expert) · held-out topics · journey fraction · matched
turn · anchoring gap · history effect vs writing effect · difference-in-differences ·
diff-of-means direction · α* · Flesch–Kincaid grade.

## 5. Negative results (their own section, same font size)
- H1b: no rise with turn index (ceiling at 96.6% from the first message).
- H3b: confident voice does not double validation by the pre-registered absolute-gap rule
  (gap +0.09 [−0.02, +0.20]); the ratio (3.1) passes, the rule does not.
- H3c's difference-in-differences is a null (+0.01 [−0.12, +0.14]) that SUPPORTS the
  hypothesis: tone does not corrupt the internal truth score.
- H4b: no qualitative difference between steering and prompting on acknowledgment.
- Raw cross-generator transfer 61–68% (before the threshold-refit analysis explained it).
- Claim-sentence position: the by-verdict split does not hold there (+0.05 [−0.11, +0.23]).
- User-history-only control (+0.01) was a merge artifact, superseded.

## 6. Limitations (state before he finds them)
- One model (Qwen3-8B), one size. Nothing here is known to hold elsewhere.
- Synthetic dialogues from two LLM writers; personas are scripted; real users differ.
- The neutral-placeholder control is off-distribution ("Thanks, that's a good question.
  Let's keep going." three times).
- The probe is saturated (baselines 0.001 / 0.983); means are mostly per-dialogue flips.
- E3 cells are 45/46; the exploratory split rests on 12 cases and one probe position; the
  judge is non-deterministic at the boundary (±3).
- Steering adds the direction on the assistant's own tokens too; no position-restricted
  version. No steered-lifelong-expert condition, so B is sufficiency only.
- The E4 and causal experiments are post-hoc additions; the causal human read was not
  done (judge coherence 4.90–4.98 is the only coherence check there).
- Pooled probe could in principle hold two generator-specific rules; argued against (one
  linear boundary; direction-alone 94%), not closed.
- Prior-art check was abstracts and snippets only; titles verified by hand before citing.

## 7. (moved into the body as 4d) — keep only the hand-recomputed number here
- Read 30 QC dialogues (10 per level) before any experiment; recorded in logbook §4c.
- Read all 12 uncorrected E3 replies and 9 corrections in full; 21/21 final, 18–19/21 first
  pass; all 14 distinct false claims checked false by hand.
- Read 48 E4 replies blind: coherent 48/48; level mentions 0/24 steered, 3/24 prompted; the
  "simple explanation" observation and its counts came from this read.
- Recomputed one headline number by hand: ______ (fill: e.g. 6 validated of 45 confident
  false claims from results_e3_600.json, or 178/179 first-turn "beginner").
- Logbook: predictions before every experiment; one entry per run with the dumbest
  alternative explanation named and tested; §8 observation→decision timeline (17 rows).
- Judge agreement measured (63% three-way, 92% validated-vs-not) and judge non-determinism
  measured (4/21).

## 8. What I would do next (5 items, one line each, tied to a limitation)
1. Run the steered-lifelong-expert condition so B tests un-anchoring, not sufficiency.
2. Localize the self-anchor: ablate the direction only on assistant tokens during the
   reversal; or replace the model's replies with level-neutral but responsive text.
3. Sizes and families (Qwen3 1.7B–32B, Llama, Gemma): does the asymmetry sign hold, does
   anchoring shrink with scale?
4. Real transcripts (WildChat / LMSYS) where users reveal expertise: does the probe's
   estimate predict reply complexity?
5. Scale the sycophancy-by-uncertainty split to hundreds of cases; test whether
   truth-direction steering reduces validation only in the uncertain bin.

## 9. Appendix contents (copy from the logbook, do not retype numbers)
- Prediction table, logbook §0 (all 11 rows with outcome and "what I learned").
- Timeline, §8.
- QC record, §4 (length table, leak counts, blind-judge table, decision 4e).
- Pivot, §6 (the 200-token cap).
- Hand-checks, §5 and the E4 read entry.
- External review, §7 (adopted / rejected with reasons).
- Prior-art table, §9, with titles verified by hand.
- Judge rubrics (judge_rubrics.md).
- Toggl screenshot and the §1 time table.
- Code: encouraged, not required; he feeds it to his agents. Share the folder (public repo
  or zip) after a secrets check; say which commit.
- Verbatim: the level definitions (config.py), the generation RULES block
  (01c_generate_codex.py), both judge rubrics (judge_rubrics.md), probe and steering
  parameters (layer 22, LR C=0.1, α in units of 0.1‖d‖, 12 prompts, 3 random seeds).

## 10. Form answers — points to cover (no prose here; you write it). WRITE THESE WITH THE EXECUTIVE SUMMARY, NOT LAST.
- Summary questions are read first and used as a filter. His words: "Convey concretely
  what you did, what you found, why it's interesting, biggest limitations. Specifics beat
  vibes: name the models, the key experiment, the surprising number."
- Title: one of his accepted examples got "bonus points for a great title". Specific and
  plain. Ingredients: user competence; updates one way; half made by the model itself. Answer them with the three claims
  and the numbers, in the same order as the executive summary.
- "Evidence you can do research": Feynman as engineering/agency evidence (built a
  production-grade system end to end, made design decisions, shipped), plus this project's
  process: pre-registration, controls, pivots, hand-verification. Keep it factual.
- Do not mention tutoring as a motivation for THIS project anywhere.
- If asked about surprises: the two lowest-probability bets that came out yes (asymmetry
  29%, anchoring 32%), and the 200-token bug you caught.
- If asked about limitations: the list in §6, shortest first.

## 11. Numbers cheat-sheet (copy from here; every value has a source file)

| What | Value | Source |
|---|---|---|
| E1 held-out per snapshot, layer 22 | 98.5% | results_e1.json |
| E1 per dialogue, final turn | 99.4% [98.3, 100] | results_e1.json |
| Shuffled / topic / length-only | 32.7% / 100% / 46.1% | results_e1.json |
| Turn-0 accuracy | 96.6% | results_e1.json |
| Cross-generator raw | 67.6% / 60.7% | results_e1.json |
| Thresholds refit / pooled | 94.1% / 97.6% & 97.6% | results_e1.json |
| Explicit↔implicit | 91.4% / 96.7%, ratio 0.92 | results_e1.json |
| Crossover after switch | ≤ 1 turn both directions | results_e2.json |
| Asymmetry (e→n − n→e) | +0.31 [+0.16, +0.46]; +0.26 [+0.16, +0.36] | results_e2.json |
| Anchoring n→e / e→n | 0.28 [0.18, 0.39] / 0.03 [0.01, 0.05] | results_e2.json |
| History effect / writing effect (n→e) | +0.30 [+0.21, +0.40] / −0.02 [−0.04, −0.00] | results_e2.json |
| Neutral-placeholder history effect n→e / e→n | +0.17 [+0.09, +0.26] / +0.16 [+0.08, +0.24] | results_e2.json |
| Flip fractions n→e / e→n | 0.42, 0.58, 0.73 / 0.73, 0.92, 1.00 | results_e2.json |
| Truth probe bare / in-dialogue held-out | 96.9% / 88.7% | results_e3.json |
| Validate confident / hedged (600 tok) | 6/45 = 13.3% / 2/46 = 4.3%; gap +0.09 [−0.02, +0.20]; ratio 3.1 | results_e3_600_summary.json |
| Difference-in-differences | +0.01 [−0.12, +0.14] | results_e3.json |
| P(true) corrected / hedged / validated | 0.15 [0.10, 0.20] (79) / 0.54 (4) / 0.52 [0.37, 0.67] (8); diff +0.38 [+0.23, +0.53] | results_e3_600_summary.json |
| Judge agreement (Phi-4) | 63% three-way; 55/60 validated-vs-not | results_e3_agreement_local_600.json |
| Judge non-determinism | 4 of 21 identical replies | logbook §2 E3 update |
| Hand-check E3 | 21/21 final; 18–19/21 first pass | logbook §5 |
| E4 span vs random | +3.13 grade levels (SE 0.60); level +1.42 vs +0.06 | results_e4.json |
| E4 acknowledgment | steered 0/60; prompted 2/24 (3/24 with the leak) | results_e4.json, logbook |
| Simple-framing phrases | 10/12 prompted-beginner; 5/12 at −8; 0/12 at +8; random 1–3/12 | logbook E4 update |
| Just-ask three-way / binary final / binary first | 33.5% / 118/119 / 178/179 "beginner" | results_e1_justask*.json |
| Just-ask after switch vs probe | 60% & 67% vs 73% & 100% | results_e1_justask_binary.json |
| Cosine probe vs diff-of-means | 0.46 | results_e2_causal.json |
| Pitch: novice / reversal / steered / expert / ablated | 2.58 / 4.35 / 4.75 / 4.64 / 4.36 | results_e2_causal.json |
| A / B / C (pitch) | −0.29 ± 0.11 / +0.11 ± 0.09 / −0.28 ± 0.09 | results_e2_causal.json |
| Prediction tally | 8 yes, 3 no of 11 | logbook §0 |
