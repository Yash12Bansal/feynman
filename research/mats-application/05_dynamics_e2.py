"""E2: how does the internal user-competence estimate UPDATE on evidence?
(This is Nanda's verbatim open question: "Do LLMs form dynamic models of users
for attributes that vary across turns, eg ... what the user knows".)

Method: apply the FROZEN E1 probe (frozen = we measure how the MODEL's
representation moves, not let a refitted probe do the tracking) to every turn of
the reversal dialogues, and plot P(expert) per turn with bootstrap CI bands.

Numbers produced (pre-registered in logbook.md, Section 0):
  H2  turns-to-crossover : after evidence flips at turn 3, how many turns until
      the mean P(expert) crosses the line? Line = 0.5 (primary) AND the midpoint
      between consistent-novice and consistent-expert baselines (pre-registered
      fallback for a weak probe whose P(expert) never reaches 0.5).
  H2b asymmetry : PRE-REGISTERED metric = fraction of the journey covered, where
      journey = from the dialogue's own pre-switch value (turn 2) to the
      consistent baseline of the TARGET level at the matched turn. This removes
      the confound that one direction simply has less distance to travel.
      Bootstrap CI on the difference between directions. (Turn counts kept as a
      secondary, coarser statistic.)
  H2c anchoring : reversal final estimate vs consistent dialogues at the SAME
      turn index (turn 5), both directions, bootstrap CIs. Matched turns remove
      the 4-8-turn vs exactly-6-turn confound.

Run: python 05_dynamics_e2.py   (needs activations/reversal.pt, probe_e1.joblib,
                                 activations/main.pt for the baselines)
"""
import json, os
import numpy as np, torch, joblib
import matplotlib.pyplot as plt
from config import FIG_DIR, COLORS, act_path

K = 3                          # first switched user turn (0-indexed)
FINAL = 5                      # last turn of a 6-turn reversal dialogue
P = joblib.load(os.environ.get("PROBE_FILE", "probe_e1.joblib")); probe, L = P["probe"], P["layer"]
rng = np.random.default_rng(0)


def p_expert(x):
    return probe.predict_proba(x)[:, 2]


# ---- reversal curves --------------------------------------------------------
d = torch.load(act_path("reversal"))
X, meta = d["acts"].numpy()[:, L], d["meta"]
by_dlg = {}
for x, m in zip(X, meta):
    by_dlg.setdefault(m["id"], {"dir": m["direction"], "turns": {}})["turns"][m["turn"]] = x
curves = {"novice->expert": [], "expert->novice": []}
for v in by_dlg.values():
    if len(v["turns"]) < FINAL + 1:
        continue                                  # malformed dialogue, skip
    curves[v["dir"]].append(p_expert(np.stack([v["turns"][t] for t in range(FINAL + 1)])))
curves = {k: np.stack(v) for k, v in curves.items()}
print({k: v.shape[0] for k, v in curves.items()}, "dialogues per direction")

# ---- consistent baselines at matched turns (from main.pt) -------------------
dm = torch.load(act_path("main"))
Xm, mm = dm["acts"].numpy()[:, L], dm["meta"]
base = {}                                        # base[level][turn] -> array of P(expert)
for x, m in zip(Xm, mm):
    if m["n_turns"] >= FINAL + 1 and m["turn"] <= FINAL:
        base.setdefault(m["level"], {}).setdefault(m["turn"], []).append(x)
base = {lv: {t: p_expert(np.stack(xs)) for t, xs in d_.items()} for lv, d_ in base.items()}
nov_final, exp_final = base["novice"][FINAL], base["expert"][FINAL]
midpoint = float((nov_final.mean() + exp_final.mean()) / 2)
print(f"consistent baselines at turn {FINAL}: novice {nov_final.mean():.3f} (n={len(nov_final)})"
      f"  expert {exp_final.mean():.3f} (n={len(exp_final)})  midpoint {midpoint:.3f}")


def boot(fn, *arrays, n=2000):
    """Bootstrap the statistic fn(*resampled arrays); returns (point, lo, hi)."""
    point = fn(*arrays)
    bs = []
    for _ in range(n):
        res = [a[rng.integers(0, len(a), len(a))] for a in arrays]
        bs.append(fn(*res))
    bs = np.array(bs)
    return float(point), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def crossover(mean, line, rising):
    for t in range(K, len(mean)):
        if (mean[t] > line) == rising:
            return t - K
    return None


def journey_fraction(curve_mat, target_base, t):
    """Fraction of the way from the dialogue's own turn-2 value to the target
    baseline, reached by turn t. Averaged over dialogues. 0 = no movement,
    1 = fully at the target level, >1 = overshoot."""
    start = curve_mat[:, K - 1].mean()
    end = target_base.mean()
    return (curve_mat[:, t].mean() - start) / (end - start)


stats = {"layer": L, "n": {k: int(v.shape[0]) for k, v in curves.items()},
         "baseline_turn5": {"novice": float(nov_final.mean()),
                            "expert": float(exp_final.mean()), "midpoint": midpoint}}
fig, ax = plt.subplots(figsize=(7, 4.2))
for name, c, rising, target in [("novice->expert", "blue", True, exp_final),
                                ("expert->novice", "orange", False, nov_final)]:
    mat = curves[name]
    mean = mat.mean(0)
    bs = np.stack([mat[rng.integers(0, len(mat), len(mat))].mean(0) for _ in range(2000)])
    lo, hi = np.percentile(bs, 2.5, 0), np.percentile(bs, 97.5, 0)
    ax.plot(mean, color=COLORS[c], lw=2)
    ax.fill_between(range(len(mean)), lo, hi, color=COLORS[c], alpha=0.18, lw=0)
    ax.annotate(name, (len(mean) - 1, mean[-1]), textcoords="offset points",
                xytext=(6, 0), color=COLORS[c], fontsize=10, va="center")
    fr = {f"turn{t}": boot(lambda m_, b_: journey_fraction(m_, b_, t), mat, target)
          for t in range(K, FINAL + 1)}
    stats[name] = {
        "mean_curve": mean.tolist(), "ci_lo": lo.tolist(), "ci_hi": hi.tolist(),
        "crossover_0.5": crossover(mean, 0.5, rising),
        "crossover_midpoint": crossover(mean, midpoint, rising),
        "journey_fraction": fr,
        "final": float(mean[-1]),
    }
    print(f"{name}: crossover@0.5 = {stats[name]['crossover_0.5']}  "
          f"@midpoint = {stats[name]['crossover_midpoint']}  "
          f"journey fraction turn3 {fr['turn3'][0]:.2f} [{fr['turn3'][1]:.2f},{fr['turn3'][2]:.2f}]"
          f"  turn5 {fr['turn5'][0]:.2f} [{fr['turn5'][1]:.2f},{fr['turn5'][2]:.2f}]")

# per-dialogue flip fraction: the probe is near-saturated (consistent dialogues sit at
# ~0.00 / ~0.98), so a mean of 0.4 may mean "40% of dialogues have flipped", not
# "every dialogue is at 0.4". Report which.
for name, rising in [("novice->expert", True), ("expert->novice", False)]:
    mat = curves[name]
    flipped = [(float(((mat[:, t] > 0.5) == rising).mean())) for t in range(FINAL + 1)]
    mid = [float(((mat[:, t] > 0.2) & (mat[:, t] < 0.8)).mean()) for t in range(FINAL + 1)]
    stats[name]["fraction_of_dialogues_flipped_by_turn"] = flipped
    stats[name]["fraction_in_middle_0.2_0.8_by_turn"] = mid
    print(f"{name}: fraction of dialogues flipped by turn {[round(f, 2) for f in flipped]}; "
          f"fraction with P(expert) in (0.2, 0.8) {[round(f, 2) for f in mid]}")

# H2b asymmetry: expert->novice fraction minus novice->expert fraction (>0 = e->n faster)
asym = {}
for t in (K, FINAL):
    asym[f"turn{t}"] = boot(
        lambda a, b, en, ne: journey_fraction(a, en, t) - journey_fraction(b, ne, t),
        curves["expert->novice"], curves["novice->expert"], nov_final, exp_final)
stats["h2b_asymmetry_e2n_minus_n2e"] = asym
print(f"H2b asymmetry (e->n minus n->e) journey fraction: turn3 {asym['turn3'][0]:+.2f} "
      f"[{asym['turn3'][1]:+.2f},{asym['turn3'][2]:+.2f}]  turn5 {asym['turn5'][0]:+.2f} "
      f"[{asym['turn5'][1]:+.2f},{asym['turn5'][2]:+.2f}]   (threshold: 0.15, CI clear of 0)")
# secondary coarse statistic
stats["h2b_turns_earlier_e2n"] = (
    None if None in (stats["expert->novice"]["crossover_0.5"], stats["novice->expert"]["crossover_0.5"])
    else stats["novice->expert"]["crossover_0.5"] - stats["expert->novice"]["crossover_0.5"])

# H2c anchoring at matched turn, both directions
anch_ne = boot(lambda b, m_: b.mean() - m_[:, FINAL].mean(), exp_final, curves["novice->expert"])
anch_en = boot(lambda m_, b: m_[:, FINAL].mean() - b.mean(), curves["expert->novice"], nov_final)
stats["h2c_anchoring_gap"] = {"novice->expert (consistent expert - reversal)": anch_ne,
                              "expert->novice (reversal - consistent novice)": anch_en}
print(f"H2c anchoring gap at turn {FINAL}: n->e {anch_ne[0]:+.3f} [{anch_ne[1]:+.3f},{anch_ne[2]:+.3f}]"
      f"   e->n {anch_en[0]:+.3f} [{anch_en[1]:+.3f},{anch_en[2]:+.3f}]   (threshold 0.1)")

# H2c control: post-switch turns WITHOUT the pre-switch history (activations/reversal_postonly.pt)
try:
    dpo = torch.load(act_path("reversal_postonly"))
    Xpo, mpo = dpo["acts"].numpy()[:, L], dpo["meta"]
    po = {}
    for x, m in zip(Xpo, mpo):
        po.setdefault(m["direction"], {}).setdefault(m["turn"], []).append(x)
    po = {d_: {t: p_expert(np.stack(v)) for t, v in ts.items()} for d_, ts in po.items()}
    ctrl = {}
    for name, target, sign in [("novice->expert", exp_final, 1), ("expert->novice", nov_final, -1)]:
        full = curves[name][:, FINAL]
        iso = po[name][FINAL]
        # history effect: what the pre-switch turns cost, relative to the same turns in isolation
        hist = boot(lambda a, b: sign * (a.mean() - b.mean()), iso, full)
        # writing effect: how far even the isolated post-switch turns sit from a lifelong baseline
        writ = boot(lambda a, b: sign * (a.mean() - b.mean()), target, iso)
        ctrl[name] = {"full_context_final": float(full.mean()), "post_only_final": float(iso.mean()),
                      "consistent_target": float(target.mean()),
                      "history_effect_ci": hist, "writing_effect_ci": writ,
                      "post_only_curve": {t: float(v.mean()) for t, v in sorted(po[name].items())}}
        print(f"H2c control {name}: full-context final {full.mean():.3f} | post-switch turns only "
              f"{iso.mean():.3f} | lifelong {target.mean():.3f}  ->  history effect "
              f"{hist[0]:+.3f} [{hist[1]:+.3f},{hist[2]:+.3f}], writing effect "
              f"{writ[0]:+.3f} [{writ[1]:+.3f},{writ[2]:+.3f}]")
    stats["h2c_control_history_vs_writing"] = ctrl
    print("  (history effect > 0.1 with CI clear of 0 = anchoring is real; a large writing "
          "effect = the generator wrote weaker post-switch turns)")
except FileNotFoundError:
    print("no reversal_postonly.pt — H2c history-vs-writing control not run "
          "(python 03_extract_activations.py reversal_postonly)")

for yv, lab in [(exp_final.mean(), "consistent expert"), (nov_final.mean(), "consistent novice")]:
    ax.axhline(yv, color="gray", lw=1, ls="--")
    ax.annotate(lab, (0, yv), fontsize=8, color="gray", xytext=(0, 3), textcoords="offset points")
ax.axvline(K - 0.5, color="gray", lw=1, ls="--")
ax.annotate("evidence flips", (K - 0.5, 1.02), ha="center", fontsize=9, color="gray")
ax.axhline(0.5, color="gray", lw=1, ls=":")
ax.set_xlabel("user turn"); ax.set_ylabel("probe P(expert)")
ax.set_ylim(0, 1.05); ax.spines[["top", "right"]].set_visible(False)
ax.set_title("The model's user-competence estimate updating on evidence")
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e2_update_curves.png", dpi=200)
json.dump(stats, open("results_e2.json", "w"), indent=2)
print(f"figure -> {FIG_DIR}/e2_update_curves.png  |  results_e2.json")
