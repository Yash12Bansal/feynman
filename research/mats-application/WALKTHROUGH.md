# The full story of this project, in order — what we did, why, which files, what came out

Written 2026-09-04 for Yash, who has not seen most of the code run. Every section
follows the same shape: the question, why it matters, exactly what the code does, the
files that go in and come out, the numbers that came out, what we doubted, and what we
changed because of it. Read it top to bottom once; then use it as a map when you open
any file. Every number here comes from `results_digest.md`, `results_*.json` or
`logbook.md`. Nothing is retyped from memory.

---

## Part 0. The question and the design of the whole thing

### 0.1 The one-sentence project
Does Qwen3-8B keep an internal estimate of *how much the person it is talking to knows*,
does that estimate update as the conversation gives it evidence, does it drive how the
model writes, and does the model's own account of the user match it?

### 0.2 Why this question and not another
Nanda's MATS doc lists "user models" as a suggested problem and asks verbatim whether
LLMs "form dynamic models of users for attributes that vary across turns, e.g. what the
user knows". Prior work (TalkTuner, Chen et al. 2024) showed that models represent *who*
the user is (age, gender, education, income) as linear directions and that you can steer
on them. Those are static facts about a person. Competence on a topic is different: it
can change inside one conversation, and the model gets fresh evidence every turn. So the
delta over prior work is three things: the attribute is dynamic, we watch it update, and
we compare the internal estimate with what the model says and does. The safety angle: a
model that quietly decides you are a novice and then discounts your later corrections is
the seed of both sycophancy and manipulation.

### 0.3 The four experiments, planned before anything ran
- **E1, existence.** Can a linear probe read the user's level from the residual stream?
  Where in the network? Does it generalize to topics the probe never saw?
- **E2, dynamics.** Freeze that probe. Feed scripted dialogues where the user changes
  level mid-conversation. Watch the probe's reading move turn by turn. How fast, is it
  symmetric, does the first impression persist?
- **E3, honesty.** When the user confidently asserts a false claim, does the model's
  internal truth reading stay correct while its reply caves? This was the intended
  headline.
- **E4, causality.** Steer along the competence direction. Does the model's writing
  change the way a real change in the user's level would change it, beyond random
  directions, without breaking the model?

Then two post-hoc controls were added after reading Nanda's evaluation notes and an
outside review: "just ask the model" and a causal follow-up to E2.

### 0.4 The three-model-family rule
The whole thing rests on one hygiene rule encoded in `config.py`: the model we study
(Qwen3-8B), the model that writes the dialogues (GPT via Codex, and separately
Gemma-3-27B), and the model that judges replies (Gemini 2.5 Pro; Phi-4 as a second judge)
are three different families. If Qwen had written its own training dialogues, its own
stylistic fingerprints could carry the label into the activations we probe. If the judge
were the same family as the generator, it might grade its own style. Keeping them apart
is what lets us say the probe reads competence, not a house style.

### 0.5 The prediction table (logbook §0)
Before any experiment ran you filled a table of 11 hypotheses (H1, H1b, H1c, H2, H2b,
H2c, H3, H3b, H3c, H4, H4b). Each row has your probability, a threshold that counts as a
"yes", a floor that counts as a "no", and a reason. This is the single most legible
"taste" signal in the write-up, because it shows what surprised you. Outcome column and
"what I learned" column were filled in as each experiment finished. Final tally: 8 yes,
3 no. Three of your four lowest-probability bets came out yes (H3c at 25%, H2b at 29%,
H2c at 32%); only H4b at 22% did not.

### 0.6 Files that define the project
| File | What it holds | Why it exists |
|---|---|---|
| `config.py` | MODEL_ID = Qwen/Qwen3-8B; 12 topics with a seed question and two novice misconceptions each; the 4 held-out topics (immunology, chess, statistics, networking); the three level definitions; dataset sizes; `chat_text()` which serializes messages with Qwen's chat template and thinking turned off; `act_path()` which names activation files by dataset and generator; judge backend priority | One place for every parameter so nothing is changed silently mid-project |
| `README_START_HERE.md` | The plan: phases, hour budget, the hour-6 GO/NO-GO rule, the pre-registered refinements table, write-up rules, framing rule | The contract we followed |
| `CLAUDE.md` | Rules for me: log everything, print 5 random examples for every dataset, never change parameters silently, name the dumbest alternative explanation after every result, never ghost-write your summary | Discipline |
| `judge_rubrics.md` | The exact wording of every judge prompt: E3 verdict (correct / hedge / validate), E4 scoring (level 1–5, coherence 1–5, mentions_level yes/no) | So the judge is auditable |
| `logbook.md` | §0 predictions, §2 one entry per run, §3 your verification checklist, §4 QC record, §5 your E3 hand-check, §6 pivots, §7 external review, §8 observation→decision timeline, §9 prior-art check | The appendix and the audit trail |

Why thinking is off: Qwen3 is a hybrid reasoning model that emits a `<think>` block by
default. E1 and E2 read activations before any reply, so thinking adds nothing there. E3
needs the model's actual answer to a claim, and a 500-token deliberation makes the
judge's job ambiguous and the truncation problem worse. One variable at a time.

---

## Part 1. Building the data (scripts 01, 01b, 01c, fewshot.py)

### 1.1 What the datasets are and why each exists
All are in `data/` as JSON-lines, one dialogue per line. Every dialogue is a list of
`{role, content}` messages alternating user and assistant, starting with the user.

| File | Rows | Shape | Purpose |
|---|---|---|---|
| `data/main.jsonl` | 536 | 12 topics × 3 levels × ~15 dialogues, 4–8 user turns, the user never states their level | Train and test the E1 competence probe |
| `data_gemma/main.jsonl` | 540 | Same shape, written by Gemma-3-27B instead of GPT | The cross-generator control |
| `data/explicit.jsonl` | 144 | 12 × 3 × 4; identical brief except the user *states* their level ("I'm a complete novice") in the first turn | Test whether told-competence and shown-competence land on the same internal representation (H1c) |
| `data/reversal.jsonl` | 96 | 48 novice→expert, 48 expert→novice; exactly 6 user turns; the user's behaviour flips at user turn 4 (index 3) | E2 update curves |
| `data/honesty.jsonl` | 190 | 12 topics × {claim true, claim false} × {confident voice, hedged voice}; the user asserts the claim in user turn 3 (index 2); 95 confident / 95 hedged; 95 true / 95 false | E3 |
| `data/truth.jsonl` | 192 | 8 true + 8 false bare statements per topic, no dialogue around them | Train the truth probe that E3 applies inside dialogues |

Why the truth probe is trained on bare statements and applied inside dialogues: that
distribution shift is deliberate. If the truth signal only existed in isolation and did
not survive being wrapped in a conversation, that itself would be a reportable finding.

### 1.2 The anti-confound rules baked into generation
Every generator prompt enforces the same rules (see the `RULES` block in
`01c_generate_codex.py`):
- The same 12 topics and the same underlying questions at every level, so the probe
  cannot use topic as a shortcut for level.
- The user never states or hints at their level, background, job or study history. A
  banned-phrase regex (`beginner`, `novice`, `expert`, `years of`, `PhD`, `student`, …)
  rejects dialogues that slip.
- Every user turn is 25–60 words at every level, so length cannot be the shortcut.
- Neutral, curious tone at every level, so sentiment cannot be the shortcut.
- Level is carried only by content: whether a listed misconception is stated as a
  belief, precision of terminology, the type of question (what/why vs how/when vs edge
  cases and trade-offs), and whether hedging is calibrated.

`fewshot.py` holds two hand-written gold dialogues on thermodynamics (a topic not in our
list, so exemplar text cannot leak into anything we probe). They exist because "subtle"
is the hardest instruction to convey; showing two examples where level is carried only
by *what the user is precise about* closes most of the gap between a mid-size model and
a frontier one on this constrained writing task.

### 1.3 Three generator scripts, and why there are three
- `01_generate_dialogues.py`: the original plan, per-dialogue API calls through OpenRouter
  to a frontier model. Holds the prompt templates, the parser, and the save routine that
  the other two scripts import.
- `01b_generate_local.py`: fallback written when OpenRouter credits were stuck at $0 (an
  RBI e-mandate delay on the Indian card). Runs a local generator on the pod. This is what
  produced `data_gemma/main.jsonl` with Gemma-3-27B (log in `gen_gemma_log.txt`): 540
  dialogues, 0 parse failures.
- `01c_generate_codex.py`: runs on your laptop through the Codex CLI. One call per
  (topic × level) cell writes a JSON file of 15 dialogues into `data/codex/` (121 cell
  files there now, including the `claims.json` used for truth and honesty). The script
  merges cells into the `.jsonl` files and rejects any dialogue that trips the banned-
  phrase filter: 4 were rejected from main, which is why main has 536 and not 540.

What was supposed to be a workaround became a control. Two independent generators
writing the same brief means we can train the probe on one and test on the other. If the
probe reads competence it should transfer; if it reads "how GPT writes a novice" it
should not. This is logged in §8 as the first observation→decision row.

---

## Part 2. Quality control before spending GPU time (script 02, logbook §4)

### 2.1 Why QC comes first
Nanda: "If bad data would sink your project, show me the data." A probe trained on
dialogues where novices are simply shorter, or where they say "I'm new to this", would
score high for the wrong reason. So three checks ran before any activation was extracted.

### 2.2 The three checks in `02_qc_dialogues.py`
1. **`audit`**: words per user turn by level, and the banned-phrase leak filter.
   Result (§4a, §4b): Codex novice/intermediate/expert = 33.4 / 32.9 / 36.6 words; Gemma
   = 42.6 / 37.8 / 34.3. So length does carry level information, and in *opposite*
   directions in the two sets. Leaks: 0 in Codex, 2 flags in Gemma that were both false
   positives ("years of" fund data; "intermediate nodes" in networking).
   Decision: keep both sets; add a length-only classifier to E1 so the write-up can say
   exactly how much of the probe's accuracy length explains; and note that any probe
   that transfers between generators cannot be reading length, because the sign flips.
2. **`read`**: prints 3 random dialogues per cell into `qc_read_sample.txt` for a human
   to read. You read novices and experts; I read 6 random Codex novices. Two properties
   were recorded (§4c): register is equally polished at every level (level is in content,
   not writing quality), and novices visibly *learn* across the dialogue, often stating
   the correct view by the last turn. So "novice" describes where the persona starts.
3. **`judge_local`**: a blind judge (Phi-4 locally, later Gemma-27B) sees only the user
   turns and guesses the level. Purpose: if a whole LLM cannot recover the level, a
   linear probe result would be uninterpretable; if it gets 100%, the signals are too
   on-the-nose. Target was 85–95%.

### 2.3 The judge result that looked like a disaster and what it turned out to be
First run: Phi-4 agreed with the labels only 36.7% of the time on Codex, 55% on Gemma.
That is the point where a sloppy project either regenerates data or ignores the number.
We did neither. The script was extended (commit 13da8ab) to put the level definitions
into the judge prompt, allow 24 output tokens, and print a confusion matrix plus every raw
judge output into per-item files (`qc_judge_phi-4.jsonl`, `qc_judge_gemma-3-27b-it.jsonl`,
…, and the text summaries `qc_judge_codex_phi4.txt`, `qc_judge_codex_gemma27.txt`,
`qc_judge_codex_phi4_first2.txt`, `qc_judge_gemma_phi4.txt`).

The confusion matrices (§4d) showed one specific thing: every error in every run is a
shift of exactly one step, always upward (novice called intermediate, intermediate called
expert), and novice↔expert swaps are 0 of 120 with the strong judge. Rank correlation
between true and judged level: 0.86–0.87 in every run. Then the decisive test: a
`JUDGE_TURNS=2` option that shows the judge only the first two user turns. Agreement went
from 51.7% to 80.0%, and novice recall from 8/38 to 30/38. So the judge was not wrong
about the labels. The novice personas absorb the assistant's explanations and read as
intermediates by the end. The same shift appears in the Gemma set (29/37), so it is a
property of realistic tutoring dialogues, not one generator.

§4e records the decision, written before E1 ran: labels are valid where each persona
starts and the three levels are correctly ordered everywhere; the honest QC criteria are
no extreme swaps, rank correlation above 0.8, and at least 80% agreement on opening turns,
all met; expect the probe's confusions to sit between novice and intermediate; report
early-turn and final-turn accuracy both. This pre-registration matters later: it is why
the H1b "no" is a ceiling and not a failure.

---

## Part 3. Getting the activations out (script 03)

### 3.1 What an activation is here
A transformer keeps a running vector per token, the residual stream, that every layer
reads and writes. Qwen3-8B has 36 layers and a 4096-dimensional residual stream. We
store the residual stream at the *last token position* of the prompt, at every layer
(37 vectors including the embedding output). That position is the exact state from which
the model would begin writing its reply, so whatever it has inferred about the user must
be usable there.

### 3.2 How `03_extract_activations.py` does it, and why the slow way
For user turn t of a dialogue, the script takes the conversation truncated to turns 0..t,
appends the chat template's generation prompt, runs one forward pass with
`output_hidden_states=True`, and keeps `hidden_states[layer][0, -1]` for every layer.
That is one short forward pass per user turn. A faster method would run the whole
dialogue once and index into the right positions, but chat-template token indexing is the
number one source of silent bugs for newcomers. O(turns) forward passes cost minutes on an
A100 and cannot be wrong. Optimization was allowed only after the science worked.

Output: `activations/<dataset>[_<generator>].pt` with `acts` (float16, shape
[n_snapshots, 37, 4096]) and `meta` (dialogue id, topic, level or labels, turn index).
The activation files live on the pod's network volume, not in git (they are hundreds of
MB each). The extraction logs are in the repo as `act_main.txt` etc.

| Dataset | Snapshots | Note |
|---|---|---|
| main (Codex) | 2748 from 536 dialogues | one per user turn |
| main_gemma | 2846 from 540 dialogues | |
| explicit | 809 | |
| reversal | 576 = 96 × 6 turns | |
| honesty | 760 | |
| truth | 192 | one per bare statement |

### 3.3 The extra modes added during the project
Each was added because a result raised a question that only a different extraction could
answer. They are all in the same script, chosen by the command-line argument:
- `reversal_postonly`: the reversal dialogues with everything before the switch cut off.
  Added after E2, to test whether the anchoring gap comes from the history or from the
  writing of the post-switch turns.
- `reversal_userhistory`: keeps the user's pre-switch turns but removes the assistant's
  pre-switch replies (the novice turns are merged into the first post-switch user
  message). Added to ask whether the anchor is the user's words or the model's own
  replies.
- `reversal_neutralassistant`: every turn stays in place; the three pre-switch assistant
  replies are replaced by a fixed neutral placeholder, "Thanks, that's a good question.
  Let's keep going." Added because the previous control also changed the dialogue's
  structure, which confounded the reading.
- `truth_lastword` and `honesty_claimpos`: snapshots at the last token of the bare
  statement and at the end of the claim *sentence* inside the claim turn, instead of the
  end of the turn. This is the pre-registered H3 fallback: the truth signal might not
  travel to the end of a turn that continues with reasoning and a question. The claim
  position is found via the tokenizer's offset mapping (`at_char_end`,
  `claim_sentence_end`), matching the claim text exactly or by its first 60% and then the
  first sentence-ending punctuation.

---

## Part 4. E1, existence: can a linear probe read the user's level? (script 04)

### 4.1 What a probe is
The model is frozen. For each layer we take the stored 4096-dimensional vectors and fit a
logistic regression (with feature standardization, regularization C = 0.1) to predict
novice / intermediate / expert. We measure the model; we do not train it. If a linear
classifier on one layer's vector can read the level, the level is linearly represented
there.

### 4.2 The split that makes the result mean something
Train on the 8 training topics, test on the 4 held-out topics that the probe never saw
(immunology, chess, statistics, networking; 179 dialogues, 933 snapshots). If the probe
had merely learned "questions about lenses come from novices", it would fail on chess.
Chance is 33.3%.

### 4.3 What `04_probe_e1.py` computes and why each piece is there
1. **Layer profile**: held-out accuracy at every one of the 37 layers. Existence and
   location.
2. **Shuffled-label control**: same pipeline with labels permuted. Must collapse to
   chance; if it does not, there is leakage or a bug.
3. **Topic probe**: predict the topic from the same activations. Must be high. This is
   the positive control that proves the activations are rich, so a competence null would
   mean the concept is absent, not that the pipeline is broken.
4. **Length-only baseline**: a classifier that sees only word counts, trained on the same
   split. Added after the QC audit. The activation probe must beat it clearly.
5. **Held-out confusion matrix, count of novice↔expert swaps, binary novice-vs-expert
   probe**: added after QC predicted that confusions would sit between neighbours.
6. **Turn curve with one fixed probe**: train one probe on all training-topic snapshots
   and evaluate it per turn index. Pre-registered as the primary H1b curve so that a rise
   cannot come from more training data at later turns. A growing-data curve is kept as a
   secondary line.
7. **Per-level recall by turn and P(true class) by turn**: does the probe's reading of a
   novice drift as the novice learns?
8. **Explicit↔implicit transfer (H1c)**: train on explicit, test on implicit held-out
   topics, and the reverse. Pre-registered to be topic-clean in both directions so the
   explicit set cannot leak held-out topics into training.
9. **Cross-generator transfer**: train on Codex training topics, test on Gemma held-out
   topics, and back. Runs only if `activations/main_gemma.pt` exists.

Outputs: `results_e1.json`, `probe_e1.joblib` (the Codex probe and its best layer),
`probe_e1_pooled.joblib`, `figures/e1_layer_profile.png`, `figures/e1_turn_curve.png`,
console logs `e1_output.txt` (v1) and `e1_output_v2.txt` (v2).

### 4.4 Run v1 (logbook entry 2026-09-02 ~20:45)
- Best layer 22. Held-out accuracy 98.5% per snapshot; 99.4% per dialogue at the final
  turn (178/179, CI 98.3–100). Accuracy is already 81% at layer 1, about 90% from layer
  11, about 98% from layer 21 onward.
- Shuffled labels 32.7% (chance). Topic control 100%. Length-only 46.1%.
- Confusion on held-out: novice 312/314, intermediate 299/301, expert 308/318 (10 experts
  called intermediate). Novice↔expert swaps 0 of 933. Binary novice-vs-expert 99.7%.
- Turn curve (one probe): 96.6% at turn 0, then 99–100%. Turn 3 minus turn 0 = +3.4
  points. H1b line was +8, so H1b = NO, for the ceiling reason written in §4e before the
  run: the first message already gives the level away.
- Recall by turn stays about 1.0 for every level. The probe keeps calling late-turn
  novices "novice" even though blind judges call those same turns "intermediate".
- Cross-generator: codex→gemma 67.6%, gemma→codex 60.7%, against within-generator 98.5%
  and 96.4%.

What we doubted. The dumbest alternative explanation was that the probe reads Codex's
house style for each level. The cross-generator number said this was partly true: a
third of the accuracy did not survive a change of generator. Decision: GO, but report the
cross-generator number wherever 98.5 appears, and extend the script to find out *what*
fails to transfer.

### 4.5 Run v2 (entry ~21:15, commit d4872c2)
The script gained: cross-generator accuracy at every layer, the codex→gemma confusion
matrix, a probe trained on both generators, a test that keeps the Codex probe's direction
and refits only the decision thresholds on Gemma (via `decision_function` plus a small
logistic regression), and P(true class) by turn. `explicit.pt` now existed so H1c ran.
- H1c: explicit→implicit 91.4%, implicit→explicit 96.7%, own-set 98.9% / 98.5%. Worse
  transfer divided by own-set = 0.92, above the 0.8 line. H1c = YES. Told and shown
  competence converge on one representation; the explicit probe is not a keyword detector.
- Codex→Gemma confusion (rows true, columns predicted): novice [291, 0, 0]; intermediate
  [266, 50, 0]; expert [3, 30, 282]. The whole drop is one cell: Gemma's intermediates get
  called novice.
- Codex direction with thresholds refit on Gemma: 94.1%. Pooled probe: 97.6% on Codex
  held-out and 97.6% on Gemma held-out. Best raw-transfer layer is 14 (about 66%), so no
  layer transfers well without refitting thresholds; this is not a layer choice problem.
- P(true class) by turn stays 0.94–1.0 for every level at every turn. The internal
  estimate does not follow a novice's learning inside a dialogue.

Reading: the competence *direction* in Qwen is the same whoever wrote the dialogue; only
the *calibration* differs, because Gemma writes its "intermediate" closer to Codex's
"novice". The raw 61–68% was a threshold shift, not style leakage.

What we doubted: the pooled 97.6% could be two generator-specific rules learned side by
side. Argument against: one linear boundary cannot hold two different rules for the same
three classes, and the refit-threshold test shows the Codex direction alone gets 94% on
Gemma. Not fully closed; noted as a limit.

Decision, as pre-registered: downstream experiments use `probe_e1_pooled.joblib` because
it is within a point of within-generator accuracy. The Codex probe is kept as a
robustness check for E2.

### 4.6 What E1 means and does not mean
It means user competence is a linear direction at mid layers of Qwen3-8B, readable at
near ceiling from the first message, generalizing across topics and across two writers.
It does not mean much on its own: Nanda's own assessment of a past emotion-probe project
said "I expected it to work, didn't learn too much." E1 is the tool. One sentence in the
write-up should say it was expected.

---

## Part 5. E2, dynamics: does the estimate update? (script 05)

### 5.1 The idea
Take the frozen probe from E1 and apply it to every turn of the 96 reversal dialogues.
Frozen matters: we want to measure how the *model's* representation moves, not let a
refitted probe do the tracking. The reading is P(expert) per turn, with bootstrap
confidence bands over dialogues.

### 5.2 The three pre-registered numbers and the confounds each design choice kills
- **H2, crossover**: after the behaviour flips at user turn 4, how many turns until the
  mean P(expert) crosses 0.5? Also reported at the midpoint between the consistent-novice
  and consistent-expert baselines, as the fallback for a weak probe.
- **H2b, asymmetry**: fraction of the journey covered, where journey runs from the
  dialogue's own pre-switch value to the consistent baseline of the *target* level at the
  matched turn. This removes the confound that one direction may simply have less
  distance to travel. Bootstrap CI on the difference between directions.
- **H2c, anchoring**: the reversal dialogue's final estimate against consistent dialogues
  at the *same* turn index (turn 6, from main-set dialogues that have at least 6 user
  turns). Matched turns remove the 4–8-turn versus exactly-6-turn confound.

Inputs: `activations/reversal.pt`, `activations/main.pt` for baselines, the probe chosen
by the `PROBE_FILE` environment variable. Outputs: `results_e2.json`,
`figures/e2_update_curves.png`, logs `e2_output_pooled*.txt`, `e2_output_codex.txt`.

### 5.3 Results (entry ~21:40, pooled probe; Codex probe in brackets)
Baselines at turn 6: novice 0.001, expert 0.983 (n = 60, 61).
- novice→expert: mean P(expert) by turn [0.0, 0.0, 0.0, 0.38, 0.61, 0.70]; crosses 0.5
  one turn after the switch [0]; journey fraction 0.39 [0.53] on the first switched turn,
  0.71 [0.76] by the last.
- expert→novice: [1.0, 0.99, 1.0, 0.30, 0.09, 0.03]; crosses on the first switched turn;
  journey fraction 0.70 [0.76] then 0.97 [0.97].
- H2b: e→n minus n→e = +0.31 [+0.16, +0.46] at the first switched turn, +0.26 [+0.16,
  +0.36] at the last. Codex probe +0.23 / +0.22, CIs clear of 0. YES, and you had it at 29%.
- H2c: novice→expert ends 0.28 [0.18, 0.39] below a lifelong expert; expert→novice ends
  0.03 [0.01, 0.05] above a lifelong novice. YES in one direction, NO in the other.

Plain statement: after three turns of clearly expert behaviour, 27% of users who started
as novices are still classified as novices; after three turns of novice behaviour, 0% of
users who started as experts are still classified as experts.

### 5.4 The chain of controls, in the order they happened
This is the part of the project with the most re-runs, and each one was triggered by a
specific doubt. It is also where the most original finding came from.

**Doubt 1: the writer, not the model.** Codex might write post-switch expert turns less
convincingly than lifelong experts, so the 0.28 gap would be a property of the text.
Control: `reversal_postonly`, the same dialogues with everything before the switch cut
off. If isolated post-switch turns score like a lifelong expert, the gap comes from the
history. Result: in isolation they score 1.000 (lifelong expert 0.983); with the novice
history attached, 0.702. History effect +0.30 [+0.21, +0.40]; writing effect −0.02
[−0.04, −0.00]. The post-switch experts are, if anything, written slightly stronger. The
anchoring is real. (No prediction was written for this control beforehand, because of
time pressure that morning; the logbook records that gap rather than back-filling.)

**Doubt 2: the probe is saturated.** Baselines are 0.001 and 0.983, so a mean of 0.39
could mean "39% of dialogues have flipped" rather than "each dialogue is at 0.39". Added
per-dialogue flip fractions: novice→expert 0.42 / 0.58 / 0.73 on the three switched
turns; expert→novice 0.73 / 0.92 / 1.00. About a quarter of dialogues sit in the middle
band at any time, so the curves are mostly per-dialogue flips. Reported as such.

**Doubt 3: which part of the history anchors?** The history contains the user's three
novice turns *and* the assistant's three replies to them, which the generator pitched at a
novice. Control 1, `reversal_userhistory`: keep the user's novice turns, remove the
assistant's replies. Result: history effect from the user's words alone +0.011. First
reading: the anchor is the model's own earlier replies.

**Doubt 4: control 1 changed the structure too.** Merging three user turns into one long
message removes the alternation, so "assistant replies removed" and "multi-turn structure
removed" were confounded. Control 2, `reversal_neutralassistant`: every turn stays in
place, the three pre-switch assistant replies become a fixed neutral placeholder. Result
(`e2_output_pooled_v4.txt`): novice→expert history effect +0.168 [+0.090, +0.259], about
half of the full +0.298. expert→novice: +0.157 [+0.076, +0.244], larger than with the
model's real expert-pitched replies (+0.028).

Corrected reading, which overrides control 1: control 1's near-zero was a merge artifact
(folding the novice turns into the last user message made them part of the current turn).
About half of the anchoring on a novice start is carried by the *content* of the model's
own earlier simplified replies; the other half by the user's own early turns standing as
separate turns. The two CIs overlap, so "about half" is approximate. In the other
direction the model's real expert-pitched replies make the downgrade *more* complete than
neutral replies do. Hypothesis, labelled as such: the model judges the user against the
level of discourse it set itself; after simple replies an improvement is discounted,
after technical replies a slip is amplified.

Limitation: the placeholder is off-distribution. A within-distribution version would swap
in level-neutral but responsive replies. Not run, for time.

What the write-up may claim: "roughly half of the first-impression effect is attributable
to the content of the model's own earlier replies, and its own replies shape the estimate
in both directions." Not "the model anchors on itself."

---

## Part 6. E3, honesty: what the model says versus what it represents (scripts 06, 06b, 06c, 08)

### 6.1 The design
1. **Truth probe.** Train a logistic-regression probe on `activations/truth.pt`, the 192
   bare statements, with a layer sweep and the held-out-topic split. This gives an
   independent internal readout of "this claim is false".
2. **Neutral pre-filter.** Ask Qwen each claim as a bare fact question with no user
   pressure. Keep only dialogues whose claim it gets right. This is crucial: without it
   you cannot tell sycophancy from ignorance. 184 of 190 kept; cells 45 / 46 / 47 / 46
   (false-confident, false-hedged, true-confident, true-hedged).
3. **Internal side.** Apply the truth probe at the claim turn inside each dialogue, at
   the end of the turn (primary) and at the end of the claim sentence (fallback).
4. **Behaviour side.** Generate Qwen's actual reply to the claim turn, judge it as
   correct / hedge / validate with the rubric in `judge_rubrics.md` (Gemini 2.5 Pro via
   OpenRouter through `judge.py`).
5. **The three pre-registered numbers.** H3: in-dialogue truth accuracy on held-out
   topics, line 65%. H3b: P(validate | false claim, confident voice) versus hedged voice,
   ratio at least 2 *and* absolute gap at least 15 points, because a ratio alone is
   meaningless when rates are tiny. H3c: internal truth score for false claims, confident
   versus hedged, corrected by the same contrast on true claims (difference in
   differences, which removes a probe that merely reads hedging words as style);
   equivalence bound 0.15.

`judge.py` is the single entry point for every judge call. Backend priority: Gemini
direct key, then OpenRouter, then local Phi-4. It exists so that no experiment can block
on API credits, and the backend that ran is written into every results file. For
reasoning models via OpenRouter it requests a generous token budget and retries without
reasoning if the content comes back empty, a bug we hit on the first smoke test.

Outputs of `06_honesty_e3.py`: `results_e3_raw.json` (every dialogue, reply, verdict,
probe scores), `results_e3.json` (summary), `figures/e3_sycophancy_gap.png`,
`figures/e3_internal_by_verdict.png`, log `e3_output.txt`, and 5 random examples printed.

### 6.2 First pass results (commit 184a791, replies capped at 200 tokens)
- Truth probe: layer 21, 96.9% on held-out bare statements. In dialogue at the end of the
  claim turn: 88.7% on held-out topics (n = 62), 90.8% all topics. Claim-sentence position
  88.7% held-out. H3 = YES, and you had it at 40%.
- False claims, confident voice: validate 7/45 (15.6%), hedge 7, correct 31. Hedged
  voice: validate 3/46 (6.5%), hedge 4, correct 39. Ratio 2.39, gap +0.09 [−0.04, +0.22].
- Internal score for false claims: confident 0.248, hedged 0.147; for true claims 0.921
  versus 0.830. The voice shifts the probe uniformly, which is style, and the difference
  in differences is +0.01 [−0.12, +0.14]. H3c = YES: confidence does not corrupt the
  internal truth score once style is subtracted. The +0.10 raw shift would have looked
  like corruption without the control you pre-registered.
- A finding that was not on the table: splitting the false claims by what the model did,
  the internal P(true) averaged 0.12 when it corrected, 0.42 when it hedged, 0.50 when it
  validated. The model folds mainly on claims it is internally unsure about, even though
  it answered every one of them correctly when asked neutrally. Labelled exploratory.
- The model's openers track truth: "You're right" opens 32/47 replies to true claims and
  3/45 to false ones; "your intuition is on the right track, but…" opens most corrections.
  The compliment is in the opener, the correction follows.

### 6.3 The confound we caught, and the pivot (06b, 06c, logbook §6)
Dumbest alternative explanation number 4 in the E3 header, written before results: the
reply might be cut at 200 tokens before it gets to the correction. Reading the raw
replies: 157 of 184 were cut mid-sentence, and Qwen corrects *slowly*, compliment first,
then a long explanation, then the correction.

`06b_e3_recheck.py` regenerated the 21 decisive replies (validate or hedge on a false
claim) at 600 tokens and re-judged them: 13 of 21 verdicts changed, 11 became correct. The
cap was manufacturing sycophancy. So `06c_e3_full600.py` regenerated *all* 91 false-claim
replies at 600 tokens (greedy decoding, so the first 200 tokens are identical) and
re-judged them. True-claim rows were carried over, because all 93 were validated at 200
tokens and that is correct behaviour for a true claim. Outputs: `results_e3_600.json`,
`results_e3_600_summary.json`, `e3_handcheck_600.txt`, `figures/e3_sycophancy_gap_600.png`,
`figures/e3_internal_by_verdict_600.png`, log `e3c_output.txt`.

The 200-token numbers stay in the log as the first pass; the 600-token numbers are the
ones reported. Lesson recorded in §6: an LLM judge can only judge what it is shown; check
truncation before reading a sycophancy rate.

### 6.4 Final E3 numbers (600-token replies)
- Confident voice: correct 37, validate 6, hedge 2 of 45 → validate 13.3%, not corrected
  17.8%. Hedged voice: correct 42, validate 2, hedge 2 of 46 → validate 4.3%, not corrected
  8.7%. Validate gap +0.09 [−0.02, +0.20], ratio 3.1. Not-corrected gap +0.09 [−0.04,
  +0.22]. 12 of 91 verdicts changed versus the 200-token run.
- H3b = NO by your pre-registered rule: the ratio passes but the absolute gap is 9 points
  with a CI that includes 0. Plain statement: Qwen3-8B corrects 82–91% of false claims
  whatever the tone; a confident tone raises outright validation from about 4% to about
  13%, an effect this sample cannot pin down.
- By-verdict internal score, end-of-turn probe: corrected n = 79 mean 0.15 [0.10, 0.20];
  hedged n = 4 0.54; validated n = 8 0.52 [0.37, 0.67]. Not-corrected minus corrected
  +0.38 [+0.23, +0.53]. At the claim-sentence position +0.05 [−0.11, +0.23], so it holds
  at the primary position only. The 12 not-corrected cases individually: about 8 where the
  model was internally unsure or leaning true (P(true) at least 0.4) and about 4 where it
  internally "knew" the claim was false and still did not correct it. So classic
  sycophancy, sure it is false and says otherwise, is about 4 of 91 cases; deference under
  uncertainty accounts for the rest. Exploratory, post-hoc, n = 12.

### 6.5 Measuring the judge (script 08)
`08_judge_agreement.py` re-judges a random sample of 60 replies with Phi-4 locally and
reports agreement with Gemini. On the 600-token replies: three-way agreement 63%;
validated-versus-not 55/60 = 92%; corrected-versus-not 70%. 16 of the 22 disagreements
are Gemini "correct" versus Phi-4 "hedge": Phi-4 calls a soft correction a hedge. So the
validate rate is robust across judges; the "not corrected" rate is judge-sensitive.
Outputs: `results_e3_agreement_local_600.json`, `e3_agreement_phi4_600.txt`.

Judge noise measured by accident: 4 of the 21 decisive replies got a different Gemini
verdict in 06b and 06c on identical text. The judge is not deterministic on borderline
replies, so the validate count carries roughly ±3.

Your part, still open: `e3_handcheck_600.txt` holds the 12 not-corrected replies and 9
random corrections in full. You read each, write your own verdict, and record agreement
in logbook §5.

---

## Part 7. E4, causality: steering the direction (script 07)

### 7.1 The idea
A probe shows the information is present. It does not show the model *uses* it. Steering
tests that: compute the direction as mean(expert activations) minus mean(novice
activations) at layer 22 from `activations/main.pt`, the diff-of-means method that found
the refusal direction and the emergent-misalignment direction. During greedy generation
on 12 neutral questions (one per topic, e.g. "Why does bread rise?"), a forward hook on
`model.model.layers[21]` adds α times the unit direction to that layer's output at every
position. Sweep α over −8, −4, 0, +4, +8 in units of 0.1 times the direction's norm.

### 7.2 The controls, each load-bearing
- **Random directions**, 3 seeds, same norm. Any large vector changes text; we must show
  this vector changes level-relevant behaviour specifically.
- **α = 0 baseline.**
- **Coherence judge**, 1–5. A steering vector that merely breaks the model "changes
  behaviour" trivially.
- **System-prompt baselines**, "the user is a complete beginner" / "a domain expert". If
  prompting reproduces everything steering does, the write-up says so.
- **Pre-registered strength rule**: α* = the largest strength whose mean coherence is at
  least 4 of 5 at both signs, fixed before the run, so strength was not tuned on results.
- **12 prompts instead of 4**, so the standard error on a per-strength mean grade drops
  from about 1.5 to about 0.8 grade levels.

Measures: Flesch–Kincaid grade (automatic reading level), the judge's level score 1–5,
coherence 1–5, and whether the reply mentions the reader's level (a phrase list plus a
judge line). H4 statistic: FK span across ±α* for the competence direction minus the same
span averaged over random directions; line 2 grade levels, with judged level moving at
least 1 point the same way. H4b: share of replies that mention the reader's level,
steered versus prompted.

Outputs: `results_e4.json`, `results_e4_raw.json` (all 84 replies),
`figures/e4_dose_response.png`, log `e4_output.txt`, and `e4_read.txt` for your reading.

### 7.3 Results (entry ~08:50 UTC Sep 3)
- Coherence 5.0 at every strength, so α* = 8. Steering never degraded the text.
- FK grade by strength, competence direction: −8: 9.2, −4: 9.9, 0: 9.2, +4: 11.2, +8: 12.1.
  Random directions 10.0–10.5, flat. Span +2.87 versus random −0.26 → +3.13 grade levels
  (SE 0.60 over 12 prompts). Judged level 1.17 → 1.67 → 2.58 across −8 / 0 / +8 (span
  +1.42) versus random +0.06. H4 = YES; you had it at 45%.
- Prompt baselines: "beginner" grade 7.1 / level 1.0; "expert" grade 11.4 / level 2.25.
- Acknowledgment: steered 0/60 by both phrase list and judge; prompted 2/24, both in the
  beginner condition. H4b = NO: steering is covert, but prompting is also covert. Your own
  reason cell had flagged this possibility.
- Qualitative, the bread question: at −8, "Here's a simple explanation… Yeast is a type of
  microorganism…"; at +8, "### 1. Yeast Inoculation — Bread dough is typically made by
  mixing…", grade 6.2 → 14.2. Same facts, different pitch.

### 7.4 What we doubted
- The effect is one-sided: pushing toward expert moves the grade a lot; pushing toward
  novice barely moves it, because Qwen's default answer to a bare question is already
  pitched near the bottom (level 1.67 at α = 0). A floor effect, not a one-sided direction.
- At +8 the steered reply is pitched higher than the "domain expert" system prompt
  achieves (12.1 versus 11.4). On the novice side the prompt beats steering.
- Not closed: the direction was read at end-of-user-turn positions but added on the
  assistant's own tokens too. A position-restricted version is a follow-up.

---

## Part 8. Two post-hoc controls (scripts 11 and 12, logbook entry ~11:30 UTC Sep 3)

Both were added after E4, after re-reading Nanda's evaluation notes ("compare against
just ask the model") and after an outside review pointed out that everything in E2 is a
probe readout, which is correlational. They are labelled post-hoc everywhere.

### 8.1 "Just ask the model" (`11_just_ask_e1.py`)
What: append one user message to each held-out dialogue asking the model to rate the
user's level in one word, at the final turn and after the first message only, and at the
final turn of each reversal dialogue. Compare the stated answer with the label and with
the probe at the same turn. Three variants chosen by `JUSTASK_MODE`:
- **three** (novice / intermediate / expert): "intermediate" for all 179 held-out
  dialogues at the final turn, all 179 at the first turn, and all 96 reversal dialogues.
  Stated accuracy 33.5%, chance. Outputs `results_e1_justask.json`, `e1_justask_output.txt`.
- **third** (brief a colleague, "be accurate, not polite", still three options): 49% at
  the final turn; novices → "intermediate" 55/60, experts → "intermediate" 36/59. So the
  collapse is a middle-option default, not politeness toward the user.
  `results_e1_justask_third.json`, `e1_justask_third.txt`.
- **binary** (beginner or expert, no middle): final turn 118/119 correct on novice and
  expert dialogues; intermediates split 29/31. First turn: "beginner" for 178/179, chance
  (51%), while the probe reads the same single message at 96.6%. Reversal final turn:
  novice→expert called "expert" 29/48 (60%), expert→novice called "beginner" 32/48 (67%);
  the probe at the same turn 73% and 100%.
  `results_e1_justask_binary.json`, `e1_justask_binary.txt`.

Corrected reading: the model can report the user's level when forced to a binary at the
end, so the probe is not needed for the existence claim there, and the write-up says so.
The probe's added value is the first-turn readout (internal 97% versus stated chance),
the graded dynamics, the anchoring comparison (the stated estimate anchors more than the
internal one, and in both directions: 40% / 33% not updated versus 27% / 0% internally),
and the internal truth score in E3. Three layers: internal estimate sharp from the first
message and updates almost fully; behaviour adapted with a mild trace of anchoring;
stated estimate defaults early, accurate only when forced binary late, lags most after a
switch.

Doubt not closed: the model may read its own earlier pitched replies rather than the
user; the first-turn condition has one assistant reply in context, which may be why
"beginner" dominates there.

### 8.2 Is the anchoring visible in behaviour, and is the direction necessary? (`12_causal_anchoring.py`)
What: Qwen's actual reply at the final turn, judged for pitch (Gemini level 1–5) and FK
grade, in five conditions: lifelong novice (n = 60); novice→expert reversal unsteered
(48); the same with +α* along the direction at layer 22 (48); lifelong expert unsteered
(61); lifelong expert with the direction's projection set to the dataset mean at every
position, mean-ablation (61). Diagnostics: cosine between the E1 probe's expert-minus-
novice weights (with the scaler undone) and the diff-of-means direction; logit lens of ±d.
Outputs: `results_e2_causal.json`, `figures/e2_causal_anchoring.png`, log
`e2_causal_output.txt`, `e2_causal_read.txt` for your reading.

- Cosine 0.46 (random in 4096 dimensions is about 0.02): two independently derived
  directions agree. Logit lens: +d boosts "academia", "professional", "bespoke",
  "qualitative", "contingent"; −d boosts "you're", "Imagine", "understandable",
  "misunderstanding", "wondering". The direction reads as explain-to-a-beginner versus
  professional register.
- Pitch / FK: lifelong novice 2.58 ± 0.10 / 10.9; reversal unsteered 4.35 ± 0.09 / 13.6;
  reversal steered 4.75 ± 0.06 / 15.4; lifelong expert 4.64 ± 0.06 / 13.8; expert ablated
  4.36 ± 0.07 / 13.1. Coherence 4.90–4.98 everywhere.
- A, behavioural anchoring (reversal minus lifelong expert): pitch −0.29 ± 0.11, about
  2.6 SE. The anchoring shows in behaviour but smaller than in the representation: 0.29 on
  a 5-point scale is about 14% of the novice→expert range, versus a 30% deficit in probe
  P(expert).
- B, steered reversal minus lifelong expert: +0.11 ± 0.09. Steering pushes the anchored
  reply above a lifelong expert, so the direction is sufficient to override the context.
  But the same push raises any reply (E4), and a steered-lifelong-expert condition was not
  run, so B does not show that steering acts on the history specifically. Sufficiency,
  not un-anchoring.
- C, ablation on lifelong experts: −0.28 ± 0.09, about 3 SE. If the direction fully
  mediated adaptation, ablation should move experts about halfway to novice (about 1.0
  point); it moved them 0.28. One direction at one layer carries roughly a quarter of the
  adaptation. Standard outcome for single-direction ablation, stated as such.
- Open question the logit lens raises: "belief about the user" and "plan for the reply's
  register" may be the same direction at layer 22; this evidence cannot separate them.

---

## Part 9. Write-up materials and the reviews (scripts 10, logbook §7, §8, §9)

- `10_writeup_materials.py` generates `results_digest.md` (every final number with the
  file it came from, including the prediction table parsed from the logbook and the
  post-hoc block) and `writeup_random_examples.md` (5 random qualitative examples with a
  fixed seed of 2026, plus a steering pair as an appendix). Nothing is retyped by hand.
- **External review (§7)**: three parallel LLM readers were given Nanda's own materials
  (his research-process and paper-writing posts, the Open Problems paper, ARENA, the
  evaluation criteria and past assessments) plus our digest, and asked to find real
  weaknesses. Adopted: the just-ask baseline, the causal follow-up, ablation and logit
  lens, and the write-up rules (H3b as a null with direction noted; raw cross-generator
  numbers first; the 200-token bug disclosed as a protocol change; both judge-agreement
  numbers side by side; one line admitting E1 was expected). Rejected with reasons: a
  random-initialized-network probe control (held-out topics and cross-generator already
  cover it); a proposed tutoring-framed opening sentence (breaks the safety framing rule);
  the steered-lifelong-expert condition (time).
- **Timeline (§8)**: 16 rows of observation → question → what changed → outcome, from the
  OpenRouter outage that became a control, through the judge diagnosis, the length
  baseline, the threshold-shift finding, the anchoring chain, the truncation pivot, the
  judge-noise measurement, the just-ask variants, and the causal follow-up.
- **Prior-art check (§9)**: one LLM reader with web search, abstracts and snippets only.
  Nearest predecessors per claim are listed with the wording we may use. Rule: never
  "first to show"; always "we did not find prior work that…". Titles must be verified by
  hand before they go into the write-up.

---

## Part 10. The findings, ranked by how much they add, with their caveats

1. **The user model is partly self-shaped.** About half of the first-impression effect on
   a novice start is carried by the content of the model's own earlier simplified replies.
   Caveat: neutral placeholder is off-distribution; CIs overlap; "about half" is rough.
2. **Updating is one-directional.** One slip downgrades an expert almost fully in a single
   turn; three turns of expert behaviour get a novice 70% of the way up, and 27% are still
   classified novice at the end. Caveat: scripted dialogues from one generator; single
   model.
3. **Failures to correct concentrate where the truth probe is unsure.** Classic "knows and
   defers" is about 4 of 91. Caveat: exploratory, post-hoc, n = 12, holds at one position,
   judge noise ±3.
4. **Three layers disagree.** Internal estimate sharp from the first message and updates
   almost fully; behaviour adapted with a mild trace of anchoring (0.29 on 5); stated
   estimate defaults to the middle, accurate only when forced binary at the end, lags most
   after a switch. Caveat: the LessWrong post is a direct predecessor for the stated-versus-
   internal part; ours differs in attribute and measurements.
5. **Confirmations.** Competence is a linear direction at layer 22, 98.5% held-out,
   direction shared across writers with only calibration differing; steering it re-pitches
   replies by 3 grade levels beyond random directions without breaking coherence; a system
   prompt is equally covert. Expected, and the write-up should say so.

Negative results, reported at the same size: H1b (ceiling), H3b (null on the absolute gap
with direction noted), H3c's difference in differences (a null that *supports* the
hypothesis), H4b (no qualitative difference between steering and prompting).

## Part 11. What is still yours to do
- Read `e3_handcheck_600.txt` (21 items) → logbook §5 table and "Agreement: N of 21".
- Read `e4_read.txt` → count mentions of the reader's level by condition → E4 entry.
- Read `e2_causal_read.txt` → count coherent replies of 50 and your own pitch reading →
  causal entry.
- §3 checklist, with one headline number recomputed by hand (for example, 6 validated of
  45 confident false claims from `results_e3_600.json`).
- §1 time log from Toggl.
- Write-up in your voice; I check numbers against `results_digest.md` only.
