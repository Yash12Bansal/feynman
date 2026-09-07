# Experiments still to run — the list you can point me at

Written 2026-09-07. Deadline Sept 11, 11:59 pm PT = Sept 12, 12:29 pm IST. Every hour of
active work below counts inside the 20 h; fill the matching logbook §0 row (H5–H8) BEFORE the
run, in your own words. All scripts below were smoke-tested end to end on fake activations
(CPU); none has run on real data yet. Nothing here is a result until it runs.

To start one, tell me its ID ("run A", "run C with steer", "run everything in tier 1").
The pod must be on (`source pod_setup.sh`); the laptop steps need Codex logged in.

Status key: READY = script exists and smoke-tested · HUMAN = your reading time, no GPU ·
WRITING = no code, goes straight into the doc.

---

## Why these and not others (the principle)

Nanda's own words for what he scores: a **North Star** (a safety goal), a **proxy task**
("empirical feedback that stops you fooling yourself"), **method minimalism** ("prompting,
steering, probing, reading chain-of-thought" before anything fancy), **baselines** for any
method claim, and **"just ask the model"** before trusting a probe. The list below is what our
write-up is missing against that rubric, ordered by how much each one changes the story per
hour. The linking experiment (C) is the only one that adds a new claim; the rest turn claims we
already make into claims that survive a hostile reader.

---

## Tier 1 — cheap, existing activations, run first (≈ 1 h active total)

### A · Paired decomposition of the anchoring source  (T1.1) — READY
- **Question.** How much of the novice→expert anchoring is carried by the CONTENT of the model's
  own earlier replies, with an interval on the difference?
- **Why it is needed.** The draft says "about half" from two numbers with overlapping intervals
  (+0.30 full history vs +0.17 fixed placeholder). A reader who knows statistics will ask for
  the interval on the difference. The variants are the same 48 dialogues, so the right test is
  paired, and paired intervals are much tighter than the two independent ones.
- **Why Nanda cares.** "Show your work" and "truth-seeking": a claim stated with the interval it
  deserves, softened to "consistent with" if the interval includes zero.
- **Design.** Per dialogue i and variant v: h_v[i] = sign·(P_postonly[i] − P_v[i]). Paired
  bootstrap over dialogue ids of mean(h_full − h_placeholder), both directions, plus the share
  of the full effect carried by reply content (1 − h_placeholder/h_full) with its interval.
- **Decision rule.** Interval on (full − placeholder) clear of 0 → the "own replies" claim stands
  with its interval; includes 0 → reword to "consistent with about half".
- **Cost.** 15 min active, no GPU generation (activations exist).
- **Command (pod).** `PROBE_FILE=probe_e1_pooled.joblib python 17_e2_history_decomposition.py`
- **Outputs.** results_e2_history.json, figures/e2_history_decomposition.png (replaces
  e2_anchoring_source.png in the doc).
- **Dumbest way it is wrong.** Dialogues share topics (4 per topic per direction), so a
  topic-cluster bootstrap would be wider; say so if the interval is close to 0.

### B · Bare-statement check of the E3 lead  (T1.2, H7) — READY
- **Question.** Are the false claims the model fails to correct ALSO "unsure" when scored as bare
  statements, with no dialogue, no user, and nothing to plan?
- **Why it is needed.** Our most quotable E3 line ("the model defers where it is internally
  unsure", P(true) 0.5 vs 0.15) is read at the END of the claim turn, the state from which the
  reply is written. A hostile reader's first alternative: the probe is reading the reply plan
  ("I am about to agree"), not a belief about the claim. This experiment separates the two.
- **Why Nanda cares.** His doc asks for "a truth probe that generalizes well to real situations"
  and warns against probes that read the wrong thing. He also lists "compare against just
  asking the model"; here the comparison is against the claim in isolation.
- **Design.** Leave-one-topic-out truth probe at the E3 layer, so every one of the 192 bare
  statements gets an out-of-sample P(true). Split the 91 false rows (46 distinct claims; each
  claim appears in a confident and a hedged dialogue) by the 600-token verdict. Report rows AND
  claims (the claim is the honest unit), a rank-based AUC, and the correlation between bare
  and in-dialogue scores.
- **Decision rule (H7).** Bare difference (not-corrected − corrected) ≥ +0.15 with the interval
  clear of 0 → the belief reading survives. ≈ 0 while the in-dialogue split stays large → the
  lead is downgraded to "the dialogue adds something the probe reads" and the draft's sentence
  is rewritten.
- **Cost.** 20 min active.
- **Command (pod).** `python 18_e3_bare_probe_by_verdict.py`
- **Outputs.** results_e3_bare.json, figures/e3_bare_vs_dialogue_by_verdict.png.
- **Dumbest way it is wrong.** n = 12 rows / few claims, so the interval is wide either way;
  "not corrected" is a Gemini label with known run-to-run flips (use your hand-checked verdicts
  from logbook §5 if they differ).

### F · Causal blind read  (T1.5) — HUMAN, ≈ 1 h
- Read `e2_causal_read_blind.txt` (50 replies, shuffled): coherent yes/no and pitch 1–5 each.
  Key: `e2_causal_read_key.json`. Closes the one "Human read: NOT DONE" in the logbook. Every
  judge-based number in the doc then has a human check behind it.

### G · Writing-only closures  (T1.3, T1.4) — WRITING, ≈ 50 min
- T1.3: the evidence-strength answer to "is the asymmetry just stronger evidence?": isolated
  post-switch turns score 1.000 (expert) and 0.000 (novice), both saturated, so by the probe's
  own measure the two kinds of post-switch evidence are equally strong. Goes into Claim B.
- T1.4: reviewer points 1, 4, 7 (competence estimate unused in E3 → fixed by C; asymmetry vs
  evidence strength → T1.3; self-report prompt sensitivity) into limitations and next steps.

---

## Tier 2 — the experiment that adds a claim (≈ 3–4 h active)

### C · The linking experiment, E5  (T2.1, H5 / H5b / H5c) — READY
- **Question.** Does the model's estimate of the user gate what it does with a false claim?
  Same claim, same words; only who appears to be saying it changes.
- **Why it is needed.** Right now E1–E2 (the model tracks the user) and E3 (what it does with a
  false claim) never touch. A reviewer's sharpest line: "the competence estimate is never used
  for anything". C is the bridge, and it is the only experiment on this list that can add a
  headline rather than defend one.
- **Why Nanda cares.** This is his "proxy task" pattern exactly: North Star = read and control
  what a deployed model believes about its user, because those beliefs shape honesty; proxy
  task = predict and change what the model does with a false claim by manipulating only the
  apparent user. His doc's user-model paragraph asks "how else do they shape behaviour?" This
  answers it with a paired, controlled measurement.
- **Design.** 96 false claims + 48 true claims (control: does the model push back on CORRECT
  claims from novices?). For each claim, ONE confident claim turn written once and reused
  verbatim; before it, two user turns and two assistant replies in the novice register or the
  expert register (same rules as the main set). 288 dialogues. Manipulation check: the E1 probe
  at the turn before the claim must read ≥ 80% of each context as intended, or H5 is not scored.
  600-token replies, E3 rubric judge, every decisive verdict hand-checked, paired by claim.
- **Measures.**
  - H5: P(validate) and P(not corrected), expert-looking minus novice-looking, paired by claim.
  - H5b: truth-probe P(true) at the end of the claim turn, by context (does the internal truth
    estimate of the same sentence bend toward an expert-looking user?).
  - Just-ask baseline (built in, cheap): the claim turn with "one word first: is the statement
    I just made true or false?" appended. Nanda's "compare against just asking the model".
    Probe moves but stated answer does not → the belief bends silently. Both move → they agree.
    Stated moves but probe does not → verbal effect only.
  - H5c (exploratory): drop in P(expert) from the pre-claim turn to the claim turn, false vs
    true claims. A confident false claim as single-sentence downgrade evidence, E2's asymmetry
    at the scale of one turn.
  - Exploratory: does the context effect concentrate on claims the model is unsure about (bare
    P(true) from B)?
- **Decision rule.** Write your probability and threshold for H5 first (suggested line: paired
  gap of ±0.10 with the interval clear of 0). Both signs are plausible: deference to apparent
  authority, or gentler hedged correction of novices. A null with a passed manipulation check
  is a real result too: "the user model does not gate honesty at this size".
- **Cost.** Laptop: ~40 min wall, ~15 min active (Codex). Pod: extraction 5 min; replies ≈ 70
  min wall (background); judge included; analysis 5 min; hand-check 30–45 min. ≈ 2–2.5 h active.
- **Commands.**
  1. Laptop: `python 19a_generate_linking_codex.py` → `git add data && git commit -m "linking dialogues" && git push`
  2. Pod: `git pull && python 03_extract_activations.py linking && python 03_extract_activations.py linking_claimpos`
  3. Pod: `python 19_linking_e5.py generate` (resumable; saves every 10 rows)
  4. Pod: `PROBE_FILE=probe_e1_pooled.joblib python 19_linking_e5.py analyze`
  5. You: `e5_handcheck.txt` (each item shows both contexts for one claim), logbook entry.
- **Outputs.** data/linking.jsonl, results_e5_raw.json, results_e5.json, figures/e5_linking.png,
  e5_handcheck.txt.
- **Dumbest ways it is wrong.** The manipulation failed (checked); novice-context dialogues
  carry misconceptions the reply must also address, so "hedge" can mean "busy correcting
  something else" (read the hand-check file); judge noise (every decisive verdict is in the
  file); the assistant's two earlier replies are generator-written in the level's register,
  which is part of the manipulation, as in E2.

### C-steer · Causal arm of E5  (H5d) — READY, optional, run only if C finds an effect
- **Question.** If the context effect exists, is it carried by the competence direction? Steer
  ±α* (the E4 direction and strength) during the reply in both contexts.
- **Why Nanda cares.** Turns a correlation (context → behaviour) into an intervention on the
  representation, with the E4 machinery he has already seen work. "Mechanistic claims
  predicting intervention outcomes" is on his list of good proxy tasks.
- **Design.** Same dialogues, false claims only, replies regenerated with +α* (toward expert)
  and −α* (toward novice). Paired with the unsteered verdict per row.
- **Decision rule (H5d).** Steering toward expert in novice contexts moves the not-corrected
  rate in the same direction as the context did, interval clear of 0.
- **Cost.** +192 generations ≈ 50 min GPU wall, ≈ 20 min active. Command: `STEER=1 python 19_linking_e5.py generate` then `analyze`.

### C-ablate · Necessity arm of E5 — READY, optional
- **Question.** Does mean-ablating the competence direction during the reply CLOSE the gap
  between expert-looking and novice-looking contexts?
- **Why Nanda cares.** Sufficiency (steering) and necessity (ablation) are different claims;
  E4 only showed the first. The 12_causal ablation on lifelong experts removed about a quarter
  of the adaptation; here the question is whether it removes the honesty gating.
- **Cost.** +96 generations ≈ 25 min GPU wall, ≈ 10 min active. Command: `ABLATE=1 python 19_linking_e5.py generate` (can be combined: `STEER=1 ABLATE=1`).

### A1 · System-prompt baseline for E5 — READY, ≈ 30 min active  (new since the plan)
- **Question.** Does simply TELLING the model the user's level ("The user is a complete
  beginner / a domain expert") gate the false-claim behaviour the same way the implicit
  two-turn inference does?
- **Why it is needed.** Nanda: "for methodology contributions, it's crucial to compare to
  baselines", and his cheapest baseline is always the prompt. If the instruction reproduces
  the context effect, the model's inference is doing the same work as an explicit instruction.
  If it does not, the implicit user model has effects the instruction lacks (or vice versa).
  Either way the write-up needs the number next to E5's.
- **Design.** The 91 existing E3 false-claim dialogues, regenerated with each system prompt
  (E4 wording), same decoding and judge; the no-prompt verdicts already exist. Paired by row.
- **Cost.** ≈ 45 min GPU wall (background), 30 min active incl. the hand-check file.
- **Command (pod).** `python 21_e5_sysprompt_baseline.py` → results_e5_sysprompt.json,
  e5_sysprompt_handcheck.txt.

---

## Tier 2b — fixing E2's weakest control (≈ 1 h active)

### D · Level-neutral but RESPONSIVE replies  (T2.2, H6) — READY
- **Question.** Is "half of the anchoring is the content of the model's own replies" robust
  when the replacement replies are real answers rather than one repeated line?
- **Why it is needed.** The placeholder control changed two things at once: it removed the
  replies' pitch AND their content, and a repeated line is off-distribution. A reader can say
  the placeholder just confused the model. D changes one thing: every pre-switch reply is
  rewritten as a genuine 40–90-word answer that would read the same to a beginner or a
  professional.
- **Why Nanda cares.** "Minimal change to the prompt that causes a predictable change" is his
  own description of a good understanding-type proxy task, and this is the minimal version.
- **Decision rule (H6).** History effect with responsive-neutral replies lands between the
  placeholder (+0.17) and the full history (+0.30), both paired differences clear of 0.
  Manipulation check printed by 17: FK grade of the rewritten replies, n→e vs e→n gap ≈ 0.
- **Cost.** Laptop ≈ 15 min active (12 Codex calls); pod 3 min extraction + rerun A.
- **Commands.** Laptop: `python 20_generate_neutral_replies_codex.py` → commit, push.
  Pod: `git pull && python 03_extract_activations.py reversal_neutralresponsive && PROBE_FILE=probe_e1_pooled.joblib python 17_e2_history_decomposition.py`

---

## Tier 3 — breadth, only if hours remain (≈ 1.5 h active)

### E · Second model size  (T3.1, H8) — READY
- **Question.** Do the E2 asymmetry sign and the n→e anchoring gap hold at another size?
- **Why it is needed.** Every claim in the doc is about one model. One replication turns "Qwen3-8B
  does X" into "two Qwen3 sizes do X", which is the smallest step from anecdote to pattern.
- **Design.** E1 + E2 + A only, on Qwen3-14B (fits the A100 in bf16) or Qwen3-4B; outputs land in
  `runs/<tag>/` and never touch the 8B files.
- **Cost.** ≈ 40 min GPU wall for extraction, 10 min analysis, 30 min writing.
- **Command (pod).** `bash 22_second_model.sh Qwen/Qwen3-14B` (`WITH_GEMMA=1` adds the
  cross-generator test).

---

## Recommended order for the days left
1. Sept 7–8: A, B (40 min), F (1 h), predictions for H5–H7, start C step 1 on the laptop in the
   background; pod runs C steps 2–4 overnight if possible.
2. Sept 8–9: C hand-check + logbook; A1 in the background; D if time; C-steer only if C found an
   effect.
3. Sept 9–10: E only if the hour count allows; otherwise writing.
4. Sept 10–11: doc only. No new experiments after Sept 10 evening.

## What each result changes in the doc
| Run | Doc section it touches | If positive | If null |
|---|---|---|---|
| A | Claim B anchoring source | "half" gets an interval | soften to "consistent with" |
| B | Claim C lead + limitations | lead promoted from exploratory | lead demoted, alternative stated |
| C | New Claim D (linking) + exec summary | new headline: the user model gates honesty | "does not gate at 8B" + manipulation check |
| C-steer / C-ablate | Claim D causal sentence | representation carries it | context effect not via this direction |
| A1 | Claim D baseline row | instruction ≈ inference | inference ≠ instruction (interesting either way) |
| D | Claim B control | own-reply content confirmed | placeholder artefact; reword |
| E | Setup + limitations | "two sizes" | "size-specific"; report honestly |
