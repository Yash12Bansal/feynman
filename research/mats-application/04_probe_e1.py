"""E1: can a linear probe read the user's competence level? Where? Does it
generalize to topics it never saw?

The three results this script produces, and what each is FOR:
  1. LAYER PROFILE (accuracy vs layer, held-out topics)  -> existence + location.
  2. CONTROLS: shuffled labels (must collapse to ~33% — detects leakage/bugs);
     topic probe on the same activations (must be high — positive control proving
     the activations are rich, so a competence null would mean absence of the
     concept, not a broken pipeline).
  3. TURN CURVE (accuracy vs turn index) -> evidence accumulates across turns.
     If turn-1 accuracy is already at ceiling, the generator leaks level in the
     opening line — go fix data, don't celebrate.

Also: explicit<->implicit transfer (probe trained on self-labeled dialogues tested
on implicit ones and vice versa). High transfer = one shared representation;
low = keyword feature. Free mini-finding either way.

Run: python 04_probe_e1.py       (expects activations/main.pt [+ explicit.pt])
"""
import json, os
import numpy as np
import torch
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from config import ACT_DIR, FIG_DIR, HELDOUT_TOPICS, COLORS

os.makedirs(FIG_DIR, exist_ok=True)
LEVEL_ID = {"novice": 0, "intermediate": 1, "expert": 2}


def load(name):
    d = torch.load(f"{ACT_DIR}/{name}.pt")
    X = d["acts"].numpy()                     # [n, layers, dim]
    return X, d["meta"]


def fit_eval(Xtr, ytr, Xte, yte):
    clf = make_pipeline(StandardScaler(),
                        LogisticRegression(max_iter=2000, C=0.1))
    clf.fit(Xtr, ytr)
    return clf.score(Xte, yte), clf


X, meta = load("main")
y = np.array([LEVEL_ID[m["level"]] for m in meta])
topics = np.array([m["topic"] for m in meta])
turns = np.array([m["turn"] for m in meta])
test = np.isin(topics, HELDOUT_TOPICS)        # split BY TOPIC — the load-bearing choice
n_layers = X.shape[1]
rng = np.random.default_rng(0)

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
print(f"\nBEST LAYER {best_L}: acc {acc_by_layer[best_L]:.3f} (chance=0.333)")

# --- turn curve at best layer ------------------------------------------------
acc_turn = []
for t in range(int(turns.max()) + 1):
    m_ = test & (turns == t)
    if m_.sum() < 20: break
    a, _ = fit_eval(X[~test & (turns <= t), best_L], y[~test & (turns <= t)],
                    X[m_, best_L], y[m_])
    acc_turn.append(a)

# --- explicit <-> implicit transfer -----------------------------------------
try:
    Xe, me = load("explicit")
    ye = np.array([LEVEL_ID[m["level"]] for m in me])
    a_ei, _ = fit_eval(Xe[:, best_L], ye, X[test, best_L], y[test])
    a_ie, _ = fit_eval(X[~test, best_L], y[~test], Xe[:, best_L], ye)
    print(f"explicit->implicit transfer {a_ei:.3f} | implicit->explicit {a_ie:.3f}")
except FileNotFoundError:
    print("no explicit.pt — skipping transfer diagnostic")

# --- save probe for E2/E3 ----------------------------------------------------
_, probe = fit_eval(X[~test, best_L], y[~test], X[test, best_L], y[test])
import joblib; joblib.dump({"probe": probe, "layer": best_L}, "probe_e1.joblib")

# --- figures (direct-labeled, one job per chart) -----------------------------
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(acc_by_layer, color=COLORS["blue"], lw=2)
ax.plot(acc_topic, color=COLORS["green"], lw=2)
ax.plot(acc_shuf, color=COLORS["orange"], lw=2)
ax.axhline(1 / 3, color="gray", lw=1, ls=":")
for yv, lab, c in [(acc_by_layer[best_L], "user competence (held-out topics)", "blue"),
                   (acc_topic[best_L], "topic (positive control)", "green"),
                   (acc_shuf[best_L], "shuffled labels (negative control)", "orange")]:
    ax.annotate(lab, (best_L, yv), textcoords="offset points", xytext=(6, 4),
                color=COLORS[c], fontsize=9)
ax.set_xlabel("layer"); ax.set_ylabel("probe accuracy")
ax.set_title("Linear probe accuracy by layer"); ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e1_layer_profile.png", dpi=200)

fig, ax = plt.subplots(figsize=(5.5, 4))
ax.plot(acc_turn, marker="o", color=COLORS["blue"], lw=2)
ax.axhline(1 / 3, color="gray", lw=1, ls=":")
ax.set_xlabel("user turn index"); ax.set_ylabel("accuracy (held-out topics)")
ax.set_title(f"Evidence accumulates across turns (layer {best_L})")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e1_turn_curve.png", dpi=200)
print(f"figures -> {FIG_DIR}/  |  probe -> probe_e1.joblib")
json.dump({"acc_by_layer": acc_by_layer, "best_layer": best_L,
           "acc_turn": acc_turn}, open("results_e1.json", "w"), indent=2)
