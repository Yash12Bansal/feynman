# Plan for the extension window (Sept 5–11, 2026)

> Runnable list with commands, decision rules and costs: **EXPERIMENTS_TODO.md** (kept current; point me at an ID to run it).

Rules that apply to everything below: Toggl on for every active minute; every new experiment
has its row in logbook §0 (H5–H8 are there with BLANK prediction cells — fill probability,
threshold and reason BEFORE the run); every result gets its logbook entry with the dumbest
alternative explanation named. Hours spent here count inside the 20; the +2 are for the
executive summary only.

Deadline: Sept 11, 11:59 pm PT = Sept 12, 12:29 pm IST.

## Step 0 (Sept 5, first thing): the hour count
Reconstruct logbook §1 from Toggl if it ran, else from logbook timestamps + git commit times,
counting only active work (his rules: breaks, waiting, generic setup, pre-project reading,
form answers do not count). The number decides which tiers below happen.

## What is already prepared (all scripts smoke-tested on fake data, commit after 18b8d38)
| Script | Runs where | Does |
|---|---|---|
| `e3_common.py` | — | shared truth-probe training (same rule as 06), leave-one-topic-out bare scores, paired bootstrap |
| `17_e2_history_decomposition.py` | pod | T1.1 + T2.2: paired history effects per reversal variant, paired differences, figure |
| `18_e3_bare_probe_by_verdict.py` | pod | T1.2: bare-statement P(true) split by the 600-token verdict, rows and claims, figure |
| `19a_generate_linking_codex.py` | laptop (Codex) | T2.1 data: fixed claim turns + novice/expert pre-claim turns → `data/linking.jsonl` |
| `19_linking_e5.py generate / analyze` | pod | T2.1: replies, judge, manipulation check, paired H5/H5b/H5c, optional steering, hand-check file, figure |
| `20_generate_neutral_replies_codex.py` | laptop (Codex) | T2.2 data: level-neutral responsive replies → `data/reversal_neutralresponsive.jsonl` |
| `22_second_model.sh <hf id>` | pod | T3.1: E1 + E2 + decomposition on a second size, outputs in `runs/<tag>/` |
Also: `03_extract_activations.py` now accepts `linking` and `linking_claimpos`; `config.py`
reads `MODEL_ID` from the environment (used by 22 only; default unchanged).

## Tier 1 — do regardless of budget (≈ 3.5 h active)
| # | What | Why | Cost | Command |
|---|---|---|---|---|
| T1.1 | Paired bootstrap of (full-history effect − placeholder effect), both directions | "About half" gets an interval. CI includes 0 → "consistent with"; clear of 0 → the claim stands with its interval | 15 min, existing activations | `PROBE_FILE=probe_e1_pooled.joblib python 17_e2_history_decomposition.py` |
| T1.2 | Bare-statement check of the E3 lead (H7): out-of-fold P(true) of the 46 false claims (91 rows), split by verdict | Tests "the end-of-turn probe reads the reply plan, not the belief". Bare split also positive → belief reading survives; ≈ 0 → downgrade the lead to speculative and say so | 20 min, existing activations | `python 18_e3_bare_probe_by_verdict.py` |
| T1.3 | Evidence-strength argument for the asymmetry, from existing data: post-only turns score 1.000 (expert) / 0.000 (novice) — both saturated — so by the probe's own measure both kinds of post-switch evidence are equally strong. Goes into Claim B | Closes reviewer point 4 as far as this data allows | 20 min, writing | — |
| T1.4 | Reviewer points 1, 4, 7 into limitations and next steps | Pre-empts the objections | 30 min | — |
| T1.5 | Causal blind read (`e2_causal_read_blind.txt`, 50 replies, coherent + pitch 1–5) | Closes the one "not done" | 1 h | key: `e2_causal_read_key.json` |

Note for T1.2: the 91 false rows are only 46 distinct claims (each claim appears in a confident
and a hedged dialogue). The script reports both units; the claim level is the honest one.

## Tier 2 — if ≥ 4 h remain after Tier 1 and the write-up (≈ 3.5–4.5 h active)
### T2.1 THE LINKING EXPERIMENT (E5): does the model's estimate of the user gate what it does with a false claim?
Design: the SAME confident false-claim turn (written once per claim, reused verbatim) after two
user turns in the novice register or the expert register. All 96 false claims + 48 true claims
(control: does the model challenge correct claims from novices?) × 2 levels = 288 dialogues.
Manipulation check (pre-registered in logbook §2 block): E1 probe at the turn before the claim
reads ≥ 80% as intended in both levels, else "manipulation failed".
Outcomes, paired by claim: H5 validate rate and not-corrected rate by apparent level; H5b truth
probe P(true) at the claim turn by level; H5c drop in P(expert) at the claim turn, false vs true
claims; exploratory: does the level effect concentrate on claims the model is unsure about (bare
P(true) from T1.2)?
Optional causal arm (`STEER=1`, +≈1.5 h GPU wall, ≈20 min active): the same replies with ±α*
along the competence direction; H5d = steering moves the not-corrected rate the way the context did.
Steps:
1. Laptop: `python 19a_generate_linking_codex.py` (24 + 12 Codex calls, ~40 min wall, ~15 min
   active) → `git add data && git commit && git push`.
2. Pod: `git pull && python 03_extract_activations.py linking && python 03_extract_activations.py linking_claimpos`
   (~5 min).
3. Pod: `python 19_linking_e5.py generate` (288 replies × 600 tokens ≈ 70 min wall; `STEER=1`
   adds 192 × 2; resumable, saves every 10 rows). Read the 5 random examples it prints.
4. Pod: `PROBE_FILE=probe_e1_pooled.joblib python 19_linking_e5.py analyze` → results_e5.json,
   figures/e5_linking.png, `e5_handcheck.txt` (every decisive verdict, paired by claim, shuffled).
5. Hand-check every item in `e5_handcheck.txt` (≈30–45 min), logbook entry.
Pre-register FIRST: H5, H5b, H5c (and H5d if STEER) in logbook §0. Both signs of H5 are plausible
(deference to apparent authority vs gentler, hedged correction of novices) — write down which one
you expect and why.

### T2.2 Level-neutral but RESPONSIVE replies (H6)
1. Laptop: `python 20_generate_neutral_replies_codex.py` (12 Codex calls) → commit, push.
2. Pod: `git pull && python 03_extract_activations.py reversal_neutralresponsive` (~3 min), then
   rerun 17. It prints the manipulation check (FK grade of the rewritten replies, n→e vs e→n gap
   should be ≈ 0) and the paired diffs full−responsive and responsive−placeholder.
≈ 1 h active.

## Tier 3 — if ≥ 3 h remain after Tier 2 (≈ 1.5 h active)
| # | What | Why | Cost | Command |
|---|---|---|---|---|
| T3.1 | Second model size for E1 + E2 + decomposition only (Qwen3-14B fits the A100 in bf16; Qwen3-4B as the small one) | "One model" → "two sizes" for the two main claims; does the asymmetry sign and the anchoring gap hold? (H8) | extraction ~40 min GPU wall, probe + E2 10 min, writing 30 min | `bash 22_second_model.sh Qwen/Qwen3-14B` (outputs in `runs/qwen3-14b/`; `WITH_GEMMA=1` adds the cross-generator test) |

## What NOT to do
- No new experiment on E4 (steering) — it is a confirmation and adds breadth, not depth.
- No third-person / more just-ask variants.
- No new topics or generators.

## Daily shape (assuming ~3 h/day active; adjust to the real budget)
- Sept 5: hour count; fill H5–H8 predictions; T1.1, T1.2 (pod on, ~40 min total); T1.3; read
  R1D1 and SAE Equations. Start 19a on the laptop in the background (Codex).
- Sept 6: T2.1 steps 2–4 (pod); T1.5 while the GPU runs; 20 on the laptop in the background.
- Sept 7: T2.1 hand-check, logbook entry; T2.2 extraction + 17 rerun; logbook entry.
- Sept 8: T3.1 only if the budget allows; rewrite executive summary + form answers.
- Sept 9: rewrite the body in your voice; cut to ~2,500 words; fold in T1–T2 results and reviewer points.
- Sept 10: full number check against the digest with me; delete every guide/yellow; sharing set;
  Toggl screenshot; secrets check on the code folder.
- Sept 11 (IST morning): read once more with fresh eyes; submit well before 12:29 pm IST.

## Deliverables I will prepare (no hours for you)
- Done: scripts above, logbook §0 stubs H5–H8, §2 pre-registration block.
- After each run: figures for any result that changes the story; a regenerated digest and updated
  draft sections (bullets and numbers, not your prose).
