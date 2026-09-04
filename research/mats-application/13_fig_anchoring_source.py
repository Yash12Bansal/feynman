"""Figure for the anchoring-source result (E2 chain of controls), drawn from results_e2.json.
For each reversal direction: how far the final probe estimate (turn 6) sits from the
lifelong baseline of the target level, under three versions of the pre-switch history:
  cut off entirely (post-switch turns only)      -> writing effect
  kept, with the model's replies replaced by a neutral placeholder -> user's turns + structure
  kept in full (the model's own pitched replies)  -> full first-impression effect
Run: python 13_fig_anchoring_source.py  -> figures/e2_anchoring_source.png
"""
import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import FIG_DIR, COLORS

d = json.load(open("results_e2.json"))["h2c_control_history_vs_writing"]
ROWS = [("history cut off\n(post-switch turns only)", "writing_effect_ci", -1),
        ("history kept, model's replies\nreplaced by a neutral line", "history_effect_neutral_assistant_ci", 1),
        ("history kept in full\n(model's own pitched replies)", "history_effect_ci", 1)]
# writing_effect is (lifelong - post_only); flip sign so every row reads "distance below/above baseline"
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharex=True)
for ax, (dirn, title) in zip(axes, [("novice->expert", "Novice start, then three expert turns"),
                                     ("expert->novice", "Expert start, then three novice turns")]):
    v = d[dirn]
    for i, (label, key, sign) in enumerate(ROWS):
        p, lo, hi = [sign * x for x in v[key]]
        lo, hi = min(lo, hi), max(lo, hi)
        ax.plot([lo, hi], [i, i], color=COLORS["blue"], lw=2, solid_capstyle="round")
        ax.plot(p, i, "o", ms=9, color=COLORS["blue"], mec="white", mew=1.5)
        ax.text(hi + 0.012, i, f"{p:+.2f}", va="center", ha="left", fontsize=10, color="#333")
    ax.axvline(0, color="#999", lw=1, ls="--")
    ax.set_yticks(range(len(ROWS))); ax.set_yticklabels([r[0] for r in ROWS], fontsize=9.5)
    ax.set_title(title, fontsize=11, loc="left")
    ax.set_xlim(-0.06, 0.48); ax.grid(axis="x", color="#eee"); ax.set_axisbelow(True)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
axes[1].set_yticklabels([])
fig.supxlabel("Distance of the final estimate (turn 6) from the lifelong baseline of the new level, in probe P(expert); 95% bootstrap CI",
              fontsize=9.5, y=0.02)
fig.suptitle("How much of the first impression survives, by what stays in the pre-switch history",
             fontsize=11.5, x=0.01, ha="left")
plt.tight_layout(rect=(0, 0.05, 1, 0.94))
plt.savefig(f"{FIG_DIR}/e2_anchoring_source.png", dpi=180)
print("saved", f"{FIG_DIR}/e2_anchoring_source.png")
