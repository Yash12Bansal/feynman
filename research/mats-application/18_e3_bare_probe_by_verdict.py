"""T1.2 — does the E3 lead survive when there is no dialogue at all?

The exploratory E3 finding: false claims the model FAILS to correct (validate/hedge at
600 tokens, n=12 rows) sit at truth-probe P(true) ≈ 0.5 at the end of the claim turn,
while corrected ones sit at ≈ 0.15 (difference +0.38 [+0.23, +0.53]). Reading offered in
the draft: "the model defers where it is internally unsure".

Dumbest alternative: the end-of-turn snapshot is the state from which the reply is
written, so the probe may be reading the REPLY PLAN ("I am about to agree") rather
than a belief about the claim. The two are confounded at that position.

Test: score the SAME claims as BARE statements — no dialogue, no user, nothing to
plan — with the truth probe, out-of-fold (leave-one-topic-out, so every statement is
predicted by a probe that never saw its topic), and split by the 600-token verdict.
  * If the uncorrected claims are ALSO higher on the bare probe, the belief reading
    survives (the uncertainty is about the claim itself).
  * If the bare split is ≈ 0 while the in-dialogue split stays large, the lead is
    downgraded: the in-dialogue probe reads something the dialogue adds.
Unit of analysis: rows (91, as in E3) AND distinct claims (46 — each false claim
appears in a confident and a hedged dialogue; the claim is the honest unit).

Pre-registered: logbook section 0, H7. Run on the pod (needs activations/truth.pt,
truth_lastword.pt, results_e3_600.json, results_e3_raw.json).
Writes results_e3_bare.json, figures/e3_bare_vs_dialogue_by_verdict.png
"""
import json
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import spearmanr, mannwhitneyu
from config import FIG_DIR, COLORS
from e3_common import train_truth_probe, oof_bare_p_true, boot

rng = np.random.default_rng(0)
raw = json.load(open("results_e3_raw.json")); L_e3 = raw["truth_probe_layer"]
d600 = json.load(open("results_e3_600.json"))
rows = [r for r in d600["results"] if not r["filtered"]]
false_ = [r for r in rows if not r["claim_true"]]
true_ = [r for r in rows if r["claim_true"]]
print(f"E3 rows: {len(false_)} false ({len({r['claim'] for r in false_})} distinct claims), {len(true_)} true; "
      f"E3 end-of-turn truth-probe layer {L_e3}")

# ---- bare-statement P(true), out of fold, two positions ---------------------------
# end-of-template position = the position E3's primary probe used (truth.pt); the
# statement-last-token position (truth_lastword.pt) is the pre-registered H3 fallback.
positions = {}
oof, accs = oof_bare_p_true("truth", L_e3)
positions["end_of_template"] = {"layer": L_e3, "p": oof, "loto_acc_by_topic": accs}
try:
    _, L_lw, a_lw = train_truth_probe("truth_lastword")           # same layer rule as 06
    oof2, accs2 = oof_bare_p_true("truth_lastword", L_lw)
    positions["statement_last_token"] = {"layer": L_lw, "p": oof2, "loto_acc_by_topic": accs2}
except FileNotFoundError:
    print("no truth_lastword.pt — statement-last-token position skipped")
for k, v in positions.items():
    print(f"bare probe @ {k} (layer {v['layer']}): leave-one-topic-out accuracy "
          f"{np.mean(list(v['loto_acc_by_topic'].values())):.3f} (per topic "
          f"{ {t: round(a, 2) for t, a in v['loto_acc_by_topic'].items()} })")

NOT = lambda r: r["verdict_600"] != "correct"
res = {"n_false_rows": len(false_), "n_false_claims": len({r["claim"] for r in false_}),
       "verdicts_600": {v: sum(r["verdict_600"] == v for r in false_) for v in ("correct", "hedge", "validate")},
       "positions": {}}
for pos, P in positions.items():
    p = P["p"]
    miss = [r["claim"] for r in false_ if r["claim"] not in p]
    assert not miss, f"{len(miss)} claims have no bare statement: {miss[:2]}"
    # --- row level (comparable to the E3 numbers) ---
    bare_nc = np.array([p[r["claim"]] for r in false_ if NOT(r)])
    bare_c = np.array([p[r["claim"]] for r in false_ if not NOT(r)])
    dia_key = "probe_p_true" if pos == "end_of_template" else "probe_p_true_claimpos"
    dia_nc = np.array([r[dia_key] for r in false_ if NOT(r) and r.get(dia_key) is not None])
    dia_c = np.array([r[dia_key] for r in false_ if not NOT(r) and r.get(dia_key) is not None])
    row = {"bare_not_corrected": boot(lambda a: a.mean(), bare_nc), "bare_corrected": boot(lambda a: a.mean(), bare_c),
           "bare_diff_nc_minus_c": boot(lambda a, b: a.mean() - b.mean(), bare_nc, bare_c),
           "dialogue_not_corrected": boot(lambda a: a.mean(), dia_nc), "dialogue_corrected": boot(lambda a: a.mean(), dia_c),
           "dialogue_diff_nc_minus_c": boot(lambda a, b: a.mean() - b.mean(), dia_nc, dia_c),
           "n": {"not_corrected": int(len(bare_nc)), "corrected": int(len(bare_c))}}
    # rank-based: how well does the bare score alone predict "not corrected"?
    u = mannwhitneyu(bare_nc, bare_c, alternative="greater")
    row["bare_auc_not_corrected"] = float(u.statistic / (len(bare_nc) * len(bare_c)))
    row["bare_auc_p_one_sided"] = float(u.pvalue)
    allb = np.array([p[r["claim"]] for r in false_ if r.get(dia_key) is not None])
    alld = np.array([r[dia_key] for r in false_ if r.get(dia_key) is not None])
    row["spearman_bare_vs_dialogue_all_false_rows"] = float(spearmanr(allb, alld).correlation)
    # --- claim level (46 distinct false claims; "ever not corrected" = either voice) ---
    by_claim = {}
    for r in false_:
        by_claim.setdefault(r["claim"], []).append(NOT(r))
    c_nc = np.array([p[c] for c, v in by_claim.items() if any(v)])
    c_c = np.array([p[c] for c, v in by_claim.items() if not any(v)])
    row["claim_level"] = {"n_ever_not_corrected": int(len(c_nc)), "n_always_corrected": int(len(c_c)),
                          "bare_ever_nc": boot(lambda a: a.mean(), c_nc), "bare_always_c": boot(lambda a: a.mean(), c_c),
                          "bare_diff": boot(lambda a, b: a.mean() - b.mean(), c_nc, c_c)}
    # reference: true claims on the bare probe (should be high) and false claims overall
    row["reference_bare_true_claims_mean"] = float(np.mean([p[r["claim"]] for r in true_]))
    row["reference_bare_false_claims_mean"] = float(np.mean([p[r["claim"]] for r in false_]))
    res["positions"][pos] = row
    b, dd = row["bare_diff_nc_minus_c"], row["dialogue_diff_nc_minus_c"]
    cl = row["claim_level"]["bare_diff"]
    print(f"\n[{pos}] not corrected (n={len(bare_nc)}) vs corrected (n={len(bare_c)}):"
          f"\n  in-dialogue P(true): {row['dialogue_not_corrected'][0]:.2f} vs {row['dialogue_corrected'][0]:.2f}"
          f"  diff {dd[0]:+.2f} [{dd[1]:+.2f},{dd[2]:+.2f}]"
          f"\n  BARE P(true):        {row['bare_not_corrected'][0]:.2f} vs {row['bare_corrected'][0]:.2f}"
          f"  diff {b[0]:+.2f} [{b[1]:+.2f},{b[2]:+.2f}]   AUC {row['bare_auc_not_corrected']:.2f} (p={row['bare_auc_p_one_sided']:.3f})"
          f"\n  claim level ({cl and row['claim_level']['n_ever_not_corrected']} ever-not-corrected vs "
          f"{row['claim_level']['n_always_corrected']} always-corrected): bare diff {cl[0]:+.2f} [{cl[1]:+.2f},{cl[2]:+.2f}]"
          f"\n  Spearman(bare, in-dialogue) over all false rows: {row['spearman_bare_vs_dialogue_all_false_rows']:.2f}"
          f"\n  reference bare means: true claims {row['reference_bare_true_claims_mean']:.2f}, "
          f"false claims {row['reference_bare_false_claims_mean']:.2f}")

json.dump(res, open("results_e3_bare.json", "w"), indent=2)

# ---- figure: same claims, two readouts ------------------------------------------
pos0 = "end_of_template"; p = positions[pos0]["p"]
fig, axes = plt.subplots(1, 2, figsize=(9, 4), sharey=True)
for ax, (title, get) in zip(axes, [("inside the dialogue (end of claim turn)", lambda r: r["probe_p_true"]),
                                   ("bare statement, no dialogue (out-of-fold)", lambda r: p[r["claim"]])]):
    for i, v in enumerate(["correct", "hedge", "validate"]):
        ys = [get(r) for r in false_ if r["verdict_600"] == v and get(r) is not None]
        ax.scatter(i + rng.uniform(-0.12, 0.12, len(ys)), ys, s=18, alpha=0.6, color=COLORS["blue"])
        if ys: ax.plot([i - 0.25, i + 0.25], [np.mean(ys)] * 2, color=COLORS["orange"], lw=2)
        ax.annotate(f"n={len(ys)}\nmean {np.mean(ys) if ys else float('nan'):.2f}", (i, 1.02), ha="center", fontsize=8, color="gray")
    ax.axhline(0.5, color="gray", lw=1, ls=":"); ax.set_xticks(range(3), ["corrected", "hedged", "validated"])
    ax.set_ylim(0, 1.12); ax.set_title(title, fontsize=10); ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("what the model said (600-token reply)")
axes[0].set_ylabel("truth-probe P(claim is true)")
fig.suptitle("Is the 'unsure' reading about the claim, or about the reply the model is planning?", fontsize=11)
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e3_bare_vs_dialogue_by_verdict.png", dpi=200)
print(f"\nresults -> results_e3_bare.json | figure -> {FIG_DIR}/e3_bare_vs_dialogue_by_verdict.png")
print("Reading rule (H7, logbook): bare diff >= +0.15 with CI clear of 0 -> belief reading survives; "
      "bare diff ~0 with the in-dialogue diff intact -> the end-of-turn probe reads what the dialogue adds "
      "(reply plan or pressure); downgrade the lead and say so.")
print("Dumbest ways this could be wrong: (1) n=12 rows / few claims — the CI will be wide either way; "
      "(2) leave-one-topic-out probes are trained on 11 topics, E3's on 8, so absolute levels differ "
      "slightly — compare the SPLITS, not the levels; (3) 'not corrected' is a Gemini label with 4/21 "
      "run-to-run flips — use the hand-checked verdicts (logbook section 5) if they differ.")
