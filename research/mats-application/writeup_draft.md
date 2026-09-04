<!-- FULL DRAFT for Yash to rewrite in his own voice. Every number is from results_*.json / logbook.md.
     Directives: {{fig:name|caption}}  {{table:key}}  {{examples}}  {{levels}} {{topics}} {{rules}} {{rubrics}} {{paras:key}}
     Lines starting with "NOTE:" are for Yash and are NOT included in the document. -->

# TITLE

NOTE: pick one, or write your own. Specific and plain beats clever.
NOTE: (a) What Qwen3-8B thinks you know: a user-competence estimate that updates one way and is partly its own doing
NOTE: (b) Do you know this? Probing the running estimate of user competence in Qwen3-8B
NOTE: (c) The model's picture of the user: sharp from the first message, slow to upgrade, half self-made

Yash Bansal · Application to MATS 12.0, Neel Nanda stream · September 2026
Hours: __ h on the project + __ h on the executive summary (Toggl screenshot in Appendix I) · Code: [link, commit __]

Epistemic status: a 20-hour project on one 8B model with synthetic dialogues. The two main results survived the controls I could think of; the third is a lead, not a result.

# Executive summary

## What problem am I trying to solve?

Chen et al. (TalkTuner, 2024) showed chat models represent who the user is: age, gender, education, income. Those are static. I asked whether Qwen3-8B also keeps a running estimate of what the user knows about the topic at hand, which can change within one conversation: does it update on evidence, drive how the model writes, and match what the model says about the user when asked? A model that decides you are a novice and then discounts your corrections is the seed of sycophancy.

Setup: Qwen3-8B, thinking off. 1,076 dialogues (12 topics × 3 competence levels) by two independent writers, GPT via Codex and Gemma-3-27B, with length, tone and topic matched and no self-labels. Linear probe on the layer-22 residual stream at the end of each user turn, trained on 8 topics, tested on 4 held-out. Gemini 2.5 Pro judge, Phi-4 second judge, my own hand-checks. 11 predictions written before any run: 8 yes, 3 no; three of my four lowest bets among the yeses.

## High-level takeaways

- **Existence was expected and is the tool.** 98.5% held-out (chance 33%, shuffled 33%, length-only 46%), same direction in both writers' dialogues.
- **Compelling evidence that the estimate updates one way.** One turn of novice behaviour drops a lifelong expert to the floor; three expert turns get a novice-start user 70% of the way up, and 27% are still classified novice. Asymmetry +0.31 [+0.16, +0.46].
- **Suggestive evidence that about half of that first impression is carried by the model's own earlier replies.** Cutting the history removes the effect (+0.30 → −0.02); replacing only the model's three pre-switch replies with a neutral line halves it (+0.17 [+0.09, +0.26]).
- **Three layers disagree.** The internal estimate is right from the first message (96.6%); replies show a smaller trace of anchoring (−0.29 on a 5-point pitch scale); asked directly, the model says "intermediate" for everyone, is right 118 of 119 only when forced to a binary at the end, is at chance on the first message, and lags the internal estimate after a switch (60% / 67% vs 73% / 100%).
- **Tentative lead (post-hoc, n = 12).** The false claims the model fails to correct are mostly ones its truth probe already scores as uncertain: P(true) 0.52 vs 0.15, +0.38 [+0.23, +0.53]. Knowing and deferring anyway is about 4 of 91 cases.

## Key experiments

{{fig:e2_update_curves|Figure 1. Frozen layer-22 probe on 96 reversal dialogues (switch at turn 4); 95% bootstrap bands.}}

Expert→novice covers 0.70 of the distance on the first switched turn and 0.97 by the last; novice→expert 0.39 and 0.71. With the history cut off, the novice-start gap (0.28 [0.18, 0.39]) vanishes: it comes from the context, not the writing.

{{fig:e2_anchoring_source|Figure 2. Final estimate's distance from the lifelong baseline, by what stays in the pre-switch history.}}

Neutralising only the model's replies cuts the novice-start gap from +0.30 to +0.17; in the other direction its real expert-pitched replies make the downgrade more complete (+0.03) than neutral ones (+0.16).

{{fig:e3_internal_by_verdict_600|Figure 3. Internal P(true) for 91 false claims, split by what the model's reply did.}}

Validation of a confident user (13.3% vs 4.3%) misses my pre-registered 15-point line (gap +0.09 [−0.02, +0.20]). Tone does not move the internal truth score once style is subtracted (+0.01 [−0.12, +0.14]); the model's own uncertainty predicts a failure to correct.

## Biggest limitations, and what I would do next

One model at one size; synthetic dialogues; off-distribution neutral-line control; E3 cells of 45 and 46 with the split resting on 12 cases; the judge changed 4 of 21 borderline verdicts on identical text. Next: a steered-lifelong-expert condition, ablation on the model's own tokens only, other sizes, real transcripts.

## What I verified by hand

30 dialogues before any GPU run; all 12 not-corrected replies plus 9 corrections (21/21 final, 18–19/21 first pass); 48 steered and prompted replies blind; ______ recomputed by hand.

# Randomly selected examples (not cherry-picked)

Five items drawn with a fixed random seed (2026) before I looked at them: two main-set dialogues (one per writer), one reversal dialogue, and two honesty dialogues with the model's full reply and the judge's verdict. The steering pair at the end is a sixth item, also random. Nothing here was edited.

{{examples}}

# Setup

## Terms I use

{{table:terms}}

## Model and data

The subject model is Qwen3-8B in bfloat16 with thinking disabled. I switched thinking off because the probe reads the model's state before it writes anything, so a think block adds nothing there, and because in the honesty experiment I need the model's actual answer to a claim rather than a long deliberation that the judge then has to interpret.

{{table:datasets}}

Three model families are kept apart on purpose. Qwen is studied. GPT (through the Codex CLI) and Gemma-3-27B write the dialogues. Gemini 2.5 Pro judges replies, with Phi-4 as a second judge. If the studied model had written its own training dialogues, its stylistic fingerprints could carry the label into the very activations I probe.

## How the dialogues were written

Every generation prompt enforced the same rules (verbatim in Appendix H): the same 12 topics and seed questions at every level; the user never states or hints at their level, background or job; every user turn is 25–60 words at every level; a neutral, curious tone; and level shown only through misconceptions, precision of terminology, the type of question asked, and how the user hedges. A phrase filter rejected dialogues that slipped (4 of 540 in the Codex set). Two hand-written exemplar dialogues on a topic not in the list were included in the prompt to show what "subtle" means. The level definitions given to the writers are in Appendix H.

## Quality control before any GPU time

I ran three checks on the dialogues before extracting a single activation, because a probe will happily learn a shortcut if one exists.

Length. User turns differ in length by level, and in opposite directions in the two sets: Codex experts write about 3 more words per turn than novices, Gemma novices about 8 more than experts. I kept both sets, added a length-only classifier to E1 as a baseline, and noted that a probe which transfers between the two writers cannot be reading length.

{{table:t4a}}

Self-labels. The phrase filter found 0 leaks in the Codex set and 2 flags in the Gemma set, both false positives on inspection ("years of" fund data; "intermediate nodes" in networking).

Blind judges. A different-family model read only the user turns of 120 random dialogues and guessed the level. My first run scored 37%, far below the 85–95% I had planned for. The confusion matrix showed that every error in every run was a one-step shift upward, novice↔expert swaps were at most 1 in 120, and rank correlation between true and judged level was 0.86–0.87. Showing the judge only the first two user turns raised agreement to 80%: the novice personas learn from the assistant inside the dialogue. So the label describes where a persona starts, and I pre-registered before E1 that the probe's confusions should sit between neighbouring levels.

{{table:t4d}}

## Activations, probes, steering, judges

- Activations: the residual stream at the last token of the prompt (the state from which the model would begin its reply), at all 37 layers, one forward pass per user turn. 2,748 snapshots from the Codex set and 2,846 from the Gemma set.
- Competence probe: logistic regression on standardized features (C = 0.1), trained on 8 topics and tested on the 4 held-out ones (immunology, chess, statistics, networking; 179 dialogues, 933 snapshots). The layer was chosen by held-out accuracy. Downstream experiments use a probe trained on both writers' dialogues, under a rule fixed in advance: use it if it is within a few points of within-writer accuracy. It was within 1 point.
- Truth probe: the same recipe on 192 bare true/false statements (8 + 8 per topic), layer 21, applied inside dialogues at the end of the claim turn and, as a pre-registered fallback, at the end of the claim sentence.
- Steering: direction = mean(expert) − mean(novice) at layer 22 from the Codex main set, added at every position through a forward hook on that layer's output, at strengths ±4 and ±8 in units of 0.1‖d‖, with three random unit directions of equal norm as controls and 12 neutral questions as prompts.
- Judges: Gemini 2.5 Pro via OpenRouter for reply verdicts and pitch scores; Phi-4 locally as a second judge; Gemma-27B and Phi-4 for the QC judges. Rubrics verbatim in Appendix H.

# Results

## Claim A. About half of the first-impression effect is carried by the content of the model's own earlier replies

My prediction for anchoring (H2c) was 32% with a line of 0.1. The question was whether a first impression survives three turns of opposite evidence. At the matched turn 6, novice-start users end 0.28 [0.18, 0.39] below a lifelong expert; expert-start users end 0.03 [0.01, 0.05] above a lifelong novice. In plain terms: after three turns of clearly expert behaviour, 27% of novice-start users are still classified as novices; after three turns of novice behaviour, 0% of expert-start users are still classified as experts.

The first alternative explanation was the writer, not the model: perhaps the post-switch expert turns were written weakly. I fed the model only the post-switch turns. In isolation they score 1.000 against 0.983 for lifelong experts, so the history effect is +0.30 [+0.21, +0.40] and the writing effect is −0.02 [−0.04, −0.00]. The anchoring is caused by what is in the context.

The second was that the probe is saturated (baselines 0.001 and 0.983), so a mean of 0.39 may mean "39% of dialogues have flipped" rather than "every dialogue is at 0.39". Per-dialogue flip fractions on the three switched turns are 0.42, 0.58, 0.73 for novice→expert and 0.73, 0.92, 1.00 for expert→novice. The curves are mostly per-dialogue flips, and I describe them that way.

Then the question I did not plan: the history holds both the user's early turns and the model's own replies to them, which were pitched at a novice. My first control removed the assistant replies by merging the user's three novice turns into one message. It gave +0.01 and looked like a clean answer. It was a merge artifact: folding the turns into the current message made them part of the current turn. The second control kept every turn in place and replaced the three pre-switch replies with "Thanks, that's a good question. Let's keep going." The history effect fell from +0.30 [+0.21, +0.40] to +0.17 [+0.09, +0.26]. In the expert→novice direction the same substitution moved the effect from +0.03 to +0.16 [+0.08, +0.24]: the model's real expert-pitched replies make the downgrade more complete, not less.

What I take from this, stated at the strength I think it deserves: roughly half of the first-impression effect is attributable to the content of the model's own earlier replies, and its own replies shape the estimate in both directions. The two confidence intervals overlap, so "half" is approximate. One hypothesis, which I have not tested: the model judges the user against the level of discourse it set itself, so after simple replies an improvement is discounted and after technical replies a slip is amplified. I did not find prior work that separates the model's own outputs from the user's words as sources of a user representation; "Old Habits Die Hard" (2026) reports that a model's own outputs trap its later hidden states in general. Caveats: the placeholder reply is off-distribution, and this is a probe readout at one layer.

## Claim B. Updating is one-directional

My prediction (H2b) was 29% that expert→novice updates faster, by at least 0.15 in journey fraction with a confidence interval clear of zero. Journey fraction measures how far the estimate has travelled from its own pre-switch value toward the lifelong baseline of the new level at the same turn, which removes the confound that one direction has less distance to cover. Expert→novice minus novice→expert is +0.31 [+0.16, +0.46] on the first switched turn and +0.26 [+0.16, +0.36] on the last. The probe trained on Codex only gives +0.23 and +0.22, both clear of zero. Both directions cross 0.5 within one turn of the switch: expert→novice on the first switched turn, novice→expert one turn later.

This fits something I had already seen in E1. Novices in the natural dialogues learn as they go, and blind judges call their later turns "intermediate", but the probe keeps calling them novices at every turn (P(novice) ≈ 0.99 at the last turn). Upgrading takes strong, sustained evidence; downgrading takes one slip.

Caveats: the reversal dialogues are scripted and come from one writer, and the assistant's post-switch replies are in the context in both directions, so they cannot create the asymmetry on their own. I did not find prior work reporting this asymmetry for a user model. Schubert et al. (ICML 2024) report asymmetric belief updating for rewards in in-context learning, and the LessWrong post "Do LLMs Change Their Minds About Their Users… and Know It?" reports that user-attribute probes update within a turn, without a directional asymmetry.

## Claim C. Three layers disagree: internal estimate, behaviour, stated estimate

This section is post-hoc. It exists because Neel's Common Mistakes list says to compare against "just ask the model", and because an outside reader pointed out that everything in E2 is a probe readout.

Internal. The probe reads the level from the first user message alone at 96.6%, and at 99.4% [98.3, 100] per dialogue at the final turn.

Behaviour. I took the model's actual reply at the final turn and had the judge score its pitch from 1 (total beginner) to 5 (domain expert). Lifelong novices get 2.58 ± 0.10, lifelong experts 4.64 ± 0.06, and novice→expert reversals 4.35 ± 0.09. The anchoring is visible in behaviour, −0.29 ± 0.11, but it is about 14% of the novice-to-expert range against a 30% deficit in the probe. Adding the competence direction to the reversal replies pushes them above lifelong experts (+0.11 ± 0.09), which shows sufficiency, not un-anchoring, because the same push raises any reply and I did not run a steered-lifelong-expert condition. Setting the direction's projection to the dataset mean on lifelong experts lowers their pitch by 0.28 ± 0.09, about a quarter of the adaptation, which is the usual outcome for one direction at one layer. Coherence stayed at 4.90–4.98 in every condition.

{{fig:e2_causal_anchoring|Figure 4. The model's actual final-turn reply in five conditions, judged pitch (primary) and reading grade (secondary); n = 60 / 48 / 48 / 61 / 61; error bars are standard errors.}}

Stated. I appended one user message asking the model to rate the user's level in one word. With three options it said "intermediate" for all 179 held-out dialogues at the final turn, all 179 after the first message, and all 96 reversal dialogues: 33.5%, chance. Asking it to brief a colleague and "be accurate, not polite" gave 49%, so the collapse is a middle-option default, not politeness. Forcing a binary choice at the final turn gave 118 of 119 correct on novice and expert dialogues, so the model can report the level at the end of a conversation and the probe is not needed for that. On the first message the forced binary said "beginner" 178 of 179 times, chance, while the probe reads the same message at 96.6%. After a switch, the stated estimate matches the user's current behaviour 60% of the time (novice→expert) and 67% (expert→novice), against 73% and 100% for the probe.

So the internal estimate is sharp from the first message and updates almost fully; the replies adapt with a small trace of anchoring; the stated estimate defaults early, is accurate only when forced binary late, and lags most after a switch. The LessWrong post above is the direct predecessor for the stated-versus-internal gap, on demographics with a 3B model; this is the same pattern on competence, with the first-message contrast and the forced-binary recovery added. One caveat: the first-message condition has one assistant reply in context, so the model may be reading its own reply rather than the user.

## Claim D (exploratory, post-hoc). Failures to correct a false claim concentrate where the truth probe is unsure

This was meant to be the headline and turned into a lead. In each honesty dialogue the user asserts a claim in their third message, in a confident voice ("Since X, I figure…") or a hedged one ("I might be wrong, but I think X…"), and the model replies. Only claims the model answers correctly when asked neutrally are kept (184 of 190), so a validated false claim is deference, not ignorance.

The truth probe, trained on bare statements, reads true from false inside dialogues on held-out topics at 88.7% (n = 62; 90.8% on all topics) against 96.9% on bare statements. My prediction (H3) was 40% with a line of 65%.

At 600-token replies, the confident voice got 37 corrections, 6 validations and 2 hedges out of 45; the hedged voice 42, 2 and 2 out of 46. Validation is 13.3% vs 4.3%, ratio 3.1, gap +0.09 [−0.02, +0.20]. My rule (H3b) required both a ratio of 2 and a gap of 15 points, so this is a no, with the direction noted: Qwen3-8B corrects 82–91% of false claims whatever the tone, and a confident tone raises outright validation from about 4% to about 13%, an effect this sample cannot pin down.

The internal truth score is not corrupted by tone. The confident voice raises the probe's P(true) by 0.10 on false claims, but by 0.09 on true claims too, so the difference-in-differences is +0.01 [−0.12, +0.14] against a pre-registered bound of 0.15 (H3c, which I had at 25%). Without the true-claim contrast the raw shift would have looked like corruption.

The finding I did not plan is in the split by what the model did. Among false claims, internal P(true) averages 0.15 [0.10, 0.20] when the model corrected (n = 79), 0.54 when it hedged (n = 4) and 0.52 [0.37, 0.67] when it validated (n = 8); not-corrected minus corrected is +0.38 [+0.23, +0.53]. Of the 12 uncorrected cases, about 8 had P(true) at or above 0.4 and about 4 had the model internally sure the claim was false. So "knows it is false and defers", the strict sense of sycophancy, is about 4 of 91; the rest is deference under uncertainty. This holds at the end-of-turn position only; at the claim-sentence position the same contrast is +0.05 [−0.11, +0.23].

{{fig:e3_sycophancy_gap_600|Figure 5. Share of false claims validated and not corrected, by the user's voice, 600-token replies, Gemini 2.5 Pro judge (n = 45 confident, 46 hedged).}}

Judge and protocol. The first pass capped replies at 200 tokens; 157 of 184 were cut mid-sentence, and Qwen corrects slowly: a compliment, a long explanation, then the correction. Regenerating the 21 decisive replies at 600 tokens changed 13 verdicts, so I regenerated all 91 false-claim replies; validation went from 15.6% / 6.5% to 13.3% / 4.3%. Phi-4 as a second judge agreed with Gemini on 63% of three-way verdicts and 55 of 60 validated-versus-not decisions. Gemini itself gave different verdicts to 4 of 21 identical borderline replies across two runs, so the validate count carries about ±3. I read all 12 uncorrected replies and 9 corrections myself: 21 of 21 final agreement, 18–19 of 21 before comparing with the judge. This extends the internal-origins-of-sycophancy line ("When Truth Is Overridden", AAAI 2026; "Dissociating the Internal Representations of Sycophancy", 2026) with a per-case split; it rests on 12 cases.

## Confirmation 1. User competence is a linear direction at mid layers

I expected this to work and it did; it is the tool the rest of the project uses. At layer 22 the probe reaches 98.5% on held-out topics per snapshot and 99.4% [98.3, 100] per dialogue at the final turn. Shuffled labels give 32.7%, a topic probe on the same activations 100%, and a classifier that sees only word counts 46.1%. Accuracy is 81% at layer 1, about 90% from layer 11 and about 98% from layer 21 on. Of 933 held-out snapshots, none is a novice↔expert swap; the 14 errors are between neighbouring levels.

{{fig:e1_layer_profile|Figure 6. Probe accuracy by layer on held-out topics, with the shuffled-label and topic controls and the length-only baseline.}}

Two method points. First, a probe trained on one writer's dialogues and tested on the other's scores only 67.6% and 60.7%. The confusion matrix shows the entire drop in one cell: Gemma's intermediates are called novices. Keeping the Codex probe's direction and refitting only its thresholds on Gemma gives 94.1%, and a probe trained on both writers gives 97.6% on each. The direction transfers; the calibration does not. Second, a probe trained on dialogues where the user states their level, tested on dialogues where they do not, gets 91.4% (96.7% the other way), 0.92 of own-set accuracy against a line of 0.8: told and shown competence land on one representation. My prediction that accuracy would rise with turn index (H1b) was a no: the first message already gives 96.6%, and turn 3 minus turn 0 is +3.4 points against a line of +8, a ceiling I had pre-registered after the QC read.

## Confirmation 2. The direction is causal for pitch; prompting is equally covert

With the pre-registered strength rule, the largest strength whose coherence stayed at or above 4 of 5 at both signs, coherence was 5.0 at every strength and α* = 8. Reading grade of the reply moves from 9.2 at −8 to 12.1 at +8 along the competence direction, while three random directions of equal norm stay flat at 10.0–10.5: a span of +3.13 grade levels over random (SE 0.60 over 12 prompts; my line was 2). The judge's pitch score moves 1.17 → 1.67 → 2.58 across −8 / 0 / +8, against +0.06 for random directions. System prompts give grade 7.1 for "the user is a complete beginner" and 11.4 for "a domain expert". The effect is one-sided because the default reply to a bare question is already pitched near the bottom.

{{fig:e4_dose_response|Figure 7. Reading grade of replies to 12 neutral questions by steering strength, competence direction versus the mean of three random directions of equal norm; dashed lines are the system-prompt baselines.}}

My prediction (H4b, 22%) was that steering would adapt covertly while prompting would announce the assumption. Steering is covert: none of the 48 steered replies mentions the reader's level by either the phrase list or the judge. But prompting is nearly as covert: 2 of 24 by the rubric, or 3 of 24 if I count one expert-prompt reply that calls the model itself "a domain expert", which is the prompt leaking into the model's self-description. No qualitative difference to claim. One observation from my own read of the replies: beginner-prompted replies open with "let me explain in a simple way" and the like, and so do some −8 replies. Counted on the full replies, such framing phrases appear in 10 of 12 beginner-prompted replies, 5 of 12 at −8, 4 of 12 at −4, 2 of 12 at 0, 0 of 12 at +4 and +8, 0 of 12 expert-prompted, and 1–3 of 12 for random directions at every strength. The direction carries the model's "I am explaining simply" framing along with the pitch, without ever naming the reader.

# How these results could be wrong, and what I checked

{{table:tkit}}

# Three things that went wrong

The blind judge scored 37%. I had planned for 85–95% agreement between an outside judge and the labels, and the first Phi-4 run gave 36.7%. Instead of regenerating the data I added a confusion matrix and printed the raw judge outputs, and found that every error was a one-step upward shift and that a first-two-turns run reached 80%. The personas were learning inside the dialogues. I kept the data and wrote down, before E1, what the probe's confusions should look like if that was the explanation. They did.

The 200-token cap manufactured sycophancy. I had listed "reply cut before the correction" as an alternative explanation before seeing results, and reading the raw replies showed 157 of 184 cut mid-sentence. Re-running 21 decisive replies at 600 tokens flipped 13 verdicts. I regenerated all 91 false-claim replies and report the before and after.

The first anchoring-source control gave a clean, wrong answer. Removing the assistant replies by merging the user's turns gave a history effect of +0.01, which read as "the model anchors on itself". The merge changed the structure of the dialogue too. The placeholder control, which keeps every turn in place, gave the real answer of about half.

# What I verified myself, and how

- I read 30 dialogues, 10 per level, before any activation was extracted, and recorded the verdicts in the logbook.
- I read every one of the 12 false-claim replies the judge marked as not corrected, plus 9 it marked as corrected, together with the user's message each one answered. Final agreement 21 of 21. The judge's label was visible in the file and I changed 2–3 of my verdicts after comparing, so first-pass agreement is 18–19 of 21. I also checked by hand that all 14 distinct claims are false.
- I read 48 steered and prompted replies with the judge's labels hidden: all 48 coherent; 0 of 24 steered and 3 of 24 prompted mention the reader's level (judge: 0 and 2). The framing-phrase observation above came from this read and was then counted on the full replies.
- I recomputed ______ by hand from the result file. NOTE: fill in, e.g. "6 validated of 45 confident false claims from results_e3_600.json".
- Every experiment has a prediction written before it ran, a logbook entry with the dumbest alternative explanation named, and a 17-row timeline of observation → question → change → outcome (Appendix B).
- Not done: a human read of the 50 replies in the behavioural anchoring experiment. The judge's coherence scores (4.90–4.98) are the only coherence check there.

# How I used the agent, and what stayed mine

NOTE: this must match what actually happened; correct anything that does not.

I used Claude Code throughout. The agent wrote the scripts, the figures, the first drafts of the logbook entries and the literature snippets, and it ran three outside-review passes over Neel's own materials to find weaknesses. I ran the experiments on the GPU pod, read the outputs, and decided what happened next. The predictions, thresholds and floors in the prediction table are mine, as are the decisions to keep the data after the 37% judge result, to regenerate all replies at 600 tokens, to add each control in the anchoring chain, and to skip the causal hand-read for time. The hand-checks above are mine. The agent worked under rules I set at the start: never change a parameter silently, name the dumbest alternative explanation after every result, print five random examples for every dataset or judged set, and never write the executive summary or the form answers.

# Negative results

- H1b: accuracy does not rise with turn index. The first message already gives 96.6%; turn 3 minus turn 0 is +3.4 points against a line of +8.
- H3b: a confident voice does not double validation by my rule. Gap +0.09 [−0.02, +0.20]; the ratio (3.1) passes, the absolute-gap guard does not.
- H3c is a null that supports the hypothesis: tone does not corrupt the internal truth score once style is subtracted (+0.01 [−0.12, +0.14]).
- H4b: no qualitative difference between steering and prompting on acknowledging the user's level (0 of 48 vs 2 of 24).
- Raw cross-writer transfer is 61–68% before the threshold analysis explains it.
- The by-verdict split is absent at the claim-sentence position (+0.05 [−0.11, +0.23]).
- The merged-turns control (+0.01) was an artifact and is superseded.

# Limitations

- One model at one size. Nothing here is known to hold elsewhere.
- Synthetic dialogues from two LLM writers with scripted personas; real users differ.
- The neutral-line control is off-distribution, and the two confidence intervals behind "about half" overlap.
- The probe is saturated, so the update curves are mostly per-dialogue flips.
- E3 cells are 45 and 46; the split rests on 12 cases and one probe position; the judge is non-deterministic at the boundary.
- Steering adds the direction on the model's own tokens too; no position-restricted version; no steered-lifelong-expert condition, so the steering result is sufficiency only.
- The pooled probe could in principle hold two writer-specific rules side by side; one linear boundary makes that unlikely and the direction alone gets 94%, but it is not closed.
- The prior-art check used abstracts and snippets; titles were verified by hand before citing.

# What I would do next

- Run the steered-lifelong-expert condition so the steering comparison tests un-anchoring rather than sufficiency.
- Localize the self-anchor: ablate the direction only on the model's own tokens during the reversal, or replace its replies with level-neutral but responsive text.
- Repeat E2 across sizes and families (Qwen3 1.7B–32B, Llama, Gemma): does the asymmetry sign hold, and does anchoring shrink with scale?
- Real transcripts (WildChat, LMSYS) where users reveal expertise: does the probe's estimate predict the complexity of the reply?
- Scale the sycophancy-by-uncertainty split to hundreds of cases and test whether steering along the truth direction reduces validation only in the uncertain bin.

# Appendix

## A. Pre-registered predictions and outcomes (written before any experiment ran)

{{table:pred}}

## B. Observation → question → change → outcome

{{table:t8}}

## C. Quality-control record

{{paras:p4b}}

{{paras:p4c}}

Decision written before E1 ran:

{{paras:p4e}}

## D. Hand-checks

E3: every false-claim reply the judge labelled validate or hedge at 600 tokens (12, the entire "not corrected" count) plus 9 random corrections; 14 distinct claims, each checked false by hand. Final agreement 21 of 21; the judge's label was visible in the file and 2–3 verdicts were changed after comparing, so first-pass agreement is 18–19 of 21.

{{table:t5}}

First-pass disagreements: ______ NOTE: which items and your first labels.

E4, 48 replies read with judge labels hidden: coherent 48 of 48; mentions the reader's level: steered 0 of 24 (judge 0, phrase list 0), prompted 3 of 24 (judge 2, phrase list 1). The third is the expert-prompt reply to the stocks question, "As a domain expert, I can provide a nuanced analysis": the model calling itself the expert, which the rubric does not count, but a visible leak of the system prompt.

## E. Pivot: the 200-token reply cap (logbook entry)

{{paras:p6}}

## F. External review against Neel's own materials (logbook entry)

{{paras:p7}}

## G. Prior-art check

Method: one LLM reader with web search, two to three queries per claim, abstracts and snippets only. Titles were verified by hand before they went into this document. NOTE: verify each title yourself before submitting.

{{table:t9}}

## H. Prompts and parameters, verbatim

Level definitions given to the writers:

{{levels}}

Topics and seed questions (held-out for every probe: immunology, chess, statistics, networking):

{{topics}}

Hard rules in every generation prompt:

{{rules}}

Judge rubrics:

{{rubrics}}

Parameters:

- Subject model Qwen/Qwen3-8B, bfloat16, thinking disabled; activations at the last prompt token, all 37 hidden states, one forward pass per user turn.
- Competence probe: StandardScaler + LogisticRegression(C = 0.1, max_iter = 2000), trained on 8 topics; layer chosen by held-out accuracy (22); downstream probe trained on both writers. Truth probe: same recipe on 192 bare statements, layer 21.
- E2: 96 reversal dialogues, 6 user turns, switch at turn 4; baselines from main-set dialogues with at least 6 user turns at turn 6; 2,000 bootstrap resamples over dialogues.
- E3: neutral pre-filter; greedy replies, 600 tokens (first pass 200); judge Gemini 2.5 Pro via OpenRouter with low reasoning effort; Phi-4 second judge on 60 items.
- E4: direction = mean(expert) − mean(novice) at layer 22 from the Codex main set; forward hook on the layer-22 output, added at every position; α ∈ {−8, −4, 0, 4, 8} × 0.1‖d‖; 3 random unit directions of equal norm; 12 prompts; α* rule fixed before the run; Flesch–Kincaid grade, judge (level, coherence, mentions_level), phrase list.
- Behavioural anchoring: five conditions (n = 60 / 48 / 48 / 61 / 61); mean-ablation sets the projection on the unit direction to the dataset mean at every position; judge Gemini 2.5 Pro.

## I. Time log

NOTE: Toggl screenshot here, plus the session table from logbook §1 (start, end, hours, what). State the project total and the executive-summary hours separately.

## J. Code and data

NOTE: link to the repository folder research/mats-application at commit __, after a secrets check. Scripts 01–14, results_*.json, figures/, logbook.md, judge_rubrics.md.
