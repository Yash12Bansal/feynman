"""E2: how does the internal user-competence estimate UPDATE on evidence?
(This is Nanda's verbatim open question: "Do LLMs form dynamic models of users
for attributes that vary across turns, eg ... what the user knows".)

Method: apply the FROZEN E1 probe (frozen = we measure how the MODEL's
representation moves, not let a refitted probe do the tracking) to every turn of
the reversal dialogues, and plot P(expert) per turn with bootstrap CI bands.

The three numbers this produces — none has been published for user models:
  * turns-to-crossover : after evidence flips at turn k, how many turns until
    P(expert) crosses 0.5?
  * asymmetry          : novice->expert vs expert->novice speed. Both directions
    are theoretically motivated ("competence must be demonstrated" vs "one error
    destroys credibility") — which wins is a genuinely open question.
  * anchoring          : final-turn estimate of reversal dialogues vs consistent
    dialogues (from main.jsonl) — any gap is first-impression anchoring.

Run: python 05_dynamics_e2.py   (needs activations/reversal.pt, probe_e1.joblib,
                                 activations/main.pt for the anchoring baseline)
"""
import numpy as np, torch, joblib
import matplotlib.pyplot as plt
from config import ACT_DIR, FIG_DIR, COLORS

P = joblib.load("probe_e1.joblib"); probe, L = P["probe"], P["layer"]
d = torch.load(f"{ACT_DIR}/reversal.pt")
X, meta = d["acts"].numpy()[:, L], d["meta"]

# group by dialogue, collect per-turn P(expert)
by_dlg = {}
for x, m in zip(X, meta):
    by_dlg.setdefault(m["id"], {"dir": m["direction"], "k": m["switch_turn"],
                                "turns": {}})["turns"][m["turn"]] = x
curves = {"novice->expert": [], "expert->novice": []}
for v in by_dlg.values():
    T = max(v["turns"]) + 1
    p_exp = probe.predict_proba(np.stack([v["turns"][t] for t in range(T)]))[:, 2]
    curves[v["dir"]].append(p_exp)


def boot_ci(mat, n=2000, rng=np.random.default_rng(0)):
    mat = np.stack(mat); mean = mat.mean(0)
    bs = np.stack([mat[rng.integers(0, len(mat), len(mat))].mean(0)
                   for _ in range(n)])
    return mean, np.percentile(bs, 2.5, 0), np.percentile(bs, 97.5, 0)


def crossover(mean, k, rising):
    for t in range(k, len(mean)):
        if (mean[t] > 0.5) == rising:
            return t - k
    return None


fig, ax = plt.subplots(figsize=(7, 4.2))
stats = {}
for name, c in [("novice->expert", "blue"), ("expert->novice", "orange")]:
    mean, lo, hi = boot_ci(curves[name])
    k = 3  # switch turn (0-indexed: evidence flips starting turn index 3)
    ax.plot(mean, color=COLORS[c], lw=2)
    ax.fill_between(range(len(mean)), lo, hi, color=COLORS[c], alpha=0.18, lw=0)
    ax.annotate(name, (len(mean) - 1, mean[-1]), textcoords="offset points",
                xytext=(6, 0), color=COLORS[c], fontsize=10, va="center")
    stats[name] = {"turns_to_crossover_after_switch":
                   crossover(mean, k, rising=name == "novice->expert"),
                   "final": float(mean[-1])}
ax.axvline(2.5, color="gray", lw=1, ls="--")
ax.annotate("evidence flips", (2.5, 1.02), ha="center", fontsize=9, color="gray")
ax.axhline(0.5, color="gray", lw=1, ls=":")
ax.set_xlabel("user turn"); ax.set_ylabel("probe P(expert)")
ax.set_ylim(0, 1.05); ax.spines[["top", "right"]].set_visible(False)
ax.set_title("The model's user-competence estimate updating on evidence")
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e2_update_curves.png", dpi=200)

# anchoring: compare reversal final estimates to consistent-dialogue estimates
dm = torch.load(f"{ACT_DIR}/main.pt")
Xm, mm = dm["acts"].numpy()[:, L], dm["meta"]
last = [probe.predict_proba(x[None])[:, 2].item()
        for x, m in zip(Xm, mm) if m["level"] == "expert" and m["turn"] == m["n_turns"] - 1]
stats["consistent_expert_final_mean"] = float(np.mean(last))
stats["anchoring_gap_nov2exp"] = stats["consistent_expert_final_mean"] - \
    stats["novice->expert"]["final"]
print(stats)
import json; json.dump(stats, open("results_e2.json", "w"), indent=2)
print(f"figure -> {FIG_DIR}/e2_update_curves.png")
