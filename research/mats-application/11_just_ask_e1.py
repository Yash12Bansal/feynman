"""The cheapest control, from Nanda's "Common Mistakes": compare against "just ask the
model". Two questions:
 (1) E1: on held-out-topic dialogues, at the final turn, append a user message asking
     Qwen to rate the user's level in one word. Compare with the label and with the
     probe's prediction at the same turn. If asking matches the probe, the probe adds
     little for E1 (and we say so). If asking is worse — e.g. it calls learning novices
     "intermediate" the way blind judges did — the internal representation is sharper
     than the verbal report.
 (2) E2: the same question at the final turn of the reversal dialogues. Does the model's
     STATED estimate show the same anchoring as its internal one? Compare with the
     probe's P(expert) per dialogue.
Also asked at turn 0 (first message only) for the main set, to mirror the probe's 96.6%.
Run: python -u 11_just_ask_e1.py                 (three-way, ~5 min)
     JUSTASK_MODE=binary python -u 11_just_ask_e1.py
     JUSTASK_MODE=third  python -u 11_just_ask_e1.py
"""
import json, os, re, collections
import numpy as np, torch, joblib
from transformers import AutoModelForCausalLM, AutoTokenizer
from config import MODEL_ID, DTYPE, HELDOUT_TOPICS, SAVE_DIR, chat_text, act_path

# First run: the three-way question returned "intermediate" for ALL 179 + 96 dialogues.
# That could be an inability to report OR the polite middle option. Variants, chosen by
# JUSTASK_MODE: "three" (original), "binary" (no middle option), "third" (third-person
# frame: the model is asked to brief a colleague, removing the politeness pressure).
MODE = os.environ.get("JUSTASK_MODE", "three")
QS = {
    "three": ("Quick question before we continue: based on our conversation so far, how would you "
              "rate my level of knowledge on this topic? Answer with exactly one word: novice, "
              "intermediate, or expert."),
    "binary": ("Quick question before we continue: based on our conversation so far, am I closer to a "
               "beginner or closer to an expert on this topic? You must pick one. Answer with exactly "
               "one word: beginner or expert."),
    "third": ("A colleague is about to take over this conversation and needs a one-word briefing on "
              "the user's level of knowledge of this topic, judged only from what the user has "
              "written so far. Be accurate, not polite. Answer with exactly one word: novice, "
              "intermediate, or expert."),
}
Q = QS[MODE]
P = joblib.load(os.environ.get("PROBE_FILE", "probe_e1_pooled.joblib")); probe, L = P["probe"], P["layer"]
tok = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=getattr(torch, DTYPE), device_map="cuda").eval()


@torch.no_grad()
def ask(messages):
    ids = tok(chat_text(tok, messages + [{"role": "user", "content": Q}]), return_tensors="pt").to("cuda")
    out = model.generate(**ids, max_new_tokens=8, do_sample=False)
    t = tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True).lower()
    m = re.search(r"novice|beginner|intermediate|expert", t)
    g = m.group(0) if m else "unparsed"
    return ("novice" if g == "beginner" else g), t


LV = ["novice", "intermediate", "expert"]
out = {}

# ---- (1) main set, held-out topics ------------------------------------------
rows = [json.loads(l) for l in open(f"{SAVE_DIR}/main.jsonl")]
held = [r for r in rows if r["topic"] in HELDOUT_TOPICS]
d = torch.load(act_path("main")); X, meta = d["acts"].numpy()[:, L], d["meta"]
probe_pred = {}
for x, m in zip(X, meta):
    if m["topic"] in HELDOUT_TOPICS and m["turn"] in (0, m["n_turns"] - 1):
        probe_pred[(m["id"], "final" if m["turn"] == m["n_turns"] - 1 else "first")] = LV[int(probe.predict(x[None])[0])]
for which in ("final", "first"):
    conf = {a: collections.Counter() for a in LV}; agree_probe = 0; n = 0; raws = []
    for r in held:
        msgs = r["messages"]
        user_idx = [i for i, m in enumerate(msgs) if m["role"] == "user"]
        ctx = msgs[: user_idx[-1] + 1] if which == "final" else msgs[:1]
        # the model must answer after the user's last message; we append Q as a new user
        # turn, so the context must END with an assistant turn -> include the assistant
        # reply that follows the last user turn where one exists
        if which == "final":
            ctx = msgs[: user_idx[-1] + 2] if user_idx[-1] + 1 < len(msgs) else msgs[: user_idx[-1] + 1]
            if ctx[-1]["role"] == "user":
                ctx = ctx[:-1]                       # drop dangling user turn so Q follows an assistant turn
        else:
            ctx = msgs[:2]                           # first user turn + its assistant reply
        g, raw = ask(ctx)
        conf[r["level"]][g] += 1; n += 1
        agree_probe += int(g == probe_pred.get((r["id"], which)))
        raws.append(raw)
    if MODE == "binary":   # intermediates have no correct answer; score novice/expert rows only
        acc = (conf["novice"]["novice"] + conf["expert"]["expert"]) / max(1, sum(conf["novice"].values()) + sum(conf["expert"].values()))
    else:
        acc = sum(conf[a][a] for a in LV) / n
    out[f"main_{which}"] = {"n": n, "acc": acc, "confusion": {a: dict(c) for a, c in conf.items()},
                            "agree_with_probe": agree_probe / n}
    print(f"JUST ASK, main held-out, {which} turn: acc {acc:.3f} (probe at same turn: "
          f"{'99.4%' if which=='final' else '96.6%'}); agrees with probe on {agree_probe/n:.1%}")
    for a in LV: print(f"   true {a:12s} -> {dict(conf[a])}")
    print("   raw samples:", raws[:5])

# ---- (2) reversal set, final turn --------------------------------------------
rev = [json.loads(l) for l in open(f"{SAVE_DIR}/reversal.jsonl")]
dr = torch.load(act_path("reversal")); Xr, mr = dr["acts"].numpy()[:, L], dr["meta"]
p_final = {m["id"]: float(probe.predict_proba(x[None])[0, 2]) for x, m in zip(Xr, mr) if m["turn"] == 5}
res = {dname: [] for dname in ("novice->expert", "expert->novice")}
for r in rev:
    msgs = r["messages"]
    ctx = msgs if msgs[-1]["role"] == "assistant" else msgs[:-1]
    g, raw = ask(ctx)
    res[r["direction"]].append({"id": r["id"], "said": g, "probe_p_expert": p_final.get(r["id"])})
for dname, items in res.items():
    said = collections.Counter(i["said"] for i in items)
    target = "expert" if dname == "novice->expert" else "novice"
    stated_target = said[target] / len(items)
    probe_target = np.mean([(i["probe_p_expert"] > 0.5) == (target == "expert") for i in items if i["probe_p_expert"] is not None])
    out[f"reversal_{dname}"] = {"n": len(items), "stated": dict(said), "stated_matches_current_behaviour": stated_target,
                                "probe_matches_current_behaviour": float(probe_target), "items": items}
    print(f"JUST ASK, reversal {dname} at final turn: model SAYS {dict(said)} -> matches current behaviour "
          f"{stated_target:.1%}; probe matches current behaviour {probe_target:.1%}")
fn = "results_e1_justask.json" if MODE == "three" else f"results_e1_justask_{MODE}.json"
json.dump(out, open(fn, "w"), indent=2)
print("results ->", fn)
