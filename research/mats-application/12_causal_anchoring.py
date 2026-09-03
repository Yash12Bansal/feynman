"""E2 → causal. Everything in E2 is a probe READOUT (correlational). This script asks
whether the anchored representation shows up in BEHAVIOUR and whether the competence
direction is NECESSARY, not just sufficient, for the model's adaptation.

 A. Behavioural anchoring: Qwen's reply at the final turn of novice→expert reversal
    dialogues vs lifelong-expert dialogues at the same turn index (and lifelong novices
    as the floor). Pitch = Flesch–Kincaid grade + judged level (Gemini rubric).
 B. Steering un-anchors? The same reversal replies with +α*·(expert−novice) added at
    layer L (E4 hook). If the pitch gap to lifelong experts closes, the representation
    causally drives the anchored behaviour.
 C. Necessity: lifelong-expert dialogues with the direction PROJECTED OUT (mean-ablation
    along the competence axis: the projection is set to the dataset mean). If replies
    fall toward the default pitch, the direction is necessary for adaptation.
 D. Diagnostics: cosine(LR probe weights, diff-of-means); logit-lens top tokens of ±d.
Run: python 12_causal_anchoring.py     (GPU + judge, ~25 min)
"""
import json, re, os
import numpy as np, torch, joblib
from transformers import AutoModelForCausalLM, AutoTokenizer
from config import MODEL_ID, DTYPE, SAVE_DIR, FIG_DIR, COLORS, HELDOUT_TOPICS, chat_text, act_path
from judge import judge_text, judge_name
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
P = joblib.load(os.environ.get("PROBE_FILE", "probe_e1_pooled.joblib")); probe, L = P["probe"], P["layer"]
ALPHA = int(os.environ.get("ALPHA_STAR", json.load(open("results_e4.json"))["alpha_star"]))
FINAL = 5

# ---- direction (as in E4) -----------------------------------------------------
d = torch.load(act_path("main")); X, meta = d["acts"].numpy()[:, L], d["meta"]
lv = np.array([m["level"] for m in meta])
direction = X[lv == "expert"].mean(0) - X[lv == "novice"].mean(0)
norm = float(np.linalg.norm(direction)); unit = direction / norm
mean_proj = float((X @ unit).mean())                # dataset mean along the axis (for mean-ablation)
# D1: cosine with the LR probe's expert-vs-novice weight direction (undo the scaler)
sc, lr = probe.named_steps["standardscaler"], probe.named_steps["logisticregression"]
w_raw = (lr.coef_[2] - lr.coef_[0]) / sc.scale_
cos = float(w_raw @ unit / np.linalg.norm(w_raw))
print(f"layer {L}: |d| = {norm:.1f}; cosine(probe expert−novice weights, diff-of-means) = {cos:.3f}")

tok = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=getattr(torch, DTYPE), device_map="cuda").eval()
u_t = torch.tensor(unit, dtype=torch.float32)
_mode = {"steer": None, "ablate": False}


def hook(_, __, out):
    h = out[0] if isinstance(out, tuple) else out
    if _mode["ablate"]:
        u = u_t.to(h.device, h.dtype)
        proj = (h @ u).unsqueeze(-1)
        h = h - (proj - mean_proj) * u                      # set projection to the dataset mean
    if _mode["steer"] is not None:
        h = h + _mode["steer"].to(h.device, h.dtype)
    return (h, *out[1:]) if isinstance(out, tuple) else h


model.model.layers[L - 1].register_forward_hook(hook)

# D2: logit lens of the direction
W_U = model.lm_head.weight.detach().float().cpu()          # [vocab, d_model]
for sign, name in ((1, "+d (expert)"), (-1, "−d (novice)")):
    logits = W_U @ (sign * torch.tensor(unit, dtype=torch.float32))
    top = [tok.decode([i]) for i in torch.topk(logits, 15).indices.tolist()]
    print(f"logit lens {name}: {top}")


@torch.no_grad()
def reply(messages, steer=None, ablate=False, max_new=200):
    _mode["steer"], _mode["ablate"] = steer, ablate
    ids = tok(chat_text(tok, messages), return_tensors="pt").to("cuda")
    out = model.generate(**ids, max_new_tokens=max_new, do_sample=False)
    _mode["steer"], _mode["ablate"] = None, False
    return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)


def fk_grade(text):
    sents = max(1, len(re.findall(r"[.!?]+", text))); words = text.split()
    syll = sum(max(1, len(re.findall(r"[aeiouy]+", w.lower()))) for w in words)
    return 0.39 * len(words) / sents + 11.8 * syll / max(1, len(words)) - 15.59


RUBRIC = open("judge_rubrics.md").read().split("## E4")[1]
def judge(text):
    raw = judge_text(f"{RUBRIC}\n\nTEXT:\n{text}", max_new=40).lower()
    g = lambda k: (re.search(rf"{k}\s*:\s*([0-9]+)", raw) or [None, None])[1]
    return {"level": int(g("level")) if g("level") else None, "coherence": int(g("coherence")) if g("coherence") else None}


# ---- dialogue groups ------------------------------------------------------------
rev = [json.loads(l) for l in open(f"{SAVE_DIR}/reversal.jsonl")]
n2e = [r for r in rev if r["direction"] == "novice->expert"]
mainrows = [json.loads(l) for l in open(f"{SAVE_DIR}/main.jsonl")]
def with6(level):
    return [r for r in mainrows if r["level"] == level and sum(m["role"] == "user" for m in r["messages"]) >= FINAL + 1]
experts, novices = with6("expert"), with6("novice")
def ctx_at(r, t):        # context up to and including user turn t
    ui = [i for i, m in enumerate(r["messages"]) if m["role"] == "user"]
    return r["messages"][: ui[t] + 1]
print(f"groups: novice→expert reversal {len(n2e)}, lifelong experts (≥6 turns) {len(experts)}, lifelong novices {len(novices)}")

conds = {
    "reversal n→e, unsteered": [(r, None, False) for r in n2e],
    "reversal n→e, steered +α*": [(r, u_t * ALPHA * norm * 0.1, False) for r in n2e],
    "lifelong expert, unsteered": [(r, None, False) for r in experts],
    "lifelong expert, direction ablated": [(r, None, True) for r in experts],
    "lifelong novice, unsteered": [(r, None, False) for r in novices],
}
results = {}
for cname, items in conds.items():
    rows = []
    for r, st, ab in items:
        text = reply(ctx_at(r, FINAL), steer=st, ablate=ab)
        j = judge(text)
        rows.append({"id": r["id"], "fk": fk_grade(text), **j, "text": text})
    fk = np.array([x["fk"] for x in rows]); lvl = np.array([x["level"] for x in rows if x["level"] is not None], float)
    coh = np.array([x["coherence"] for x in rows if x["coherence"] is not None], float)
    results[cname] = {"n": len(rows), "fk_mean": float(fk.mean()), "fk_se": float(fk.std(ddof=1) / np.sqrt(len(fk))),
                      "level_mean": float(lvl.mean()), "level_se": float(lvl.std(ddof=1) / np.sqrt(len(lvl))),
                      "coherence_mean": float(coh.mean()), "rows": rows}
    print(f"{cname:38s} n={len(rows):3d}  grade {fk.mean():5.2f} ±{fk.std(ddof=1)/np.sqrt(len(fk)):.2f}  "
          f"level {lvl.mean():.2f} ±{lvl.std(ddof=1)/np.sqrt(len(lvl)):.2f}  coherence {coh.mean():.2f}")

def diff(a, b, k):
    A, B = results[a], results[b]; se = np.sqrt(A[f"{k}_se"]**2 + B[f"{k}_se"]**2)
    return A[f"{k}_mean"] - B[f"{k}_mean"], se
summary = {"layer": L, "alpha_star": ALPHA, "cosine_probe_vs_diffmeans": cos, "judge": judge_name(),
           "conditions": {k: {kk: v for kk, v in val.items() if kk != "rows"} for k, val in results.items()}}
for k in ("fk", "level"):
    a, se = diff("reversal n→e, unsteered", "lifelong expert, unsteered", k)
    b, se2 = diff("reversal n→e, steered +α*", "lifelong expert, unsteered", k)
    c, se3 = diff("lifelong expert, direction ablated", "lifelong expert, unsteered", k)
    summary[f"A_behavioural_anchoring_{k}"] = [a, se]; summary[f"B_steered_gap_{k}"] = [b, se2]; summary[f"C_ablation_effect_{k}"] = [c, se3]
    print(f"[{k}] A behavioural anchoring (reversal − lifelong expert): {a:+.2f} ±{se:.2f} | "
          f"B after steering: {b:+.2f} ±{se2:.2f} | C ablation on lifelong experts: {c:+.2f} ±{se3:.2f}")
json.dump({**summary, "results": results}, open("results_e2_causal.json", "w"), indent=2)

fig, ax = plt.subplots(figsize=(7.5, 4))
order = ["lifelong novice, unsteered", "reversal n→e, unsteered", "reversal n→e, steered +α*",
         "lifelong expert, unsteered", "lifelong expert, direction ablated"]
ys = [results[k]["fk_mean"] for k in order]; es = [results[k]["fk_se"] for k in order]
cols = [COLORS["orange"], COLORS["blue"], COLORS["blue"], COLORS["green"], COLORS["green"]]
ax.bar(range(len(order)), ys, yerr=es, color=cols, alpha=[0.5, 1, 0.6, 1, 0.6][0] if False else 0.9, capsize=3)
for i, k in enumerate(order):
    ax.annotate(f"{ys[i]:.1f}", (i, ys[i] + es[i]), ha="center", xytext=(0, 3), textcoords="offset points", fontsize=9)
ax.set_xticks(range(len(order)), ["lifelong\nnovice", "novice→expert\nunsteered", "novice→expert\n+ expert steer",
                                  "lifelong\nexpert", "lifelong expert\ndirection ablated"], fontsize=8)
ax.set_ylabel("Flesch–Kincaid grade of the model's reply"); ax.spines[["top", "right"]].set_visible(False)
ax.set_title("Does the anchored representation show in behaviour, and is the direction necessary?")
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e2_causal_anchoring.png", dpi=200)
print(f"figure -> {FIG_DIR}/e2_causal_anchoring.png | results_e2_causal.json")
print("\nNOW: read 10 replies from each condition in results_e2_causal.json (coherence, pitch).")
