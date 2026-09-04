"""Presentation redraws from result files (no model needed):
  figures/e1_layer_profile.png   - same data as 04_probe_e1.py, labels no longer collide
  figures/e2_causal_anchoring.png - two panels: judged pitch (the primary statistic) and FK grade
Run: python 14_fig_redraws.py
"""
import json, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from config import FIG_DIR, COLORS

# ---- E1 layer profile ---------------------------------------------------------
e1 = json.load(open("results_e1.json"))
a, sh, tp = e1["acc_by_layer"], e1["acc_shuffled"], e1["acc_topic"]
L = np.arange(len(a))
fig, ax = plt.subplots(figsize=(7.2, 4.2))
ax.plot(L, tp, color=COLORS["green"], lw=2); ax.plot(L, a, color=COLORS["blue"], lw=2.4); ax.plot(L, sh, color=COLORS["orange"], lw=2)
ax.axhline(e1["length_only_baseline"], color="#888", ls="--", lw=1); ax.axhline(1/3, color="#888", ls=":", lw=1)
ax.text(36.5, tp[-1], "topic\n(positive control)", color=COLORS["green"], va="center", fontsize=9)
ax.text(36.5, a[-1] - 0.06, "user competence\n(held-out topics)", color=COLORS["blue"], va="center", fontsize=9)
ax.text(36.5, sh[-1], "shuffled labels\n(negative control)", color=COLORS["orange"], va="center", fontsize=9)
ax.text(2.5, e1["length_only_baseline"] + 0.012, f"length-only baseline ({100*e1['length_only_baseline']:.0f}%)", color="#666", fontsize=8.5)
ax.text(2.5, 1/3 - 0.06, "chance (33%)", color="#666", fontsize=8.5)
ax.axvline(e1["best_layer"], color="#bbb", lw=1, ls="-"); ax.text(e1["best_layer"] + 0.4, 0.62, f"best layer {e1['best_layer']}\n({100*a[e1['best_layer']]:.1f}%)", color="#555", fontsize=8.5)
ax.set_xlim(-0.5, 44); ax.set_ylim(0.2, 1.05); ax.set_xlabel("layer"); ax.set_ylabel("probe accuracy")
ax.set_title("Linear probe accuracy by layer (Qwen3-8B, held-out topics)", fontsize=11)
for s in ("top", "right"): ax.spines[s].set_visible(False)
ax.set_xticks(range(0, 37, 6))
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e1_layer_profile.png", dpi=200); plt.close(fig)

# ---- causal anchoring: pitch + FK ------------------------------------------------
c = json.load(open("results_e2_causal.json"))["conditions"]
order = ["lifelong novice, unsteered", "reversal n→e, unsteered", "reversal n→e, steered +α*", "lifelong expert, unsteered", "lifelong expert, direction ablated"]
labels = ["lifelong\nnovice", "novice→expert\nunsteered", "novice→expert\n+ expert steer", "lifelong\nexpert", "lifelong expert\ndirection ablated"]
cols = [COLORS["orange"], COLORS["blue"], COLORS["blue"], COLORS["green"], COLORS["green"]]
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, (key, ylab, ttl) in zip(axes, [("level", "judged pitch (1 = beginner … 5 = domain expert)", "Judged pitch of the reply (primary)"),
                                        ("fk", "Flesch–Kincaid grade", "Reading grade (secondary)")]):
    m = [c[k][f"{key}_mean"] for k in order]; se = [c[k][f"{key}_se"] for k in order]
    x = np.arange(5)
    ax.bar(x, m, 0.62, color=cols, edgecolor="white", linewidth=1.5)
    ax.errorbar(x, m, yerr=se, fmt="none", ecolor="#222", capsize=3, lw=1.2)
    for i, (v, s) in enumerate(zip(m, se)): ax.text(i, v + s + (0.04 if key == "level" else 0.25), f"{v:.2f}" if key == "level" else f"{v:.1f}", ha="center", fontsize=9)
    ax.set_xticks(x, labels, fontsize=8.5); ax.set_ylabel(ylab, fontsize=9.5); ax.set_title(ttl, fontsize=10.5, loc="left")
    if key == "level": ax.set_ylim(1, 5.35)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
fig.suptitle("Does the anchored estimate show in behaviour, and is the direction necessary?  (Gemini 2.5 Pro judge; ± = SE)", fontsize=11, x=0.01, ha="left")
fig.tight_layout(rect=(0, 0, 1, 0.94)); fig.savefig(f"{FIG_DIR}/e2_causal_anchoring.png", dpi=200); plt.close(fig)
print("redrawn: e1_layer_profile.png, e2_causal_anchoring.png")
