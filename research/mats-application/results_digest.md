# Results digest — generated from result files by 10_writeup_materials.py

Subject model Qwen3-8B (thinking off). Generators: Codex/GPT (all sets) and Gemma-3-27B (main set). Judge: Gemini 2.5 Pro via OpenRouter (E3, E4); Phi-4 local second judge; Gemma-3-27B and Phi-4 for QC. Held-out topics: immunology, chess, statistics, networking.

## Prediction table (from logbook.md)

| # | Hypothesis | My prediction | Outcome |
|---|---|---|---|
| H1 | Linear probe decodes user competence at mid layers, generalizes to held-out topics | p: 70%, t:55%, f:33% | YES. 98.5% held-out (layer 22); chance 33, shuffled 33, length-only 46. Raw cross-generator 61–68%, but 94% with thresholds refit and 97.6% pooled. |
| H1b | Accuracy rises with turn index (evidence accumulation) | p:60%, t:+8points, f:0 | NO. Turn 0 already 96.6%; turn 3 − turn 0 = +3.4 (line was +8). |
| H1c | Explicit↔implicit probe transfer is high (shared representation, not keyword) | p:50%, t:at least 0.8 of same-set, or above 50%, f:33% absolute | YES. explicit→implicit 91.4%, implicit→explicit 96.7%; worse ÷ own-set = 0.92 (line 0.8). |
| H2 | Estimate crosses 0.5 within ≤3 turns of evidence flip | p:55%, t:within 2-3 turns, f:never crosses | YES. Crosses 0.5 within 1 turn of the switch in both directions (pooled and Codex probes). |
| H2b | Asymmetry: expert→novice updates FASTER than novice→expert | p: 29%, t:at least 1 turn earlier, f:0 turns | YES. e→n minus n→e journey fraction +0.31 [+0.16,+0.46] first switched turn, +0.26 [+0.16,+0.36] last turn. I had 29%. |
| H2c | Anchoring gap > 0.1 (first impression persists) | p: 32%, t:0.1, f:0 | YES for novice→expert (gap 0.28 [0.18,0.39]; control: history effect +0.30, writing effect 0). NO for expert→novice (0.03). I had 32%. |
| H3 | Truth probe (trained on bare statements) works in-dialogue, held-out topics ≥ 65% | p: 40%, t:65%, f:50% | YES. 88.7% in-dialogue on held-out topics (bare 96.9%), both positions. I had 40%. |
| H3b | P(validate false claim): confident voice ≥ 2x hedged voice | p: 40%, t: 2 or 15point gap | NO by my rule (600-token replies): validate 13.3% vs 4.3%, ratio 3.1, gap +0.09 [−0.02,+0.20]. The 200-token run had inflated both rates (Section 6). |
| H3c | Internal truth score is NOT corrupted by confident voice (stays low for false) | p: 25%, t: within 0.15 of hedged, f:no difference | YES. Corrected internal shift +0.01 [−0.12,+0.14]; false-claim means 0.25 / 0.15. I had 25%. |
| H4 | Steering shifts FK grade / judged level beyond random-direction control | p:45%, t:atlest 2 grade levels more, f: random | YES. +3.1 grade levels vs random (SE 0.6), judged level +1.4 vs +0.06, coherence 5/5 at all strengths. I had 45%. |
| H4b | Steering adapts covertly (no acknowledgment), unlike system-prompting | p: 22%, t: steered under 10%, prompted over 30%, f: same as prompting | NO. Steered 0/60 mention the user's level — but prompted only 2/24 (8%), below my 30% line. |

## E1 — is user competence linearly readable? (results_e1.json)

- Best layer 22 of 36: held-out-topic accuracy 98.5% per snapshot; per dialogue (final turn) 99.4% [98.3%, 100.0%], n=179 dialogues. Chance 33.3%.
- Controls at layer 22: shuffled labels 32.7%; topic probe (positive control) 100.0%; length-only classifier 46.1%.
- Layer profile: 81.2% at layer 1, 90.0% at layer 11, 97.9% at 21, 96.8% at 36.
- Held-out confusion (rows true novice/intermediate/expert): [[312, 2, 0], [1, 299, 1], [0, 10, 308]]; novice↔expert swaps 0/933; binary novice-vs-expert probe 99.7%.
- Turn curve, one probe: [0.966, 0.989, 0.972, 1.0, 1.0, 0.985, 1.0] (n per turn [179, 179, 179, 179, 118, 67, 24]); turn3−turn0 = +0.034 (H1b line +0.08).
- P(true class) by turn: novice [0.94, 0.98, 1.0, 0.98, 0.99, 0.99, 1.0]; intermediate [0.95, 0.98, 0.98, 1.0, 0.99, 1.0, 0.99]; expert [0.94, 0.96, 0.94, 0.97, 0.98, 0.97, 1.0]
- Explicit↔implicit (H1c): explicit→implicit 91.4%, implicit→explicit 96.7%, own-set 98.9% / 98.5%; min transfer ÷ own-set = 0.92 (line 0.8).
- Cross-generator at layer 22: codex→gemma 67.6%, gemma→codex 60.7%, within 98.5% / 96.4%. codex→gemma confusion [[291, 0, 0], [266, 50, 0], [3, 30, 282]]. Codex direction + Gemma-refit thresholds 94.1%. Pooled probe: 97.6% / 97.6%. Best raw-transfer layer 14.
- Figures: figures/e1_layer_profile.png, figures/e1_turn_curve.png

## E2 — does the estimate update? (results_e2.json, pooled probe)

- Consistent baselines at turn 6: novice 0.001, expert 0.983.
- novice->expert: mean P(expert) by turn [0.0, 0.0, 0.0, 0.38, 0.61, 0.7]; crossover after switch 1 turn(s) (midpoint line: 1); journey fraction turn3 +0.39 [+0.28, +0.51], turn5 +0.71 [+0.61, +0.81]; fraction of dialogues flipped [0.0, 0.0, 0.0, 0.42, 0.58, 0.73].
- expert->novice: mean P(expert) by turn [1.0, 0.99, 1.0, 0.3, 0.09, 0.03]; crossover after switch 0 turn(s) (midpoint line: 0); journey fraction turn3 +0.70 [+0.60, +0.80], turn5 +0.97 [+0.95, +0.99]; fraction of dialogues flipped [0.0, 0.0, 0.0, 0.73, 0.92, 1.0].
- H2b asymmetry (e→n minus n→e): turn3 +0.31 [+0.16, +0.46], turn5 +0.26 [+0.16, +0.36] (line +0.15, CI clear of 0).
- H2c anchoring at turn 6: novice→expert +0.28 [+0.18, +0.39]; expert→novice +0.03 [+0.01, +0.05] (line 0.1).
- Control novice->expert: full-context final 0.702 | post-switch turns only 1.000 | lifelong 0.983 → history effect +0.30 [+0.21, +0.40], writing effect -0.02 [-0.04, -0.00]; user-turns-only history effect +0.01 [+0.00, +0.02]
- Control expert->novice: full-context final 0.028 | post-switch turns only 0.000 | lifelong 0.001 → history effect +0.03 [+0.01, +0.05], writing effect -0.00 [-0.00, -0.00]; user-turns-only history effect +0.04 [+0.01, +0.08]
- Figure: figures/e2_update_curves.png

## E3 — what the model says vs what it represents (results_e3.json, results_e3_600_summary.json)

- Kept 184 of 190 dialogues (Qwen answered the claim correctly when asked neutrally; 6 dropped). Cells {'false_conf': 45, 'false_hedged': 46, 'true_conf': 47, 'true_hedged': 46}.
- Truth probe: bare statements held-out 96.9%; in-dialogue at end of claim turn 88.7% (n=62 held-out), all topics 90.8%; claim-sentence position 88.7% held-out (H3 line 65%).
- Internal score (end of turn): false/confident 0.248, false/hedged 0.147, true/confident 0.921, true/hedged 0.830; difference-in-differences +0.01 [-0.12, +0.14] (H3c bound ±0.15).
- FIRST PASS (200-token replies, superseded): validate 15.6% vs 6.5%; 157/184 replies were cut.
- FULL-LENGTH replies (600 tokens, the numbers to report): confident {'correct': 37, 'validate': 6, 'hedge': 2}, hedged {'correct': 42, 'validate': 2, 'hedge': 2}; validate 13.3% vs 4.3%, gap +0.09 [-0.02, +0.20], ratio 3.1; not corrected 17.8% vs 8.7%, gap +0.09 [-0.04, +0.22]. 12 verdicts changed vs 200 tokens.
- Internal P(true) of FALSE claims by what the model did (end-of-turn probe): corrected n=79 0.15 [0.10,0.20]; hedged n=4 0.54; validated n=8 0.52 [0.37,0.67]; not-corrected − corrected +0.38 [+0.23, +0.53]. Claim-sentence position: +0.05 [-0.11, +0.23]. (Exploratory, post-hoc.)
- Second judge (Phi-4) on 60 full-length replies: 3-way agreement 63.3%; validated-vs-not 55/60.
- Judge non-determinism: 4/21 borderline replies received different Gemini verdicts on identical text across two runs.
- Figures: figures/e3_sycophancy_gap_600.png, figures/e3_internal_by_verdict_600.png

## E4 — is the direction causal? (results_e4.json)

- α* = 8 (largest strength with coherence ≥ 4; coherence by strength {'-8': 5.0, '-4': 5.0, '0': 5.0, '4': 5.0, '8': 5.0}).
- Reading grade by strength, competence direction {-8: 9.2, -4: 9.9, 0: 9.2, 4: 11.2, 8: 12.1}; random directions {-8: 10.5, -4: 10.2, 4: 10.0, 8: 10.3}.
- H4: span steer +2.87 vs random -0.26 → +3.13 grade levels (SE 0.60 over 12 prompts; line 2). Judged level span +1.42 vs random +0.06 (line 1); level by strength {-8: 1.17, -4: 1.50, 0: 1.67, 4: 2.17, 8: 2.58}.
- Prompt baselines: beginner grade 7.1 / level 1.00; expert grade 11.4 / level 2.25.
- H4b acknowledgment of the user's level: steered 0.0% (phrase) / 0.0% (judge) of 48; prompted 4.2% / 8.3% of 24 (line: steered ≤10%, prompted ≥30%).
- Figure: figures/e4_dose_response.png

## Post-hoc controls (not pre-registered): 'just ask the model' and causal anchoring

- Just ask, three: final-turn stated accuracy 33.5% (confusion {'novice': {'intermediate': 60}, 'intermediate': {'intermediate': 60}, 'expert': {'intermediate': 59}}); first-turn 33.5% (confusion {'novice': {'intermediate': 60}, 'intermediate': {'intermediate': 60}, 'expert': {'intermediate': 59}}); reversal: stated matches current behaviour n→e 0.0% vs probe 72.9%, e→n 0.0% vs probe 100.0%.
- Just ask, binary: final-turn stated accuracy 99.2% (confusion {'novice': {'novice': 59, 'expert': 1}, 'intermediate': {'novice': 29, 'expert': 31}, 'expert': {'expert': 59}}); first-turn 51.3% (confusion {'novice': {'novice': 60}, 'intermediate': {'novice': 60}, 'expert': {'novice': 58, 'expert': 1}}); reversal: stated matches current behaviour n→e 60.4% vs probe 72.9%, e→n 66.7% vs probe 100.0%.
- Just ask, third: final-turn stated accuracy 49.2% (confusion {'novice': {'intermediate': 55, 'novice': 5}, 'intermediate': {'intermediate': 60}, 'expert': {'expert': 23, 'intermediate': 36}}); first-turn 52.0% (confusion {'novice': {'novice': 33, 'intermediate': 27}, 'intermediate': {'intermediate': 60}, 'expert': {'intermediate': 59}}); reversal: stated matches current behaviour n→e 2.1% vs probe 72.9%, e→n 2.1% vs probe 100.0%.
- Causal anchoring (judge google/gemini-2.5-pro, layer 22, α*=8; cosine probe-vs-diff-of-means 0.46): reversal n→e, unsteered: pitch 4.35±0.09, grade 13.6±0.5, coherence 4.98; reversal n→e, steered +α*: pitch 4.75±0.06, grade 15.4±0.4, coherence 4.98; lifelong expert, unsteered: pitch 4.64±0.06, grade 13.8±0.4, coherence 4.97; lifelong expert, direction ablated: pitch 4.36±0.07, grade 13.1±0.4, coherence 4.90; lifelong novice, unsteered: pitch 2.58±0.10, grade 10.9±0.3, coherence 4.97
  - [level] A behavioural anchoring (reversal − lifelong expert) -0.29 ± 0.11; B steered reversal − lifelong expert +0.11 ± 0.09; C ablation on lifelong experts -0.28 ± 0.09.
  - [fk] A behavioural anchoring (reversal − lifelong expert) -0.19 ± 0.62; B steered reversal − lifelong expert +1.60 ± 0.57; C ablation on lifelong experts -0.70 ± 0.56.
- Figure: figures/e2_causal_anchoring.png

## QC (logbook section 4)
- Length by level: Codex 33/33/37 words, Gemma 43/38/34 (opposite directions). Leaks: 0 / 2 false positives.
- Blind judge, user turns only: Gemma-27B 71% 3-way (Codex); Phi-4 52% all turns → 80% first two turns (Codex); 70% (Gemma). 0 novice↔expert swaps in every run; rank corr 0.86–0.87.
