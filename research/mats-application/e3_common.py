"""Shared truth-probe code for E3 (06), the bare-statement check (18) and the
linking experiment (19). One place, so every script trains the SAME probe:
StandardScaler + LogisticRegression(C=0.1), best layer chosen by held-out-topic
accuracy on the bare statements — exactly what 06_honesty_e3.py did.

Two things live here:
  train_truth_probe(name)      -> (probe, layer, heldout_acc) as in 06
  oof_bare_p_true(name, layer) -> {statement text: P(true)} for EVERY bare statement,
                                  each predicted by a probe that never saw its topic
                                  (leave-one-topic-out). Needed because a probe
                                  trained on 8 topics is in-sample on those 8; the
                                  bare-statement check must be out-of-sample for all 12.
"""
import numpy as np, torch
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from config import HELDOUT_TOPICS, act_path


def _clf():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.1))


def load_truth(name="truth"):
    d = torch.load(act_path(name))
    X, meta = d["acts"].numpy(), d["meta"]
    y = np.array([int(m["truth"]) for m in meta])
    topics = np.array([m["topic"] for m in meta])
    return X, y, topics, meta


def train_truth_probe(name="truth", layer=None):
    """Same selection rule as 06: sweep layers, keep the one with the best
    held-out-topic accuracy. Pass layer= to skip the sweep (e.g. the layer recorded in
    results_e3_raw.json), which guarantees the SAME layer as the E3 numbers."""
    X, y, topics, _ = load_truth(name)
    tt = np.isin(topics, HELDOUT_TOPICS)
    layers = [layer] if layer is not None else range(X.shape[1])
    best_L, best_a, best = None, -1, None
    for L in layers:
        clf = _clf().fit(X[~tt, L], y[~tt]); a = clf.score(X[tt, L], y[tt])
        if a > best_a:
            best_L, best_a, best = int(L), float(a), clf
    return best, best_L, best_a


def oof_bare_p_true(name="truth", layer=None):
    """Leave-one-topic-out P(true) for every bare statement at one layer.
    Returns (dict text -> p_true, per-topic accuracies)."""
    X, y, topics, meta = load_truth(name)
    out, accs = {}, {}
    for tp in sorted(set(topics)):
        te = topics == tp
        clf = _clf().fit(X[~te, layer], y[~te])
        p = clf.predict_proba(X[te, layer])[:, 1]
        accs[str(tp)] = float(((p > 0.5) == y[te]).mean())
        for m, pi in zip([mm for mm, t in zip(meta, te) if t], p):
            out[m["text"]] = float(pi)
    return out, accs


def boot(fn, *arrays, n=2000, seed=0):
    """Independent bootstrap of fn(*resampled arrays) -> (point, lo, hi)."""
    rng = np.random.default_rng(seed)
    point = fn(*arrays); bs = []
    for _ in range(n):
        bs.append(fn(*[a[rng.integers(0, len(a), len(a))] for a in arrays]))
    return float(point), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def boot_paired(fn, *arrays, n=2000, seed=0):
    """PAIRED bootstrap: all arrays are indexed by the same units (e.g. the same
    dialogues), so one index draw is applied to every array."""
    rng = np.random.default_rng(seed)
    N = len(arrays[0]); assert all(len(a) == N for a in arrays)
    point = fn(*arrays); bs = []
    for _ in range(n):
        idx = rng.integers(0, N, N)
        bs.append(fn(*[a[idx] for a in arrays]))
    return float(point), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
