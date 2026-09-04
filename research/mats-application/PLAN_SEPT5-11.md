# Plan for the extension window (Sept 5–11, 2026)

Rules that apply to everything below: Toggl on for every active minute; every new experiment
gets a row in logbook §0 (probability, threshold, floor, reason) BEFORE it runs; every result
gets its logbook entry with the dumbest alternative explanation named. Hours spent here count
inside the 20; the +2 are for the executive summary only.

## Step 0 (Sept 5, first thing): the hour count
Reconstruct logbook §1 from Toggl if it ran, else from logbook timestamps + git commit times,
counting only active work (his rules: breaks, waiting, generic setup, pre-project reading,
form answers do not count). The number decides which tiers below happen.

## Tier 1 — do regardless of budget (≈ 3.5 h)
| # | What | Why | Cost |
|---|---|---|---|
| T1.1 | Paired bootstrap of (full-history effect − neutral-reply effect) over the same 48 n→e dialogues, and same for e→n | Gives "about half" an interval instead of two overlapping ones. If the CI includes 0, the claim softens to "consistent with"; if not, it firms up | 45 min, existing activations |
| T1.2 | Bare-statement check of the E3 lead: for the 91 false claims, take the truth probe's P(true) on the BARE statement (truth.pt / truth_lastword.pt, no dialogue, no user, nothing to plan) and split by the 600-token verdict | Tests the alternative "the end-of-turn probe reads the reply plan, not the belief". If the 12 uncorrected claims are ALSO higher on the bare probe, the belief reading survives; if not, the lead is downgraded to speculative and the write-up says so | 1 h, existing activations (needs the claim↔statement mapping from data/codex/claims.json) |
| T1.3 | Evidence-strength argument for the asymmetry, from existing data: the post-only control shows isolated post-switch turns score 1.000 (expert) and 0.000 (novice) — both saturated — so by the probe's own measure the two kinds of post-switch evidence are equally strong; write this into Claim B as the partial answer to "evidence strength vs updating rule" | Closes reviewer point 4 as far as this data allows | 20 min, writing only |
| T1.4 | Add reviewer points 1, 4, 7 to limitations and next steps | Pre-empts the objections | 30 min |
| T1.5 | Causal blind read (e2_causal_read_blind.txt, 50 replies, coherent + pitch 1–5) | Closes the one "not done" | 1 h |

## Tier 2 — if ≥ 4 h remain after Tier 1 and the write-up (≈ 3.5 h)
| # | What | Design | Pre-register | Cost |
|---|---|---|---|---|
| T2.1 | THE LINKING EXPERIMENT: does the model's estimate of the user gate what it does with a false claim? | Reuse the honesty claims. For each claim, two versions of the two pre-claim user turns: novice-style and expert-style (same rules as main; Codex on the laptop; the claim turn identical and confident-voice only, so n ≈ 90 per level). Check the manipulation with the competence probe at the turn before the claim. Generate the 600-token reply, judge (Gemini), hand-check every decisive verdict. Measure: validate / hedge / correct rate by apparent level; truth-probe P(true) at claim end by apparent level | H5: P(validate | expert-looking) vs P(validate | novice-looking). Write your probability and threshold before generating. Both directions are plausible: deference to apparent authority, or gentler (hedged) correction of novices | Codex generation ~40 min wall / 15 min active; extraction 10 min; replies ~40 min GPU; judge 15 min; analysis + figure 45 min; hand-check 30 min. ≈ 2.5–3 h active |
| T2.2 | Level-neutral but responsive replies as the placeholder | Generate three neutral replies per n→e reversal dialogue (Codex/Gemma: "answer the question helpfully in 40–90 words; do not simplify, do not use jargon"); swap in; rerun E2 | H6: history effect with responsive-neutral replies lands between the placeholder (+0.17) and full (+0.30) | ≈ 1 h active |

## Tier 3 — if ≥ 3 h remain after Tier 2 (≈ 2 h)
| # | What | Why | Cost |
|---|---|---|---|
| T3.1 | Second model size for E1 + E2 only (Qwen3-14B fits the A100 in bf16; or Qwen3-4B) | Turns "one model" into "two sizes" for the two main claims; shows whether the asymmetry sign and the anchoring gap hold. Nothing else re-run | extraction ~40 min GPU (main + reversal + postonly + neutralassistant), probe + E2 10 min, writing 30 min. ≈ 1.5 h active |

## What NOT to do
- No new experiment on E4 (steering) — it is a confirmation and adds breadth, not depth.
- No third-person / more just-ask variants.
- No new topics or generators.

## Daily shape (assuming ~3 h/day active; adjust to the real budget)
- Sept 5: hour count; T1.1, T1.2, T1.3 (pod on). Read R1D1 and SAE Equations. Pre-register H5/H6 if Tier 2 is affordable.
- Sept 6: T2.1 generation + extraction + replies (pod); T1.5 while the GPU runs.
- Sept 7: T2.1 judge, hand-check, analysis, figure; logbook entry.
- Sept 8: T2.2 (and T3.1 only if the budget allows); rewrite executive summary + form answers.
- Sept 9: rewrite the body in your voice; cut to ~2,500 words; fold in T1–T2 results and reviewer points.
- Sept 10: full number check against the digest with me; delete every guide/yellow; sharing set; Toggl screenshot; secrets check on the code folder.
- Sept 11 (IST morning): read once more with fresh eyes; submit well before 12:29 pm IST.

## Deliverables I will prepare (no hours for you)
- Scripts for T1.1, T1.2, T2.1, T2.2, T3.1 with prediction stubs in logbook §0.
- Figures for any result that changes the story.
- A regenerated digest and updated draft sections (bullets and numbers, not your prose).
