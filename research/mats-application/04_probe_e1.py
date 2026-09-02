"""E1: can a linear probe read the user's competence level? Where? Does it
generalize to topics it never saw?

The results this script produces, and what each is FOR:
  1. LAYER PROFILE (accuracy vs layer, held-out topics)  -> existence + location.
  2. CONTROLS: shuffled labels (must collapse to ~33% — detects leakage/bugs);
     topic probe on the same activations (must be high — positive control proving
     the activations are rich, so a competence null would mean absence of the
     concept, not a broken pipeline).
  3. TURN CURVE (accuracy vs turn index) -> evidence accumulates across turns.
     PRE-REGISTERED (logbook H1b): the PRIMARY curve uses ONE probe trained on
     all training-topic snapshots and evaluated per turn, so a rise cannot come
     from "more training data at later turns". The growing-data curve is kept as
     a secondary line. If turn-0 accuracy is already at ceiling, the generator
     leaks level in the opening line — go look at the data, don't celebrate.
  4. EXPLICIT<->IMPLICIT transfer (H1c). PRE-REGISTERED: the topic split applies
     to BOTH sets — train on training topics of one, test on held-out topics of
     the other — so the explicit set can't leak held-out topics into training.
  5. LENGTH-ONLY BASELINE (trivial-baseline check): the QC audit showed user
     turns differ in length by level (Codex experts +3 words, Gemma novices
     +8 words — opposite directions). A classifier that sees ONLY word counts
     is trained on the same split. The activation probe must beat it clearly;
     the gap is what the write-up reports.
  6. CROSS-GENERATOR transfer (project-level confound): train on Codex-written
     dialogues, test on Gemma-written ones (and back). If accuracy holds, the
     probe reads competence, not one generator's house style for "novice".
     Runs only if activations/main_gemma.pt exists.

Run: python 04_probe_e1.py   (expects activations/main.pt [+ explicit.pt, main_gemma.pt])
"""
import json, os
import numpy as np
import torch
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from config import ACT_DIR, FIG_DIR, HELDOUT_TOPICS, COLORS, SAVE_DIR, act_path

os.makedirs(FIG_DIR, exist_ok=True)
LEVEL_ID = {"novice": 0, "intermediate": 1, "expert": 2}
CHANCE = 1 / 3


def load(name, tag=None):
    d = torch.load(act_path(name, tag))
    X = d["acts"].numpy()                     # [n, layers, dim]
    return X, d["meta"]


def fit_eval(Xtr, ytr, Xte, yte):
    clf = make_pipeline(StandardScaler(),
                        LogisticRegression(max_iter=2000, C=0.1))
    clf.fit(Xtr, ytr)
    return clf.score(Xte, yte), clf


def acc_ci(correct, n):
    """95% normal-approx CI on an accuracy; n = independent units."""
    p = correct / n
    se = np.sqrt(p * (1 - p) / n)
    return p, p - 1.96 * se, p + 1.96 * se


def dialogue_level_acc(clf, X, y, ids, mask):
    """Accuracy counting ONE unit per dialogue (final-turn snapshot) — snapshots
    from the same dialogue are correlated, so per-snapshot CIs are too narrow."""
    pred = clf.predict(X[mask])
    last = {}
    for i, (d, p, t) in enumerate(zip(ids[mask], pred, y[mask])):
        last[d] = (p, t)                     # later turns overwrite -> final turn
    c = sum(p == t for p, t in last.values())
    return acc_ci(c, len(last)), len(last)


X, meta = load("main")
y = np.array([LEVEL_ID[m["level"]] for m in meta])
topics = np.array([m["topic"] for m in meta])
turns = np.array([m["turn"] for m in meta])
ids = np.array([m["id"] for m in meta])
test = np.isin(topics, HELDOUT_TOPICS)        # split BY TOPIC — the load-bearing choice
n_layers = X.shape[1]
rng = np.random.default_rng(0)
print(f"main: {len(y)} snapshots, {len(set(ids))} dialogues, {n_layers} layers; "
      f"test = held-out topics {HELDOUT_TOPICS} ({test.sum()} snapshots)")

# --- 1+2. layer profile with controls ---------------------------------------
acc_by_layer, acc_shuf, acc_topic = [], [], []
y_shuf = rng.permutation(y)
topic_id = {t: i for i, t in enumerate(sorted(set(topics)))}
y_top = np.array([topic_id[t] for t in topics])
for L in range(n_layers):
    a, _ = fit_eval(X[~test, L], y[~test], X[test, L], y[test])
    s, _ = fit_eval(X[~test, L], y_shuf[~test], X[test, L], y_shuf[test])
    # topic control uses a random split (topic held-out is impossible for topic!)
    ridx = rng.permutation(len(y)); cut = int(0.8 * len(y))
    t_a, _ = fit_eval(X[ridx[:cut], L], y_top[ridx[:cut]],
                      X[ridx[cut:], L], y_top[ridx[cut:]])
    acc_by_layer.append(a); acc_shuf.append(s); acc_topic.append(t_a)
    print(f"layer {L:2d}  competence(heldout-topics) {a:.3f}   "
          f"shuffled {s:.3f}   topic(random-split) {t_a:.3f}")

best_L = int(np.argmax(acc_by_layer))
_, probe = fit_eval(X[~test, best_L], y[~test], X[test, best_L], y[test])
(p_d, lo_d, hi_d), n_d = dialogue_level_acc(probe, X[:, best_L], y, ids, test)
print(f"\nBEST LAYER {best_L}: snapshot acc {acc_by_layer[best_L]:.3f} (chance {CHANCE:.3f})"
      f"\n  final-turn dialogue-level acc {p_d:.3f}  95% CI [{lo_d:.3f}, {hi_d:.3f}]"
      f"  (n={n_d} held-out dialogues)"
      f"\n  shuffled-label control {acc_shuf[best_L]:.3f} | topic control {acc_topic[best_L]:.3f}")

# --- length-only baseline ----------------------------------------------------
def length_features(meta, path):
    """[words in current turn, mean words/turn so far, turns so far, total words]
    computed from the SAME dialogues the activations came from."""
    rows = {r["id"]: r for r in map(json.loads, open(path))}
    F = []
    for m in meta:
        ut = [x["content"] for x in rows[m["id"]]["messages"] if x["role"] == "user"]
        wc = [len(t.split()) for t in ut[: m["turn"] + 1]]
        F.append([wc[-1], float(np.mean(wc)), len(wc), sum(wc)])
    return np.array(F, float)


acc_len = None
try:
    F = length_features(meta, f"{SAVE_DIR}/main.jsonl")
    acc_len, _ = fit_eval(F[~test], y[~test], F[test], y[test])
    print(f"LENGTH-ONLY BASELINE (held-out topics): {acc_len:.3f}   "
          f"-> activation probe beats it by {acc_by_layer[best_L] - acc_len:+.3f}")
except (FileNotFoundError, KeyError) as e:
    print(f"length baseline skipped ({e!r}) — needs {SAVE_DIR}/main.jsonl with matching ids")

# --- 3. turn curves at best layer -------------------------------------------
acc_turn_fixed, acc_turn_grow, n_turn = [], [], []
for t in range(int(turns.max()) + 1):
    m_ = test & (turns == t)
    if m_.sum() < 20: break
    acc_turn_fixed.append(probe.score(X[m_, best_L], y[m_]))       # PRIMARY (H1b)
    a, _ = fit_eval(X[~test & (turns <= t), best_L], y[~test & (turns <= t)],
                    X[m_, best_L], y[m_])
    acc_turn_grow.append(a)                                         # secondary
    n_turn.append(int(m_.sum()))
rise = acc_turn_fixed[min(3, len(acc_turn_fixed) - 1)] - acc_turn_fixed[0]
print(f"turn curve (fixed probe): {[round(a, 3) for a in acc_turn_fixed]}  n={n_turn}"
      f"\n  H1b statistic: acc(turn 3) - acc(turn 0) = {rise:+.3f}")

# --- 4. explicit <-> implicit transfer (topic-clean both ways) ---------------
transfer = {}
try:
    Xe, me = load("explicit")
    ye = np.array([LEVEL_ID[m["level"]] for m in me])
    te = np.isin([m["topic"] for m in me], HELDOUT_TOPICS)
    a_ei, _ = fit_eval(Xe[~te, best_L], ye[~te], X[test, best_L], y[test])
    a_ie, _ = fit_eval(X[~test, best_L], y[~test], Xe[te, best_L], ye[te])
    a_ee, _ = fit_eval(Xe[~te, best_L], ye[~te], Xe[te, best_L], ye[te])
    transfer = {"explicit->implicit": a_ei, "implicit->explicit": a_ie,
                "explicit->explicit": a_ee, "implicit->implicit": acc_by_layer[best_L]}
    print("transfer (train topics -> held-out topics):",
          {k: round(v, 3) for k, v in transfer.items()})
    print(f"  H1c statistic: min transfer / own-set = "
          f"{min(a_ei / max(a_ee, 1e-9), a_ie / max(acc_by_layer[best_L], 1e-9)):.2f}")
except FileNotFoundError:
    print("no explicit.pt — skipping transfer diagnostic")

# --- 5. cross-generator transfer (Codex <-> Gemma) ----------------------------
xgen = {}
try:
    Xg, mg = load("main", "gemma")
    yg = np.array([LEVEL_ID[m["level"]] for m in mg])
    tg = np.isin([m["topic"] for m in mg], HELDOUT_TOPICS)
    a_cg, _ = fit_eval(X[~test, best_L], y[~test], Xg[tg, best_L], yg[tg])
    a_gc, _ = fit_eval(Xg[~tg, best_L], yg[~tg], X[test, best_L], y[test])
    a_gg, _ = fit_eval(Xg[~tg, best_L], yg[~tg], Xg[tg, best_L], yg[tg])
    xgen = {"codex->gemma": a_cg, "gemma->codex": a_gc,
            "gemma->gemma": a_gg, "codex->codex": acc_by_layer[best_L]}
    print("cross-generator (train topics -> held-out topics):",
          {k: round(v, 3) for k, v in xgen.items()})
except FileNotFoundError:
    print("no main_gemma.pt — skipping cross-generator test "
          "(run: SAVE_DIR=data_gemma python 03_extract_activations.py main)")

# --- save probe for E2/E3 ----------------------------------------------------
import joblib; joblib.dump({"probe": probe, "layer": best_L}, "probe_e1.joblib")

# --- figures (direct-labeled, one job per chart) -----------------------------
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(acc_by_layer, color=COLORS["blue"], lw=2)
ax.plot(acc_topic, color=COLORS["green"], lw=2)
ax.plot(acc_shuf, color=COLORS["orange"], lw=2)
ax.axhline(CHANCE, color="gray", lw=1, ls=":")
if acc_len is not None:
    ax.axhline(acc_len, color="gray", lw=1, ls="--")
    ax.annotate("length-only baseline", (0, acc_len), fontsize=8, color="gray",
                xytext=(0, 3), textcoords="offset points")
for yv, lab, c in [(acc_by_layer[best_L], "user competence (held-out topics)", "blue"),
                   (acc_topic[best_L], "topic (positive control)", "green"),
                   (acc_shuf[best_L], "shuffled labels (negative control)", "orange")]:
    ax.annotate(lab, (best_L, yv), textcoords="offset points", xytext=(6, 4),
                color=COLORS[c], fontsize=9)
ax.set_xlabel("layer"); ax.set_ylabel("probe accuracy")
ax.set_title("Linear probe accuracy by layer"); ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e1_layer_profile.png", dpi=200)

fig, ax = plt.subplots(figsize=(5.5, 4))
ax.plot(acc_turn_fixed, marker="o", color=COLORS["blue"], lw=2)
ax.plot(acc_turn_grow, marker="o", color=COLORS["pink"], lw=1.5, ls="--")
ax.annotate("one probe, all turns (primary)", (len(acc_turn_fixed) - 1, acc_turn_fixed[-1]),
            textcoords="offset points", xytext=(-4, 8), ha="right",
            color=COLORS["blue"], fontsize=9)
ax.annotate("probe trained on turns ≤ t", (len(acc_turn_grow) - 1, acc_turn_grow[-1]),
            textcoords="offset points", xytext=(-4, -12), ha="right",
            color=COLORS["pink"], fontsize=9)
ax.axhline(CHANCE, color="gray", lw=1, ls=":")
ax.set_xlabel("user turn index"); ax.set_ylabel("accuracy (held-out topics)")
ax.set_title(f"Does evidence accumulate across turns? (layer {best_L})")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e1_turn_curve.png", dpi=200)
print(f"figures -> {FIG_DIR}/  |  probe -> probe_e1.joblib")
json.dump({"acc_by_layer": acc_by_layer, "acc_shuffled": acc_shuf,
           "acc_topic": acc_topic, "best_layer": best_L,
           "dialogue_level_acc_ci": [p_d, lo_d, hi_d], "n_heldout_dialogues": n_d,
           "acc_turn_fixed_probe": acc_turn_fixed, "acc_turn_growing": acc_turn_grow,
           "n_per_turn": n_turn, "h1b_rise_turn3_minus_turn0": rise,
           "transfer": transfer, "cross_generator": xgen,
           "length_only_baseline": acc_len},
          open("results_e1.json", "w"), indent=2)
