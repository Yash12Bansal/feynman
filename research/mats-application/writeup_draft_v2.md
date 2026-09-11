<!-- DRAFT v2 (Sept 10) for Yash to rewrite in his own voice. Shorter, story order, plain words.
     Every number is from results_*.json / logbook.md / E5_RESULTS_FOR_DOC.md.
     Directives: {{fig:name|caption}}  {{table:key}}  {{examples2}}  {{levels}} {{topics}} {{rules}} {{rubrics}}
     Lines starting with "NOTE:" are for Yash and are NOT included in the document. -->

TITLE: Qwen3-8B keeps a readable estimate of how expert you are: it anchors on first impressions, shapes the reply, and is not what the model says when asked

Yash Bansal · Application to MATS 12.0, Neel Nanda stream · September 2026
Hours: __ h on the project + __ h on the executive summary (time log in Appendix D) · Code and data: Appendix E

Epistemic status: a 20-hour project on one 8B model with synthetic dialogues. The two main results survived every control I could think of. The honesty link is new and partly suggestive, and I say which parts.

# Executive summary

## What problem am I trying to solve?

Does a chat model form an opinion about how much you know, update it as the conversation goes on, act on it, and report it when asked? That opinion could decide whether your false claim gets corrected, or whether you get talked down to. Chen et al. (TalkTuner, 2024) showed that models represent fixed facts about the user such as age. I asked about a fact that changes inside one conversation: how much the user knows.

Setup: Qwen3-8B, thinking off; 1,076 synthetic dialogues on 12 topics at three competence levels from two LLM writers, matched for length, tone and topic, no self-labels; a linear probe on layer 22, trained on 8 topics and tested on 4 it never saw: 98.5% (chance 33%, shuffled labels 33%, word counts alone 46%); Gemini 2.5 Pro judge, Phi-4 second judge, hand-checks. Eleven predictions written before any run: 7 yes, 1 yes in one direction only, 3 no.

## High-level takeaways

- **The estimate updates one way.** One turn of novice behaviour drops a lifelong expert to the floor. Three turns of expert behaviour get a novice-start user 70% of the way up, and 27% are still classified as novices. Asymmetry +0.31 [+0.16, +0.46].
- **The first impression lives in the history, not in the user's own words.** Cut the pre-switch turns and the gap vanishes (+0.30 → −0.02). Whether the model's own earlier replies or the multi-turn structure carries it, my controls cannot say.
- **What the model says is not what it represents.** Asked directly it calls every user "intermediate" (chance); forced to a binary at the end it is right 118 of 119; on the first message it is at chance, the probe at 96.6%.
- **The estimate is causal for how the model pitches its answer.** Adding the direction while the model writes moves the reading grade by +3.1 levels beyond random directions, coherence intact.
- **Failures to correct a false claim track the model's own doubt more than the user.** The false claims it lets pass are the ones its truth probe already doubts as bare statements, no dialogue (AUC 0.77). After two expert-looking turns the same false claim reads as more likely true (+0.09 [+0.04, +0.15]; none for true claims) and passes more often (39% vs 28%; the interval touches zero); the one-word "true or false?" answer does not move.

## Key experiments

{{fig:e2_update_curves|Figure 1. Frozen layer-22 probe read at every turn of 96 scripted dialogues whose user switches level at turn 4; 95% bootstrap bands.}}

Expert→novice covers 0.70 of the distance on the first switched turn and 0.97 by the last; novice→expert 0.39 and 0.71.

{{fig:e5_linking|Figure 2. The same false claim after novice-looking or expert-looking turns (88 claims, paired). Left: what the reply did. Right: truth-probe P(true) at the end of the claim turn.}}

The probe confirmed the manipulation (134 of 134 read as intended). Behaviour tilts ten points toward deferring to apparent experts (p = 0.09); the internal estimate moves clearly; the stated answer does not.

{{fig:e3_bare_vs_dialogue_by_verdict|Figure 3. 91 false claims from the honesty experiment, split by what the reply did. Left: truth probe inside the dialogue. Right: the same claims scored as bare statements, out of sample.}}

The false claims the model failed to correct are the ones its truth probe already doubted in isolation (0.42 vs 0.10, +0.33 [+0.13, +0.52]). "Knows it is false and defers anyway" is rare; deference under uncertainty is the rule.

## Limitations and next steps

One model at one size; synthetic dialogues; the anchoring's content-versus-structure split is not identified; the honesty split rests on 12 cases; the linking behaviour effect has p = 0.09 and was not pre-registered; the judge flipped 4 of 21 borderline verdicts on identical text. Next: a level-neutral responsive-reply control, other sizes, steering during the reply, real transcripts.

## What I verified by hand

30 dialogues before any GPU run; every uncorrected honesty reply plus 9 corrections (21/21 final, 18–19/21 first pass); 48 steered and prompted replies. Not yet: the linking verdicts.

# Randomly selected examples (not cherry-picked)

{{examples2}}

# The setup, in plain words

## Terms I use

{{table:terms2}}

## The model and the data

The model is Qwen3-8B with thinking off: the probe reads the model's state before it writes anything, so a think block adds nothing there, and in the honesty experiments I need the model's actual answer to a claim rather than a long private deliberation a judge then has to interpret.

{{table:datasets}}

Three model families are kept apart on purpose. Qwen is studied. GPT (through the Codex CLI) and Gemma-3-27B write the dialogues. Gemini 2.5 Pro judges, Phi-4 second-judges. If the studied model had written its own dialogues, its stylistic fingerprints could carry the label into the activations I probe.

## How the dialogues were written

Every generation prompt enforced the same rules (verbatim in Appendix C): the same 12 topics and seed questions at every level; the user never states or hints at their level, background or job; every user turn is 25–60 words at every level; a neutral tone; level shown only through misconceptions, precision of terms, the kind of question asked, and hedging. A phrase filter for self-labels rejected 4 of the 540 Codex dialogues at merge (536 kept) and flagged 2 of the 540 Gemma ones, both false alarms on inspection. Two hand-written example dialogues on a topic not in the list showed the writers what "subtle" means.

## Checks before any GPU time

A probe will learn a shortcut if one exists, so I checked the data first. User turns differ in length by level in opposite directions for the two writers (Codex experts about 3 words longer than novices, Gemma novices about 8 words longer than experts), so I kept both sets and added a word-count-only classifier as a baseline. Self-labels: none in the final Codex file, none in the Gemma file once the 2 flags were checked by hand. A blind judge reading only the user turns of 120 random dialogues guessed the level at 37% on my first run, far below the 85–95% I had planned for. The confusion matrix showed every error was a one-step upward shift, and showing the judge only the first two turns raised agreement to 80%: the novice personas learn from the assistant inside the dialogue. So the label describes where a persona starts, and I wrote down before E1 that the probe's confusions should sit between neighbouring levels. They did.

## Probes, steering, judges

- Activations: the residual stream at the last token of the prompt, all 37 layers, one forward pass per user turn (2,748 snapshots from the Codex set, 2,846 from Gemma's).
- Competence probe: logistic regression on standardized features (C = 0.1), trained on 8 topics, tested on the 4 held-out ones (179 dialogues, 933 snapshots); layer chosen by held-out accuracy (22). Downstream experiments use a probe trained on both writers' dialogues, under a rule fixed in advance (it was within 1 point of within-writer accuracy).
- Truth probe: same recipe on 192 bare true/false statements, layer 21; refit leaving one topic out at a time for the bare-statement check, so every statement is scored out of sample.
- Steering: mean(expert) − mean(novice) at layer 22, added at every position through a forward hook, strengths ±4 and ±8 in units of 0.1‖d‖, three random directions of equal norm as controls.
- Judges: Gemini 2.5 Pro via OpenRouter for verdicts and pitch scores; Phi-4 as second judge; rubrics in Appendix C. Replies are greedy and capped at 600 tokens.

# Part 1. Can the estimate be read at all?

I expected yes, and it is the tool the rest of the project uses. At layer 22 the probe reaches 98.5% on held-out topics per snapshot and 99.4% [98.3, 100] per dialogue at the final turn. Shuffled labels give 32.7%; a topic probe on the same activations gives 100%, so the activations are rich; word counts alone give 46.1%. Of 933 held-out snapshots none is a novice↔expert swap; the 14 errors sit between neighbouring levels, as predicted from the blind-judge result.

Two things I learned on the way. A probe trained on one writer's dialogues and tested on the other's scores only 67.6% and 60.7%, with the whole drop in one cell: Gemma's intermediates are called novices. Keeping the direction and refitting only the thresholds gives 94.1%, and a probe trained on both writers gives 97.6% on each. The direction is shared; the calibration is not. And a probe trained on dialogues where the user states their level, tested where they never do, gets 91.4%: being told and being shown land on one representation. My prediction that accuracy would rise with turn index was wrong. The first message already gives 96.6%; there is no room to rise.

{{fig:e1_layer_profile|Figure 4. Probe accuracy by layer on held-out topics, with the shuffled-label and topic controls and the word-count baseline.}}

# Part 2. How does the estimate change when the user changes?

## It updates one way

I wrote 96 six-turn dialogues where the user behaves as one level for three turns and as the other for the next three, and read the frozen probe at every turn (Figure 1). Both directions cross 0.5 within one turn of the switch, but at different speeds. I measure speed as journey fraction: how far the estimate has moved from its pre-switch value toward where a consistent user of the new level sits at the same turn. Expert→novice minus novice→expert is +0.31 [+0.16, +0.46] on the first switched turn and +0.26 [+0.16, +0.36] on the last; a probe trained on one writer only gives +0.23 and +0.22. I had this at 29% before the run. One slip downgrades an apparent expert almost completely; three turns of expert behaviour get a novice-start user 70% of the way up.

The probe is saturated (consistent dialogues sit at 0.001 and 0.983), so a mean of 0.39 could mean "39% of dialogues have flipped". Per-dialogue flip fractions on the three switched turns are 0.42, 0.58, 0.73 for novice→expert and 0.73, 0.92, 1.00 for expert→novice, so that is the right reading. Could the asymmetry just be stronger evidence in one direction? In isolation the post-switch novice turns score 0.000 and the post-switch expert turns 1.000, the probe's floor and ceiling, so by the probe's own measure the two kinds of evidence are equally loud. That is as far as this data goes. It fits Part 1: novices in the natural dialogues learn as they go and blind judges call their later turns "intermediate", but the probe keeps calling them novices at every turn. Upgrading takes sustained evidence; downgrading takes one mistake.

## The first impression persists, and lives in the history

At the matched turn 6, novice-start users end 0.28 [0.18, 0.39] below a lifelong expert; expert-start users end 0.03 [0.01, 0.05] above a lifelong novice. After three turns of clearly expert behaviour, 27% of novice-start users are still classified as novices; after three turns of novice behaviour, 0% of expert-start users are still experts.

Was the writer to blame, with weak post-switch expert turns? Fed to the model alone they score 1.000 against 0.983 for lifelong experts: history effect +0.30 [+0.21, +0.40], writing effect −0.02. The anchor is what sits in the context.

Which part? The history holds the user's novice turns and the model's own novice-pitched replies. Replacing those three replies with a fixed neutral line cut the history effect to +0.17 [+0.09, +0.26], a paired difference of +0.13 [+0.06, +0.20] over the same 48 dialogues. That read as "about half is the model's own replies", and my first draft said so. But the same substitution in the other direction moved the estimate toward the middle by a similar amount (0.03 → 0.16): either the model's replies carry part of the anchor, or a repeated off-distribution line just makes it less sure about the user. My controls cannot tell. What survives: the anchoring is real, it is not carried by the user's own words alone (merging the pre-switch user turns into one message leaves +0.01, though that changes the structure too), and the content-versus-structure split is not identified. Level-neutral but responsive replies would settle it; they are in the next-steps list.

{{fig:e2_history_decomposition|Figure 5. History effect on the final estimate by what stays in the pre-switch history, paired over the same 48 dialogues per direction.}}

# Part 3. Does the model say what it represents?

This section exists because Neel's Common Mistakes list says to compare against "just ask the model", and because everything in Part 2 is a probe readout.

Asked. One appended user message asks the model to rate the user's level in one word. With three options it said "intermediate" for all 179 held-out dialogues at the final turn, all 179 after the first message, and all 96 reversal dialogues: chance. Asking it to brief a colleague and "be accurate, not polite" gave 49%, so this is a middle-option default, not politeness. Forced to a binary at the final turn it was right 118 of 119 times, so the model can report the level at the end and no probe is needed for that. On the first message the forced binary said "beginner" 178 of 179 times, chance, while the probe reads the same message at 96.6%. After a switch, the stated estimate matched the user's current behaviour 60% and 67% of the time, against 73% and 100% for the probe.

Behaviour. The judge scored the model's actual final-turn reply for pitch from 1 (total beginner) to 5 (domain expert). Lifelong novices get 2.58 ± 0.10, lifelong experts 4.64 ± 0.06, novice→expert reversals 4.35 ± 0.09: the anchoring shows in behaviour (−0.29 ± 0.11) but small next to the probe's deficit. Adding the competence direction while the model writes pushes the reversal replies above lifelong experts (+0.11 ± 0.09); removing it from lifelong experts lowers their pitch by 0.28 ± 0.09, about a quarter of the adaptation; coherence stayed at 4.9–5.0. On 12 neutral questions, steering moves the reading grade by +3.1 levels beyond random directions (SE 0.60; my line was 2), and the judge finds no mention of the reader's level in any of the 48 steered replies (12 prompts × 4 strengths); my own read of the 24 strongest found none either. But a system prompt stating the level is equally covert (judge 2 of 24, my read 3 of 24), so my prediction of a qualitative difference was wrong.

So the internal estimate is sharp from the first message and updates almost fully; the replies adapt with a small trace of anchoring; the stated estimate defaults early, is accurate only when forced late, and lags most after a switch. The LessWrong post "Do LLMs Change Their Minds About Their Users… and Know It?" (2025) is the predecessor for the stated-versus-internal gap, on demographics with a 3B model.

{{fig:e2_causal_anchoring|Figure 6. The model's actual final-turn reply in five conditions, judged pitch (primary) and reading grade (secondary); error bars are standard errors.}}

# Part 4. Does the estimate change what the model does with a false claim?

## First attempt: tone of voice

In each honesty dialogue the user asserts a claim in their third message, confidently ("Since X, I figure…") or hedged ("I might be wrong, but I think X…"), and the model replies. Only claims the model gets right when asked neutrally are kept (184 of 190), so a validated false claim is deference, not ignorance. The truth probe reads true from false inside these dialogues at 88.7% on held-out topics.

Qwen3-8B corrects most false claims whatever the tone: validation is 13.3% for the confident voice and 4.3% for the hedged one, a gap of +0.09 [−0.02, +0.20] that misses my 15-point line. The internal truth score is not corrupted by tone once style is subtracted: the confident voice raises P(true) by 0.10 on false claims and by 0.09 on true ones, difference +0.01 [−0.12, +0.14].

The interesting part was unplanned. Splitting the 91 false claims by what the reply did, internal P(true) is 0.15 [0.10, 0.20] when the model corrected (n = 79) and 0.52 [0.37, 0.67] when it validated (n = 8), 0.54 when it hedged (n = 4): not corrected minus corrected +0.38 [+0.23, +0.53]. The obvious objection: the probe is read at the end of the turn, the state the reply is written from, so it might be reading "I am about to agree" rather than a belief. So I scored the same claims as bare statements, no dialogue, with a probe that never saw their topic. The split is still there: 0.42 for the uncorrected claims against 0.10, +0.33 [+0.13, +0.52], and the bare score alone ranks uncorrected above corrected with AUC 0.77 (Figure 3). The uncertainty belongs to the claim, not to the reply. "Knows it is false and defers anyway", the strict sense of sycophancy, is about 4 of 91 cases; the rest is deference where the model was already unsure.

## Second attempt: who is asking

None of that used the competence estimate. To link the two halves I wrote one confident claim turn for each of 95 false and 47 true statements and placed it, word for word, after two user turns written either as a novice or as an expert, with the assistant's two replies in the same register (284 dialogues; before the run: 0 self-labels, identical third turns, pre-claim turns at reading grade 10 versus 17 at equal length). The E1 probe confirmed the manipulation at the turn before the claim: 134 of 134 novice-context dialogues read as novice, 134 of 134 expert-context as expert. This experiment was not pre-registered; the prediction cells were blank when it ran, and I say so rather than fill them in afterwards.

Behaviour (Figure 2, left). The same false claim was validated 39% of the time for the expert-looking user and 28% for the novice-looking one, and left uncorrected 51% versus 40%. Paired by claim, the gap is +0.10 [+0.00, +0.22]; 16 claims were validated only in the expert context against 7 only in the novice context, exact test p = 0.09. Suggestive. True claims were never challenged in either context (0 of 46 and 1 of 46): the model does not distrust novices; if anything it indulges experts.

Internal (Figure 2, right). The truth probe at the end of the claim turn reads the same false sentence as more likely true when an expert-looking user asserts it: 0.455 against 0.362, paired +0.09 [+0.04, +0.15]. For true claims there is no shift (+0.01). At the claim sentence itself, before the follow-up question, there is also no shift (+0.02), so the bend appears between the claim and the reply.

Stated. Appending "one word first: is the statement I just made true or false?" to the claim turn, the model says "false" 65% of the time in the expert context and 60% in the novice context, +0.05 [−0.05, +0.14]. It does not move with the user, while the probe does. And it is far below the near-100% these same claims got when asked neutrally with no dialogue: the confident presupposition alone costs about 40 points of stated accuracy, for everyone.

Where the user effect lives. For claims the model already doubts in isolation (bare P(true) > 0.3, n = 14) it fails to correct 71% of the time in both contexts; for claims it is sure are false (n = 74), 34% for novice-looking users and 47% for expert-looking ones. The model's own uncertainty dominates; the apparent user matters only where the model knows better.

Two caveats that travel with this. Validation rates here (28–39%) are far above the honesty experiment's (13%) because these claim turns presuppose the claim and ask the model to build on it, and the pool is all 96 false claims rather than 46; only the within-experiment contrast is meaningful. And verdicts are Gemini labels on the first 600 tokens, as in the honesty experiment, but unlike there I have not yet hand-checked them.

# How these results could be wrong, and what I checked

{{table:tkit2}}

# Three things that went wrong

The blind judge scored 37% where I had planned for 85–95%. Instead of regenerating the data I added a confusion matrix and printed the raw outputs: every error was a one-step upward shift, and a first-two-turns run reached 80%. The personas were learning inside the dialogues. I kept the data and wrote down, before E1, what the probe's confusions should look like if that was the reason.

The 200-token reply cap manufactured sycophancy. I had listed "reply cut before the correction" as an alternative before seeing results, and the raw replies showed 157 of 184 cut mid-sentence; Qwen corrects slowly, with a compliment, a long explanation, then the correction. Re-running 21 decisive replies at 600 tokens flipped 13 verdicts, so I regenerated all 91 (validation 15.6% → 13.3%, 6.5% → 4.3%).

The anchoring-source controls gave two clean, wrong answers. Merging the user's turns to remove the assistant's replies gave +0.01 and read as "the model anchors on itself"; it was a merge artefact. The fixed placeholder gave "about half", which went into my first draft; the paired re-analysis on the last day showed the placeholder moves estimates toward the middle in both directions. Both are reported above at the strength they deserve.

# What I verified myself, and how

- 30 dialogues, 10 per level, read before any activation was extracted; verdicts in the logbook.
- Every one of the 12 false-claim replies the judge marked as not corrected, plus 9 marked corrected, with the user's message each answered. Final agreement 21 of 21; the judge's label was visible and I changed 2–3 verdicts after comparing, so first-pass agreement is 18–19 of 21. All 14 distinct claims checked false by hand.
- 48 replies, the 24 steered at ±8 and the 24 system-prompted, read for coherence and for any mention of the reader's level: all coherent; 0 of 24 steered and 3 of 24 prompted mention it (judge: 0 of 24 and 2 of 24).- Every experiment except the linking one has a prediction written before it ran; every experiment has a logbook entry naming the dumbest alternative explanation.
- Not done: a human read of the 50 replies in the behavioural anchoring experiment, and a hand-check of the linking verdicts (e5_handcheck.txt is prepared: 62 claims, both contexts).

# How I used the agent, and what stayed mine

I used Claude Code throughout. What the agent did: wrote the scripts and the figures, proposed candidate controls and a first reading of each result, drafted the logbook entries, drafted this document from the result files and the logbook, and ran review passes over Neel's own materials to find weaknesses in the work. What was mine: the question and its framing; every prediction in Appendix A, with its probability, threshold and reason, written before the run; the decision on which proposed controls and experiments ran, including choosing the linking experiment over four cheaper alternatives in the final window; running the dialogue generation on my laptop and every experiment on the GPU pod; reading the raw data and replies, and every hand-check listed above; and the decisions on what this document claims and at what strength. The agent worked under rules I fixed at the start: never change a parameter silently, name the dumbest alternative explanation after every result, and print five random examples for every dataset or judged set.

# Negative results

- Accuracy does not rise with turn index (H1b): the first message already gives 96.6%.
- A confident voice does not double validation by my rule (H3b): gap +0.09 [−0.02, +0.20].
- Tone does not corrupt the internal truth score once style is subtracted (H3c): +0.01 [−0.12, +0.14].
- Steering is not more covert than prompting (H4b): judge 0 of 48 steered replies versus 2 of 24 prompted.
- A confident claim costs an expert-looking user a little competence whether true or false (H5c): −0.05 vs −0.04.
- The by-verdict split is absent at the claim-sentence position inside the dialogue (+0.05 [−0.11, +0.23]), though present for bare statements.

# Limitations

- One model at one size; synthetic dialogues from two LLM writers with scripted personas.
- The content-versus-structure split of the anchoring is not identified (placeholder artefact).
- The probe is saturated, so the update curves are mostly per-dialogue flips.
- The honesty split rests on 12 cases and 9 distinct claims; the linking effect on behaviour has p = 0.09; the judge re-labelled 4 of 21 identical borderline replies across runs.
- The linking experiment was not pre-registered, and its validation rates are not comparable with the honesty experiment's.
- Steering adds the direction on the model's own tokens too; the steering result is sufficiency only.
- Prior work: asymmetric belief updating is reported for rewards in in-context learning ("In-context learning agents are asymmetric belief updaters", Schubert et al., ICML 2024); stated-versus-internal user models for demographics ("Do LLMs Change Their Minds About Their Users… and Know It?", LessWrong, 2025); "When Truth Is Overridden: Uncovering the Internal Origins of Sycophancy in LLMs" (AAAI 2026) is the nearest to Part 4. I did not find the user-model asymmetry, the bare-statement split, or the same-claim two-context design in prior work, but my search used abstracts only.

# What I would do next

- Replace the placeholder with level-neutral but responsive replies, which decides whether the model anchors on the content of its own explanations (the data generator is written).
- Steer the competence direction during the linking replies: if pushing toward "expert" in novice contexts raises validation the way the context did, the representation carries the tilt.
- Repeat Parts 1–2 across sizes (Qwen3 4B–32B) and families: does the asymmetry sign hold, and does anchoring shrink with scale?
- Real transcripts where users reveal expertise: does the probe's estimate predict the pitch of the reply and the fate of the user's mistakes?

# Appendix

## A. Pre-registered predictions and outcomes

Rows H1–H4b were written before any experiment ran. H5–H8 were added on Sept 4 with blank prediction cells; the cells were still blank when E5 ran, so it is recorded as not pre-registered. H7 had its threshold and floor fixed before its run but no probability.

{{table:pred}}

## B. Hand-checks

Honesty experiment: every false-claim reply the judge labelled validate or hedge at 600 tokens (12) plus 9 random corrections; 14 distinct claims, each checked false by hand. Final agreement 21 of 21; first pass 18–19 of 21. I did not record which items I changed, so I report the range rather than an exact count. The hand-check file prints the judge's label in each item's header, so the read was not blind.

Steering: 48 replies read, the 24 steered at ±8 and the 24 system-prompted; coherent 48 of 48; mentions the reader's level: steered 0 of 24, prompted 3 of 24 (judge 2 of 24). The third is an expert-prompt reply that calls the model itself "a domain expert": a visible leak of the system prompt.

Linking experiment: not hand-checked. e5_handcheck.txt lists all 62 not-corrected claims with both replies; the judge's label is printed in each header, so a future read would not be blind either.

## C. Prompts and parameters, verbatim

Level definitions given to the writers:

{{levels}}

Topics and seed questions (held-out for every probe: immunology, chess, statistics, networking):

{{topics}}

Hard rules in every generation prompt:

{{rules}}

Judge prompts (the blind-judge prompt used for QC is embedded in 02_qc_dialogues.py):

{{rubrics}}

Parameters:

- Subject model Qwen/Qwen3-8B, bfloat16, thinking disabled; activations at the last prompt token, all 37 hidden states, one forward pass per user turn.
- Competence probe: StandardScaler + LogisticRegression(C = 0.1, max_iter = 2000), trained on 8 topics; layer chosen by held-out accuracy (22); downstream probe trained on both writers. Truth probe: same recipe on 192 bare statements, layer 21; leave-one-topic-out refits for the bare-statement check.
- Reversal experiment: 96 dialogues, 6 user turns, switch at turn 4; baselines from main-set dialogues with at least 6 user turns at turn 6; 2,000 bootstrap resamples over dialogues; paired resampling over dialogue ids for the history decomposition.
- Honesty experiment: neutral pre-filter; greedy replies, 600 tokens (first pass 200); judge Gemini 2.5 Pro via OpenRouter with low reasoning effort; Phi-4 second judge on 60 items.
- Linking experiment: 142 claims × 2 contexts; claim turn written once per claim and reused verbatim; two pre-claim user turns and two assistant replies per context in the level's register; same pre-filter, decoding and judge as the honesty experiment; one-word just-ask variant appended to the claim turn; paired bootstrap over claims and exact McNemar tests on discordant pairs.
- Steering: direction = mean(expert) − mean(novice) at layer 22 from the Codex main set; forward hook on the layer-22 output, added at every position; α ∈ {−8, −4, 0, 4, 8} × 0.1‖d‖; 3 random unit directions of equal norm; 12 prompts; α* rule fixed before the run; Flesch–Kincaid grade, judge (level, coherence, mentions_level), phrase list.
- Behavioural anchoring: five conditions (n = 60 / 48 / 48 / 61 / 61); mean-ablation sets the projection on the unit direction to the dataset mean at every position.

## D. Time log

Sessions, from the commit history and the logbook timeline. The extension-window work (Sept 7–10) is inside the project total.

{{table:timelog}}

Hours: __ h on the project (limit 20) + __ h on the executive summary (limit 2). Time tracked in Toggl.

▢ Toggl screenshot here.

## E. Code and data

Repository github.com/Yash12Bansal/feynman, folder research/mats-application, branch claude/neel-nanda-research-pzo08q. All code, data and result files were final at commit 4b12aba; later commits change only this document, its build script, and one line of the logbook (the first-pass disagreement note). No API key or credential is stored in the folder (.env and logs are git-ignored).

▢ Public link: __

- Pipeline, in run order. 01c_generate_codex.py (dialogues via the Codex CLI) and 01b_generate_local.py (the Gemma-3-27B writer); 01_generate_dialogues.py is the OpenRouter version, not used for the final sets. 02_qc_dialogues.py: length audit, self-label filter, blind judge with confusion matrix. 03_extract_activations.py: residual stream at the last prompt token, all layers. 04_probe_e1.py: E1 probes, layer sweep, shuffled-label, topic and word-count controls, cross-writer transfer. 05_dynamics_e2.py: E2 update curves, journey fractions, anchoring, post-only and history controls. 11_just_ask_e1.py: the stated estimate (three-way, binary, colleague-brief). 12_causal_anchoring.py: behavioural anchoring, steering and mean-ablation on final-turn replies. 07_steering_e4.py: dose-response steering on 12 neutral prompts with random-direction controls. 06_honesty_e3.py, 06b_e3_recheck.py, 06c_e3_full600.py: E3, its follow-ups, and the 600-token regeneration. 08_judge_agreement.py: Phi-4 second judge. 17_e2_history_decomposition.py: paired anchoring decomposition. 18_e3_bare_probe_by_verdict.py: bare-statement out-of-fold check. 19a_generate_linking_codex.py and 19_linking_e5.py: the linking dataset and experiment. Written but not run: 20 (responsive neutral replies), 21 (system-prompt baseline), 22 (second model).
- Shared code: config.py (topics, levels, model id, paths), judge.py (OpenRouter judge calls), e3_common.py (truth probe, leave-one-topic-out scoring, paired bootstrap), fewshot.py, pod_setup.sh, 16_build_writeup_draft.js (builds this document from writeup_draft_v2.md and writeup_content.json).
- Data: data/main.jsonl, explicit.jsonl, reversal.jsonl, truth.jsonl, honesty.jsonl, linking.jsonl; data/codex/ holds the per-topic generator outputs and claims.json. The Gemma-written main set (data_gemma/) is in the repository.
- Results: one results_eN.json family per experiment (raw rows and summary), with the printed analysis in e1_output.txt to e5_output.txt; figures/ holds every figure in this document.
- Records: logbook.md (section 0 predictions, section 2 every run with its dumbest alternative, section 5 hand-checks, section 8 the observation-to-change timeline), judge_rubrics.md, e3_handcheck_600.txt, e4_read.txt, e5_handcheck.txt, EXPERIMENTS_TODO.md (the experiments I chose not to run and why).
