"""T1.1 + T2.2 — where does the anchoring come from? PAIRED decomposition.

05_dynamics_e2.py reports the history effect for each reversal variant with an
INDEPENDENT bootstrap, so "full-history effect +0.30 vs neutral-placeholder effect
+0.17" gives two overlapping intervals and no interval on the difference. But the
variants are the SAME 48 dialogues per direction (same ids, only the assistant's
pre-switch replies differ), so the right statistic is paired: per dialogue,
  h_v[i] = sign * (P_postonly[i] - P_v[i])        (history effect of variant v)
  d[i]   = h_full[i] - h_placeholder[i]           (what the content of the model's own
                                                   replies adds on top of structure)
and a bootstrap over dialogue ids.

Variants (all read from activations/, all optional except full + postonly):
  full         reversal.pt                   every turn as written
  postonly     reversal_postonly.pt          pre-switch turns cut off (the reference)
  placeholder  reversal_neutralassistant.pt  assistant's pre-switch replies -> fixed line
  responsive   reversal_neutralresponsive.pt assistant's pre-switch replies -> real,
                                             level-neutral answers (T2.2, H6)
  userhistory  reversal_userhistory.pt       pre-switch user turns merged into one message

Pre-registered readings (logbook section 0):
  H6  the responsive-neutral history effect lands between placeholder and full.
  T1.1 has no new hypothesis: it puts a CI on a number already claimed ("about half").
      If the paired CI on (h_full - h_placeholder) includes 0 the claim softens to
      "consistent with"; if it is clear of 0 the claim stands with its interval.

Run: PROBE_FILE=probe_e1_pooled.joblib python 17_e2_history_decomposition.py
Writes results_e2_history.json, figures/e2_history_decomposition.png
"""
import json, os, re
import numpy as np, torch, joblib
import matplotlib.pyplot as plt
from config import FIG_DIR, COLORS, SAVE_DIR, act_path
from e3_common import boot_paired

FINAL, K = 5, 3
PF = os.environ.get("PROBE_FILE", "probe_e1_pooled.joblib")
P = joblib.load(PF); probe, L = P["probe"], P["layer"]
print(f"probe {PF} (layer {L})")
p_expert = lambda x: probe.predict_proba(x)[:, 2]

VARIANTS = {"full": "reversal", "postonly": "reversal_postonly",
            "placeholder": "reversal_neutralassistant",
            "responsive": "reversal_neutralresponsive",
            "userhistory": "reversal_userhistory"}


def final_by_id(name):
    """{direction: {dialogue id: P(expert) at the final turn}} for one variant."""
    try:
        d = torch.load(act_path(name))
    except FileNotFoundError:
        return None
    X, meta = d["acts"].numpy()[:, L], d["meta"]
    idx = [i for i, m in enumerate(meta) if m["turn"] == FINAL]
    p = p_expert(X[idx])
    out = {}
    for i, pi in zip(idx, p):
        out.setdefault(meta[i]["direction"], {})[meta[i]["id"]] = float(pi)
    return out


V = {k: final_by_id(v) for k, v in VARIANTS.items()}
missing = [k for k, v in V.items() if v is None]
print("variants found:", [k for k in V if V[k] is not None], " missing:", missing)
assert V["full"] is not None and V["postonly"] is not None, "need reversal.pt and reversal_postonly.pt"

# consistent baselines at the same turn index (for the plain-language flip numbers)
dm = torch.load(act_path("main")); Xm, mm = dm["acts"].numpy()[:, L], dm["meta"]
base = {}
for x, m in zip(Xm, mm):
    if m["n_turns"] >= FINAL + 1 and m["turn"] == FINAL:
        base.setdefault(m["level"], []).append(x)
base = {lv: p_expert(np.stack(xs)) for lv, xs in base.items()}

res = {"probe": PF, "layer": L, "variants_present": [k for k in V if V[k] is not None],
       "baseline_turn5": {lv: float(v.mean()) for lv, v in base.items()}}
fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
for ax, (direction, sign, rising) in zip(axes, [("novice->expert", 1, True), ("expert->novice", -1, False)]):
    ids = sorted(set(V["full"][direction]) & set(V["postonly"][direction]))
    for k in V:
        if V[k] is not None and k not in ("full", "postonly"):
            ids = [i for i in ids if i in V[k][direction]]
    iso = np.array([V["postonly"][direction][i] for i in ids])
    R = {"n": len(ids), "history_effect": {}, "flipped_share": {}, "final_mean": {}}
    h = {}
    for k in V:
        if V[k] is None or k == "postonly":
            continue
        v = np.array([V[k][direction][i] for i in ids])
        h[k] = sign * (iso - v)                                  # per-dialogue history effect
        R["history_effect"][k] = boot_paired(lambda a: a.mean(), h[k])
        R["final_mean"][k] = float(v.mean())
        R["flipped_share"][k] = float(((v > 0.5) == rising).mean())
    R["final_mean"]["postonly"] = float(iso.mean())
    R["flipped_share"]["postonly"] = float(((iso > 0.5) == rising).mean())
    # paired differences between variants
    R["paired_diff"] = {}
    for a, b in [("full", "placeholder"), ("full", "responsive"), ("responsive", "placeholder"),
                 ("full", "userhistory")]:
        if a in h and b in h:
            R["paired_diff"][f"{a}-{b}"] = boot_paired(lambda x, y: x.mean() - y.mean(), h[a], h[b])
    # share of the full effect carried by the content of the model's own replies
    if "placeholder" in h:
        R["share_of_full_effect_from_reply_content"] = boot_paired(
            lambda x, y: 1 - y.mean() / x.mean() if abs(x.mean()) > 1e-6 else float("nan"), h["full"], h["placeholder"])
    res[direction] = R
    print(f"\n{direction}  (n={len(ids)} paired dialogues; post-only final {iso.mean():.3f})")
    for k, (pt, lo, hi) in R["history_effect"].items():
        print(f"  history effect {k:12s} {pt:+.3f} [{lo:+.3f},{hi:+.3f}]   final {R['final_mean'][k]:.3f}   "
              f"flipped {R['flipped_share'][k]:.2f}")
    for k, (pt, lo, hi) in R["paired_diff"].items():
        print(f"  paired diff {k:22s} {pt:+.3f} [{lo:+.3f},{hi:+.3f}]")
    if "share_of_full_effect_from_reply_content" in R:
        s = R["share_of_full_effect_from_reply_content"]
        if R["history_effect"]["full"][1] > 0:          # ratio is meaningful only when the full effect is clear of 0
            print(f"  share of full effect carried by reply CONTENT: {s[0]:.2f} [{s[1]:.2f},{s[2]:.2f}]")
        else:
            print("  (full history effect not clear of 0 in this direction — the content share is undefined here)")
    # figure: history effect per variant with paired CIs
    order = [k for k in ("full", "responsive", "placeholder", "userhistory") if k in R["history_effect"]]
    labels = {"full": "full history\n(model's own replies)", "responsive": "level-neutral\nresponsive replies",
              "placeholder": "fixed neutral\nplaceholder", "userhistory": "user turns only\n(merged)"}
    for j, k in enumerate(order):
        pt, lo, hi = R["history_effect"][k]
        ax.bar(j, pt, 0.6, color=COLORS["blue" if direction.startswith("novice") else "orange"], alpha=0.85)
        ax.errorbar(j, pt, yerr=[[pt - lo], [hi - pt]], color="black", capsize=4, lw=1)
        ax.annotate(f"{pt:+.2f}", (j, hi), ha="center", xytext=(0, 4), textcoords="offset points", fontsize=9)
    ax.set_xticks(range(len(order)), [labels[k] for k in order], fontsize=8)
    ax.axhline(0, color="gray", lw=1)
    ax.set_title(direction.replace("->", " → ") + f"  (n={len(ids)}, paired)", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
axes[0].set_ylabel("history effect on final P(expert)\n(post-only minus variant, sign so + = anchoring)")
fig.suptitle("What in the history carries the first impression?", fontsize=12)
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e2_history_decomposition.png", dpi=200)

# ---- T2.2 manipulation check: are the responsive-neutral replies really level-neutral?
def fk_grade(text):
    sents = max(1, len(re.findall(r"[.!?]+", text))); words = text.split()
    syll = sum(max(1, len(re.findall(r"[aeiouy]+", w.lower()))) for w in words)
    return 0.39 * len(words) / sents + 11.8 * syll / max(1, len(words)) - 15.59


try:
    orig = {r["id"]: r for r in map(json.loads, open(f"{SAVE_DIR}/reversal.jsonl"))}
    neu = {r["id"]: r for r in map(json.loads, open(f"{SAVE_DIR}/reversal_neutralresponsive.jsonl"))}
    chk = {}
    for direction in ("novice->expert", "expert->novice"):
        for tag, src in (("original", orig), ("responsive", neu)):
            fks, wc = [], []
            for r in src.values():
                if r["direction"] != direction:
                    continue
                ui = [i for i, m in enumerate(r["messages"]) if m["role"] == "user"]
                pre = [m["content"] for m in r["messages"][: ui[K]] if m["role"] == "assistant"]
                fks += [fk_grade(t) for t in pre]; wc += [len(t.split()) for t in pre]
            chk[f"{direction}/{tag}"] = {"fk_mean": float(np.mean(fks)), "fk_sd": float(np.std(fks)),
                                         "words_mean": float(np.mean(wc)), "n_replies": len(fks)}
    res["responsive_manipulation_check_fk"] = chk
    print("\nT2.2 manipulation check — FK grade of the PRE-switch assistant replies:")
    for k, v in chk.items():
        print(f"  {k:28s} grade {v['fk_mean']:5.2f} ± {v['fk_sd']:.2f}   words {v['words_mean']:.0f}   (n={v['n_replies']})")
    a, b = chk["novice->expert/responsive"]["fk_mean"], chk["expert->novice/responsive"]["fk_mean"]
    print(f"  responsive replies: n→e vs e→n grade gap {a - b:+.2f} (original gap "
          f"{chk['novice->expert/original']['fk_mean'] - chk['expert->novice/original']['fk_mean']:+.2f}); "
          "a gap near 0 = the rewrite removed the pitch")
except FileNotFoundError:
    print("\n(no data/reversal_neutralresponsive.jsonl — T2.2 manipulation check skipped)")

json.dump(res, open("results_e2_history.json", "w"), indent=2)
print(f"\nresults -> results_e2_history.json | figure -> {FIG_DIR}/e2_history_decomposition.png")
print("Dumbest ways this could be wrong: (1) the placeholder line is off-distribution, so its "
      "'structure only' reading is a lower bound — that is why T2.2 exists; (2) paired CIs assume "
      "dialogues are the unit — topics are shared across dialogues (4 per topic per direction), so "
      "a topic-level cluster bootstrap would be wider; report if the CI is close to 0.")
