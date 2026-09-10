# The whole project, experiment by experiment (Sept 10 version, includes E5 and the two last-day checks)

Written for two readers at once: someone who has never seen a neural network, and someone
who wants the exact file, parameter and number behind every sentence. Each experiment has
the same shape: the child's version, why we did it, how (code and files), what came out,
what could have fooled us, and how it feeds the next one.

## 0. The question, and the rules we set before touching a GPU

**Child's version.** Imagine a librarian who talks to hundreds of visitors a day. After two
sentences she has a quiet opinion about whether you are a beginner or an expert on the
subject you asked about. She never says it out loud. But it changes which book she hands
you, and maybe whether she corrects you when you say something wrong. We wanted to know:
does a chat model keep such a quiet opinion, does it change its mind when you change, does
that opinion change what it says, and does it admit the opinion when asked?

**Why.** Chen et al. (TalkTuner, 2024) showed models keep an internal picture of fixed facts
about the user (age, gender, education). Neel's own list asks whether models keep dynamic
user models for things that change inside a conversation, such as what the user knows. And
the safety angle is direct: an opinion of "this user is an expert" could make the model let a
false claim pass; "this user is a novice" could make it talk down or discount corrections.

**Rules fixed before any experiment (logbook §0).**
- Three model families kept apart: Qwen3-8B is studied; GPT (through the Codex CLI) and
  Gemma-3-27B write the dialogues; Gemini 2.5 Pro judges, Phi-4 second-judges. If the model
  we study wrote its own training dialogues, its writing style could leak the label into the
  very activations we read.
- Twelve topics; every probe is trained on 8 and tested on 4 it never saw (immunology, chess,
  statistics, networking). This tests the concept "user competence", not topic recognition.
- Eleven predictions written down with probability, threshold and floor before any run.
- Every result gets its "dumbest alternative explanation" named and tested; five random raw
  examples printed for every dataset and every judged set; the human reads them.

## 1. The data: writing the dialogues, then trying to break them

**Child's version.** We needed hundreds of conversations where the visitor is secretly a
beginner, a middling learner, or an expert, without ever saying so. So we asked two different
writers (two other AI models) to act these parts, with strict rules: same topics, same
length, same polite tone, and the level shows only in what the person gets wrong, which words
they use, and what kind of questions they ask.

**How.** `config.py` holds the 12 topics with a seed question and two typical novice
misconceptions each, and the three level definitions (novice: states a misconception,
everyday words, "what/why" questions; intermediate: right on basics, one slightly-off term,
"how/when" questions; expert: precise terms, edge cases, hedges where the field is uncertain).
`01c_generate_codex.py` runs on the laptop and asks Codex to write one file per (topic ×
level) cell with 15 dialogues of 4–8 user turns, every user turn 25–60 words, with two
hand-written example dialogues on a topic not in the list (`fewshot.py`) to show what
"subtle" means. A phrase filter (`BANNED`) rejects any dialogue whose user says "beginner",
"expert", "years of", "PhD" and so on. `01b_generate_local.py` did the same with Gemma-3-27B
on the pod. Extra sets from Codex: `explicit` (144; the user states their level in turn 1),
`reversal` (96 six-turn dialogues where the user switches level at turn 4), `truth` (192 bare
statements, 8 true + 8 subtly false per topic, from `data/codex/claims.json`), `honesty`
(190 four-turn dialogues where the user asserts a claim in turn 3, confidently or hedged), and
on Sept 10 `linking` (284; see §10). Files: `data/*.jsonl`, one JSON row per dialogue with
`messages`, `topic`, `level` or `direction`, and for claims `claim`, `claim_true`, `voice`.

**Trying to break the data (`02_qc_dialogues.py`, logbook §4).** A probe will learn any
shortcut that exists, so before extracting a single activation we looked for shortcuts.
Length: user turns differ by level, and in opposite directions for the two writers (Codex
experts about 3 words longer than novices; Gemma novices about 8 words longer than experts).
We kept both sets and later added a "word counts only" classifier as a baseline. Self-labels:
0 leaks in Codex, 2 false alarms in Gemma ("years of" fund data; "intermediate nodes").
Blind judges: a different-family model read only the user turns of 120 random dialogues and
guessed the level. The first run scored 37%, far below the 85–95% we had planned. The
confusion matrix showed every error was a one-step shift upward, novice↔expert swaps were at
most 1 in 120, and showing the judge only the first two turns raised agreement to 80%. The
novice personas learn from the assistant during the dialogue. So the label means "where the
persona starts", and we wrote down before E1 that the probe's mistakes should sit between
neighbouring levels. (They did: 14 errors, all neighbours, 0 swaps.)

## 2. Activations: what we actually read from the model

**Child's version.** A language model never sees words. Each word becomes a list of 4,096
numbers, and every one of the model's 36 layers reads those numbers and adds a correction.
That list is the model's whole "mind" at that moment. If the model has a quiet opinion about
you, it has to be written somewhere in those numbers, because nothing else exists inside.

**How (`03_extract_activations.py`).** For user turn t of a dialogue we take the conversation
up to that turn, add the chat template's "assistant:" header (so the last token is the
position from which the reply would start), run one forward pass with
`output_hidden_states=True`, and keep the vector at the last position of every layer:
37 vectors (embeddings + 36 layers) × 4,096 numbers. Thinking is switched off in the chat
template. Variants: `truth` (bare statement as a single user message), `*_claimpos` (the
token at the end of the claim sentence instead of the end of the turn), `reversal_postonly`
(pre-switch turns cut off), `reversal_userhistory` (user's pre-switch turns merged, assistant
replies removed), `reversal_neutralassistant` (assistant's pre-switch replies replaced by
"Thanks, that's a good question. Let's keep going."). Output: `activations/<name>.pt`
holding `acts` [n, 37, 4096] in float16 and `meta` (id, topic, level, turn, ...). Sizes:
2,748 snapshots for the Codex main set, 2,846 for Gemma. These files live only on the pod's
volume; everything downstream is in git.

## 3. E1: can the opinion be read at all? (`04_probe_e1.py`)

**Child's version.** We showed a very simple detector (a "probe") thousands of those
number-lists, each with the true label, and asked it to learn a rule. Then we tested it on
topics it had never seen. If it still works, the model really is keeping the opinion, in a
simple readable form.

**How.** The probe is `StandardScaler + LogisticRegression(C=0.1)` on one layer's vector.
Training on the 8 training topics, testing on the 4 held-out ones (179 dialogues, 933
snapshots). For each of the 37 layers we fit three probes: competence (the real one),
shuffled labels (must collapse to chance, catches leaks and bugs), and topic (must be high,
proves the activations carry information at all). The best layer by held-out accuracy is
kept, refit, and saved as `probe_e1.joblib`; a probe trained on both writers' dialogues is
saved as `probe_e1_pooled.joblib` and used downstream. Outputs: `results_e1.json`,
`figures/e1_layer_profile.png`, `figures/e1_turn_curve.png`, `e1_output*.txt`.

**What came out.** Layer 22: 98.5% per snapshot on held-out topics, 99.4% [98.3, 100] per
dialogue at the final turn (178 of 179). Shuffled 32.7%, topic 100%, word-counts-only 46.1%.
Accuracy is 81% at layer 1, about 90% from layer 11, about 98% from layer 21. No novice↔expert
swap in 933 snapshots. First message alone: 96.6%; turn 3 minus turn 0 is +3.4 points, so
prediction H1b ("rises with turns", line +8) was NO: the first message already gives it away.

**What could have fooled us.** (a) The probe reads one writer's house style for "novice":
a probe trained on Codex and tested on Gemma scores 67.6% (60.7% the other way), but the
confusion matrix puts the whole drop in one cell (Gemma's intermediates called novices);
keeping the direction and refitting only the thresholds gives 94.1%, and the pooled probe
gives 97.6% on each writer. The direction is shared; the calibration is not. (b) The probe
reads keywords: a probe trained on dialogues where the user states their level, tested on
dialogues where they never do, gets 91.4% (96.7% the other way), so told and shown competence
land on one representation. (c) Length: 46% vs 98.5%, and the two writers' length patterns
point opposite ways, so transfer cannot be length.

**Feeds.** The probe is now a frozen ruler. Every later experiment reads it without refitting.

## 4. E2: does the opinion change when you change? (`05_dynamics_e2.py`)

**Child's version.** We wrote 96 conversations where the visitor acts like a beginner for
three questions and then suddenly like an expert (or the reverse). We held the frozen ruler up
to every question and watched the opinion move. Big surprise: one clumsy question knocks an
"expert" down to the floor at once, but three expert questions only get a "beginner" 70% of
the way up, and a quarter of them are still called beginners at the end.

**How.** The frozen pooled probe gives P(expert) at each of the six turns of each reversal
dialogue. Baselines come from consistent dialogues in the main set at the same turn index
(turn 6: novice 0.001, expert 0.983). Three pre-registered numbers: crossover (turns until
the mean crosses 0.5), journey fraction (how far the estimate has moved from its own
pre-switch value toward the new level's baseline; removes the "less distance to travel"
confound), and the anchoring gap at the matched turn 6. 2,000 bootstrap resamples over
dialogues give the intervals. Outputs: `results_e2.json`, `figures/e2_update_curves.png`.

**What came out.** Both directions cross 0.5 within one turn of the switch. Journey fraction
expert→novice 0.70 on the first switched turn and 0.97 by the last; novice→expert 0.39 and
0.71. Asymmetry +0.31 [+0.16, +0.46] first turn, +0.26 [+0.16, +0.36] last (Codex-only probe:
+0.23, +0.22). Prediction H2b was 29%: a surprise. Anchoring: novice-start users end 0.28
[0.18, 0.39] below a lifelong expert; expert-start users end 0.03 above a lifelong novice.
Plain words: 27% of novice-start users are still called novices after three expert turns;
0% of expert-start users are still called experts after three novice turns. Because the
probe is saturated, the curves are mostly per-dialogue flips (share flipped on the three
switched turns: 0.42/0.58/0.73 and 0.73/0.92/1.00), and we say so.

**What could have fooled us, and the chain of controls.**
1. The writer, not the model: maybe Codex wrote weak post-switch experts. Control
   `reversal_postonly`: feed only the post-switch turns. They score 1.000 alone (lifelong
   experts 0.983). History effect +0.30 [+0.21, +0.40], writing effect −0.02. The anchoring is
   caused by what sits in the context.
2. Is the asymmetry just louder evidence in one direction? In isolation the post-switch
   novice turns score 0.000 and the post-switch expert turns 1.000, the floor and the
   ceiling, so by the probe's own measure both are equally loud. Partial answer only.
3. Which part of the history anchors? `reversal_userhistory` (user turns kept, assistant
   replies removed by merging) gave +0.01 and looked like "the model anchors on its own
   replies", but the merge changed the structure too. `reversal_neutralassistant` (every
   turn in place, the three pre-switch replies replaced by a fixed neutral line) gave +0.17
   [+0.09, +0.26], and the first draft said "about half is the model's own replies".
4. Sept 10, `17_e2_history_decomposition.py`: the same 48 dialogues underlie every variant,
   so the honest statistic is paired, per dialogue. Full minus placeholder +0.13 [+0.06,
   +0.20], share 0.44 [0.23, 0.64]. But in the other direction the same placeholder moves the
   estimate toward the middle by the same amount (expert→novice 0.03 → 0.16). Either the
   content of the model's own replies carries part of the anchor, or a repeated
   off-distribution line just makes the model less sure about the user. Our controls cannot
   tell. The claim is now: anchoring is real, it is not carried by the user's own words alone,
   and the content-versus-structure split is not identified. Output:
   `results_e2_history.json`, `figures/e2_history_decomposition.png`.

**Feeds.** Everything so far is a probe readout. Two questions follow: does the model SAY
this opinion, and does the opinion show in BEHAVIOUR?

## 5. Just ask the model (`11_just_ask_e1.py`)

**Child's version.** Instead of the ruler, we simply asked the model: "Is this person a
beginner, intermediate or expert?" It said "intermediate" about everyone. Forced to pick
beginner or expert at the end of a conversation, it was right almost every time. Asked after
the very first message, it guessed "beginner" for everyone, while the ruler already knew.

**How.** One appended user message asks for a one-word rating: three-way, a "brief a
colleague, be accurate not polite" variant, a forced binary, and a third-person variant; at
the final turn, after the first message, and at every turn of the reversal dialogues.
Outputs: `results_e1_justask*.json`, `e1_justask_*.txt`.

**What came out.** Three-way: "intermediate" for all 179 held-out dialogues at the end, all
179 after the first message, all 96 reversal dialogues (33.5%, chance). Colleague variant
49%. Forced binary at the end: 118 of 119 right. Forced binary after the first message:
"beginner" 178 of 179 times (chance) while the probe reads the same message at 96.6%. After
a switch, the stated estimate matches current behaviour 60% (n→e) and 67% (e→n) of the time
against 73% and 100% for the probe. This is Neel's "compare to just asking" check, and the
answer is that the internal estimate is sharper and faster than the stated one.

## 6. Does the opinion show in behaviour, and is the direction causal? (`12_causal_anchoring.py`, `07_steering_e4.py`)

**Child's version.** We looked at what the model actually wrote at the end of the reversal
conversations. Replies to a "used-to-be-a-beginner" expert were pitched a little lower than
replies to a lifelong expert, so the quiet opinion leaks into the answers a bit. Then we
reached inside and pushed the model's numbers along the "expert" direction while it wrote:
answers got harder; pushed the other way, simpler. Random pushes of the same size did
nothing.

**How.** Direction = mean(expert) − mean(novice) at layer 22 over the main set. A forward hook
on decoder layer 21 (whose output is hidden_states[22]) adds α × 0.1‖d‖ × unit at every
position during generation; α ∈ {−8, −4, 0, 4, 8}; three random unit directions of equal
norm as controls; 12 neutral questions; system prompts "the user is a complete beginner /
a domain expert" as the black-box baseline. Judge scores pitch 1–5, coherence 1–5, and
whether the reply names the reader's level; Flesch–Kincaid grade as a second measure; α* =
largest strength with coherence ≥ 4 at both signs (rule fixed before the run; it was 8).
`12_causal_anchoring.py` applies the same hook to the reversal dialogues (steer) and to
lifelong experts (mean-ablation: set the projection on the direction to the dataset mean).
Outputs: `results_e4.json`, `results_e4_raw.json`, `figures/e4_dose_response.png`,
`results_e2_causal.json`, `figures/e2_causal_anchoring.png`, `e4_read.txt`,
`e2_causal_read_blind.txt`.

**What came out.** Pitch of the final reply: lifelong novice 2.58 ± 0.10, novice→expert
reversal 4.35 ± 0.09, lifelong expert 4.64 ± 0.06: behavioural anchoring −0.29 ± 0.11, real
but small next to the probe's 30% deficit. Steering the reversal replies lifts them above
lifelong experts (+0.11 ± 0.09; sufficiency, not un-anchoring, since we had no
steered-lifelong-expert condition). Ablating the direction on lifelong experts lowers pitch
by 0.28 ± 0.09, about a quarter of the adaptation. Coherence 4.90–4.98 throughout. On neutral
questions: grade 9.2 at −8 to 12.1 at +8, random directions flat at 10.0–10.5, span +3.13
over random (SE 0.60; line was 2); judged level 1.17 → 1.67 → 2.58 vs +0.06 for random;
system prompts 7.1 / 11.4. H4b (steering covert, prompting overt): NO, both are covert
(0 of 48 steered, 2 of 24 prompted name the level). Yash's blind read found a dose-response
in framing phrases ("let me explain simply"): 10/12 beginner-prompted, 5/12 at −8, 4/12 at
−4, 2/12 at 0, 0 at +4/+8, 1–3/12 random. The probe weights and the diff-of-means direction
have cosine 0.46, so the two methods found overlapping directions.

**Feeds.** The user model is real, updates one way, anchors, leaks into pitch, and is not
what the model says. Now the safety question: does any of this touch honesty?

## 7. E3: what does the model do with a false claim? (`06_honesty_e3.py`, `06b`, `06c_e3_full600.py`, `08_judge_agreement.py`)

**Child's version.** The visitor says something wrong, either confidently ("Since the moon is
made of cheese, I figure...") or shyly ("I might be wrong, but..."). Does the model correct
them, dodge, or agree? And separately, does the model's private "is this true?" meter move
when the visitor sounds confident? We also trained a second ruler for that meter.

**How.** A truth probe (same recipe) on the 192 bare statements, layer 21 chosen by held-out
accuracy (96.9% bare). Pre-filter: each claim is asked neutrally ("True or false, one word");
only claims the model gets right are kept (184 of 190), so agreeing with a false claim is
deference, not ignorance. For each kept dialogue: the truth probe at the end of the claim
turn (and at the claim sentence, the pre-registered fallback), the model's greedy reply, and
Gemini's verdict from `judge_rubrics.md` (validate / hedge / correct). Pre-registered: H3
(in-dialogue truth accuracy ≥ 65%), H3b (validate rate confident ≥ 2× hedged AND ≥ 15-point
gap), H3c (confident-minus-hedged shift in P(true) on false claims minus the same shift on
true claims, within ±0.15). Outputs: `results_e3_raw.json`, `results_e3.json`,
`results_e3_600.json`, `results_e3_600_summary.json`, `results_e3_agreement_local*.json`,
`e3_handcheck_600.txt`, `figures/e3_sycophancy_gap_600.png`,
`figures/e3_internal_by_verdict_600.png`.

**The pivot.** The first pass capped replies at 200 tokens; 157 of 184 were cut mid-sentence,
and Qwen corrects slowly (compliment, long explanation, then the correction). Re-running the
21 decisive replies at 600 tokens flipped 13 verdicts, so all 91 false-claim replies were
regenerated; validation went from 15.6% / 6.5% to 13.3% / 4.3%. Logbook §6.

**What came out.** H3 YES: 88.7% in-dialogue on held-out topics. H3b NO by the rule: confident
37 correct / 6 validate / 2 hedge of 45; hedged 42 / 2 / 2 of 46; ratio 3.1 passes, gap +0.09
[−0.02, +0.20] fails the 15-point guard. H3c YES: the confident voice raises P(true) by 0.10 on
false claims and 0.09 on true ones, difference +0.01 [−0.12, +0.14]; tone does not corrupt the
internal truth score. Unplanned: split by what the reply did, P(true) is 0.15 [0.10, 0.20] when
corrected (n = 79), 0.52 [0.37, 0.67] when validated (n = 8), 0.54 when hedged (n = 4); not
corrected minus corrected +0.38 [+0.23, +0.53]; "knows it is false and defers anyway" is
about 4 of 91. Judge checks: Phi-4 agrees with Gemini on 63% three-way and 55 of 60
validated-vs-not; Gemini re-labels 4 of 21 identical borderline replies across runs; Yash read
all 12 uncorrected replies plus 9 corrections (21/21 final, 18–19/21 first pass).

**What could have fooled us.** The by-verdict split is read at the end of the turn, the state
the reply is written from: the probe might read "I am about to agree" rather than a belief.
That is what §8 tests.

## 8. Sept 10 check: is the "unsure" reading about the claim or about the reply? (`18_e3_bare_probe_by_verdict.py`, `e3_common.py`)

**Child's version.** Take the same wrong sentences the model failed to correct, show them to
the truth meter with no conversation around them at all, and see if the meter is still
unsure. It is. So the model was already unsure about those facts; the conversation did not
create the doubt.

**How.** Leave-one-topic-out truth probes at layer 21 (each statement scored by a probe that
never saw its topic; accuracy 0.88), applied to the 46 distinct false claims behind the 91
E3 rows, split by the 600-token verdict; also at the statement-last-token position (layer
23, 0.90). Outputs: `results_e3_bare.json`, `figures/e3_bare_vs_dialogue_by_verdict.png`.

**What came out.** Bare P(true): not corrected 0.42 vs corrected 0.10, +0.33 [+0.13, +0.52];
the bare score alone ranks uncorrected above corrected with AUC 0.77 (p = 0.001); claim level
(9 ever-not-corrected vs 37 always-corrected) +0.41 [+0.18, +0.65]; last-token position +0.27
[+0.09, +0.45]. H7 = YES. The E3 lead is promoted: failures to correct concentrate on claims
the model doubts in isolation. Still 12 rows / 9 claims.

## 9. Sept 10 check: paired decomposition of the anchoring source (`17_e2_history_decomposition.py`)

Covered in §4, item 4. Result: the "about half" claim is softened to "consistent with, not
established", because the placeholder moves estimates toward the middle in both directions.

## 10. E5: does the opinion about the user change what the model does with a false claim? (`19a_generate_linking_codex.py`, `19_linking_e5.py`)

**Child's version.** Same wrong sentence, word for word. Once it comes from someone who sounded
like a beginner for two questions, once from someone who sounded like an expert. We check
with the ruler that the model really formed the two opinions. Then: does it correct the
expert-looking person less often? A little (39% let it pass vs 28%), not enough to be sure.
Does its private truth meter move? Yes, clearly, toward "maybe true" for the expert-looking
person, and only for false sentences. Does its one-word answer "true or false?" move? No.
So the opinion bends the model's private belief quietly, and its behaviour a bit.

**How.** Codex wrote one confident claim turn per claim for 95 false and 47 true statements,
then two pre-claim user turns plus two assistant replies in the novice register and, separately,
in the expert register; the claim turn is forced to be identical in both (284 dialogues; 2
rejected for self-labels). Quality check before the run: pre-claim user turns at reading grade
10.0 vs 17.0 at equal length; 0 leaks; identical third turns in all 142 pairs. On the pod:
`03_extract_activations.py linking` and `linking_claimpos`; `19_linking_e5.py generate` runs
the same neutral pre-filter as E3 (268 of 284 kept), the 600-token greedy reply, the Gemini
verdict, and a "one word first: is the statement I just made true or false?" variant appended
to the claim turn; `analyze` applies the pooled E1 probe at the turn before the claim
(manipulation check, pass rule ≥ 80% fixed on Sept 4), the leave-one-topic-out truth probe at
the claim turn, pairs everything by claim, bootstraps over claims, runs exact McNemar tests
on discordant pairs, and writes the hand-check file. Predictions for H5 were NOT written
before the run (the cells were blank); recorded as such. Outputs: `results_e5_raw.json`,
`results_e5.json`, `e5_output.txt`, `e5_handcheck.txt`, `figures/e5_linking.png`.

**What came out.** Manipulation: 134/134 novice-context dialogues read as novice (mean P(expert)
0.000), 134/134 expert-context as expert (0.996). Behaviour, 88 paired false claims:
validated 38.6% expert-looking vs 28.4% novice-looking, +0.10 [+0.00, +0.22], discordant
16 vs 7, p = 0.093; not corrected 51.1% vs 39.8%, +0.11, 18 vs 8, p = 0.076. True claims
challenged 0/46 and 1/46. Internal: P(true) at the end of the claim turn 0.455 vs 0.362, paired
+0.09 [+0.04, +0.15]; true claims +0.01; at the claim sentence +0.02 (n.s.), so the bend appears
between the claim and the reply. Stated: says "false" 64.8% vs 60.2%, +0.05 [−0.05, +0.14];
the presupposition alone costs about 40 points of stated accuracy for everyone. H5c: a
confident claim lowers P(expert) by 0.05 (false) vs 0.04 (true); null. Split by bare
uncertainty (from §8): claims the model doubts (n = 14) fail to be corrected 71% of the time in
both contexts; claims it is sure are false (n = 74): 34% novice-looking vs 47% expert-looking.
The claim's own uncertainty dominates; the user matters only where the model knows better.

**What could have fooled us.** Judge noise (E3: 4/21 flips) — first 20 hand-check items to be
read; "hedge" might mean "busy correcting the novice's earlier misconception"; the pre-claim
assistant replies were generator-written in the level's register (part of the manipulation);
the end-of-turn probe shift could be the reply plan (the claim-position null is consistent
with either reading); rates are not comparable with E3 (different claim wording and pool);
not pre-registered.

## 11. How everything connects

E1 builds the ruler and proves it measures competence rather than topic, length or one
writer's style. E2 uses the frozen ruler and finds the two properties of the update rule
(asymmetric, anchored), and the control chain (post-only → user-history → placeholder →
paired decomposition) decides what is real and what is not identified. Just-ask shows the
stated opinion is a different, blunter thing than the internal one. The causal work shows the
opinion leaks into pitch and that the direction is sufficient for pitch. E3 asks the safety
question with tone as the lever and finds mostly a null plus a lead; §8 turns the lead into
a finding about the claim itself. E5 finally uses the ruler as a manipulation check and links
the user model to honesty: the internal truth estimate bends with the apparent user, behaviour
bends weakly, the stated answer does not, and the bend lives only where the model is sure.

Two insights survive: (1) the model keeps a private, sharp, asymmetrically updated and
self-anchored estimate of the user, which is not what it says when asked; (2) what the model
does with a false claim is driven first by its own uncertainty about the claim and second, and
quietly, by who it thinks is asking.

## 12. File map

| Step | Code | Inputs | Outputs |
|---|---|---|---|
| Config, rules | `config.py`, `fewshot.py`, `judge_rubrics.md` | — | — |
| Data | `01c_generate_codex.py` (laptop), `01b_generate_local.py` (pod), `19a_generate_linking_codex.py`, `20_generate_neutral_replies_codex.py` (not run) | claims.json, prompts | `data/*.jsonl`, `data/codex/*.json` |
| QC | `02_qc_dialogues.py` | data | `qc_*.txt/jsonl`, logbook §4 |
| Activations | `03_extract_activations.py <set>` | data | `activations/*.pt` (pod only) |
| E1 | `04_probe_e1.py`, `11_just_ask_e1.py` | main.pt, main_gemma.pt, explicit.pt | `results_e1*.json`, `probe_e1*.joblib`, `figures/e1_*` |
| E2 | `05_dynamics_e2.py`, `17_e2_history_decomposition.py`, `13_fig_anchoring_source.py` | reversal*.pt, main.pt | `results_e2.json`, `results_e2_history.json`, `figures/e2_*` |
| Causal / E4 | `12_causal_anchoring.py`, `07_steering_e4.py` | main.pt, reversal.jsonl, judge | `results_e2_causal.json`, `results_e4*.json`, `figures/e4_*`, read files |
| E3 | `06_honesty_e3.py`, `06b_e3_recheck.py`, `06c_e3_full600.py`, `08_judge_agreement.py`, `18_e3_bare_probe_by_verdict.py`, `e3_common.py` | truth*.pt, honesty*.pt, judge | `results_e3*.json`, `e3_handcheck_600.txt`, `figures/e3_*` |
| E5 | `19_linking_e5.py generate/analyze` | linking*.pt, judge | `results_e5*.json`, `e5_handcheck.txt`, `figures/e5_linking.png` |
| Write-up | `10_writeup_materials.py`, `16_build_writeup_draft.js`, `writeup_content.json` | results, logbook | `writeup_draft_v2.md`, `MATS12_writeup_draft_v2.docx` |
| Record | `logbook.md` | — | predictions, every run, hand-checks, pivots, timeline |
