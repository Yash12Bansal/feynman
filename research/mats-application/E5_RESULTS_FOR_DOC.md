# What changed on Sept 10 and what goes into the doc

Three runs finished on the pod (all files on the branch, commit fae4a60 + logbook 50c3b82):
the paired anchoring decomposition (17), the bare-statement check of the E3 lead (18), and the
linking experiment E5 (19). Below: the exact sentences that change, the numbers behind them,
and a draft paragraph for the new claim. Rewrite everything in your own voice; keep the numbers.

## 1. Sentences to CHANGE in the existing draft

**Claim B (anchoring source) — soften.**
Old: "about half of the first-impression effect is carried by the content of the model's own
earlier replies."
New (facts): the paired difference between full history and the fixed placeholder is +0.13
[+0.06, +0.20] in novice→expert, so the placeholder removes 44% [23%, 64%] of the effect. But
in expert→novice the same placeholder moves the estimate toward the middle by a similar amount
(0.03 → 0.16). So the data are consistent with "about half is the model's own replies" and
equally consistent with "a repeated off-distribution line makes the model less certain about
the user". The controls do not separate content from artefact. What survives: the anchoring is
real (post-only control, writing effect 0) and it is not carried by the user's own words alone.
Files: results_e2_history.json, figures/e2_history_decomposition.png (replaces the old
anchoring-source figure).

**Claim C (E3 lead) — promote.**
Old: exploratory, n = 12, "the model validates the false claims it is internally unsure about",
with the caveat that the probe might be reading the reply plan.
New (facts): scored as BARE statements, no dialogue, out-of-fold: not-corrected claims P(true)
0.42 vs corrected 0.10, diff +0.33 [+0.13, +0.52]; the bare score alone ranks uncorrected above
corrected with AUC 0.77 (p = 0.001); claim level (9 vs 37 claims) +0.41 [+0.18, +0.65]; same
sign at the statement-last-token position (+0.27 [+0.09, +0.45]). The reply-plan alternative is
ruled out; the uncertainty is a property of the claim. Still 12 rows / 9 claims.
Files: results_e3_bare.json, figures/e3_bare_vs_dialogue_by_verdict.png.

## 2. NEW Claim D — draft paragraph (rewrite in your voice)

*Does the model's estimate of the user change what it does with a false claim?* I wrote one
confident claim turn for each of 95 false and 47 true statements and placed it, word for word,
after two user turns written either as a novice or as an expert (284 dialogues). The E1 probe
confirmed the manipulation: at the turn before the claim it read every novice-context
dialogue as novice and every expert-context dialogue as expert. The same false claim was then
validated 39% of the time for the expert-looking user and 28% for the novice-looking one, and
left uncorrected 51% versus 40%. The paired interval on the gap touches zero (+0.10
[+0.00, +0.22]; 16 vs 7 discordant pairs, p = 0.09), so I call this suggestive. Two things
around it are clear. The truth probe at the end of the claim turn reads the same false
sentence as more likely true when an expert-looking user asserts it (+0.09 [+0.04, +0.15]),
with no such shift for true claims, while a one-word "true or false?" appended to the same
turn does not move with the user (+0.05 [−0.05, +0.14]): the internal estimate bends, the
stated one does not. And the bend only matters where the model knows better: for false claims
its bare-statement probe already doubts, it fails to correct 71% of the time whoever is
asking; for claims it is sure are false, 34% for novice-looking users and 47% for
expert-looking ones. True claims were never challenged in either context (0/46 and 1/46).

Caveats to keep: validation rates here (28–39%) are far above E3's (13%) because the claim
turns presuppose the claim and ask the model to build on it, and the pool is all 96 false
claims; compare only within E5. Verdicts are Gemini labels on the first 600 tokens, as in E3;
hand-check agreement on the first 20 items: ____ (fill). H5 was not pre-registered (the
prediction cells were blank when the run started); say so in the doc.

## 3. Executive-summary material (numbers only; you write the sentence)
- The apparent user tilts what the model does with an identical false claim by about ten
  points toward deferring to apparent experts (39% vs 28% validated), suggestive not
  established; its internal truth estimate of the sentence bends by 0.09 while its stated
  one-word answer does not.
- Failures to correct a false claim track the model's own uncertainty about the claim,
  measured with no dialogue present (bare-probe AUC 0.77), more than they track the user.
- The anchoring decomposition claim is softened: content of own replies vs placeholder
  artefact is not identified.

## 4. Could-be-wrong rows to ADD
| Claim | How it could be wrong | What I checked |
|---|---|---|
| D: user gates behaviour | Judge noise; "hedge" = busy correcting the novice's earlier misconception | first 20 hand-checked (agreement ____); exact McNemar p 0.08–0.09 |
| D: probe bends with the user | End-of-turn probe reads the reply plan, not a belief | claim-position snapshot shows no shift (+0.02); so the shift arises after the sentence — consistent with either reading; stated as such |
| D: rates | Not comparable with E3 | different claim-turn wording and pool; within-E5 contrast only |
| B: "half is own replies" | Placeholder artefact | e→n shows the same-size shift toward the middle; claim softened |
| C: lead | Reply-plan reading | bare-statement split +0.33, AUC 0.77 → ruled out |

## 5. Numbers cheat-sheet (E5, from results_e5.json)
| Quantity | expert-looking | novice-looking | paired diff [95% CI] | n |
|---|---|---|---|---|
| validate (false claims) | 0.386 | 0.284 | +0.10 [+0.00, +0.22]; 16 vs 7; p 0.093 | 88 claims |
| not corrected (false) | 0.511 | 0.398 | +0.11 [+0.00, +0.23]; 18 vs 8; p 0.076 | 88 |
| challenged (true claims) | 0.000 | 0.022 | −0.02 [−0.07, +0.00] | 46 |
| probe P(true), end of turn, false | 0.455 | 0.362 | +0.09 [+0.04, +0.15] | 88 |
| probe P(true), end of turn, true | 0.793 | 0.784 | +0.01 [−0.06, +0.07] | 46 |
| probe P(true), claim sentence, false | 0.489 | 0.470 | +0.02 [−0.02, +0.05] | 88 |
| just-ask says false (false claims) | 0.648 | 0.602 | +0.05 [−0.05, +0.14] | 88 |
| not corrected, claims model doubts (bare > 0.3) | 0.71 | 0.71 | — | 14 |
| not corrected, claims model is sure of | 0.47 | 0.34 | — | 74 |
| manipulation check, read as intended | 134/134 | 134/134 | — | |
| kept / filtered / unfinished at 600 | 268 / 16 / 217 | | | |
