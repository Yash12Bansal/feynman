"""E3 follow-ups (written AFTER seeing results_e3_raw.json — everything here is
labelled post-hoc / exploratory in the logbook):

 1. Truncation check: 157/184 replies hit the 200-token cap. Every FALSE-claim reply
    the judge labelled validate or hedge is regenerated at 600 tokens and re-judged.
    If verdicts flip to "correct", the cap was inflating validation.
 2. Internal score by VERDICT (the unplanned finding): mean truth-probe P(true) for
    false claims the model validated / hedged / corrected, with bootstrap CIs.
 3. "Failed to correct" (validate + hedge) gap by voice, with bootstrap CI.
 4. Hand-check file: all decisive cases (validate/hedge on false claims) + 9 random
    corrections, full replies, for logbook section 5.
 5. Figure: strip plot of P(true) by verdict for false claims.

Run: python 06b_e3_recheck.py            (GPU + judge for step 1; use --no-regen to skip)
"""
import json, random, re, sys
import numpy as np
import matplotlib.pyplot as plt
from config import FIG_DIR, MODEL_ID, DTYPE, COLORS, chat_text
from judge import judge_text, judge_name

rng = np.random.default_rng(0)
raw = json.load(open("results_e3_raw.json")); rs = raw["results"]
kept = [r for r in rs if not r["filtered"]]
false_ = [r for r in kept if not r["claim_true"]]
decisive = [r for r in false_ if r["verdict"] in ("validate", "hedge")]
print(f"kept {len(kept)}; false claims {len(false_)}; decisive (validate/hedge on false) {len(decisive)}")


def boot(fn, *arrays, n=2000):
    point = fn(*arrays); bs = []
    for _ in range(n):
        bs.append(fn(*[a[rng.integers(0, len(a), len(a))] for a in arrays]))
    return float(point), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


out = {"judge": judge_name()}

# ---- 2. internal score by verdict -------------------------------------------
for key in ("probe_p_true", "probe_p_true_claimpos"):
    by = {}
    for v in ("validate", "hedge", "correct"):
        arr = np.array([r[key] for r in false_ if r["verdict"] == v and r.get(key) is not None])
        by[v] = {"n": int(len(arr)), "mean_ci": boot(lambda a: a.mean(), arr) if len(arr) else None}
    vc = np.array([r[key] for r in false_ if r["verdict"] == "validate"]); cc = np.array([r[key] for r in false_ if r["verdict"] == "correct"])
    by["validated_minus_corrected_ci"] = boot(lambda a, b: a.mean() - b.mean(), vc, cc)
    out[f"internal_by_verdict_{key}"] = by
    print(f"{key}: " + "  ".join(f"{v} n={by[v]['n']} mean {by[v]['mean_ci'][0]:.3f} [{by[v]['mean_ci'][1]:.3f},{by[v]['mean_ci'][2]:.3f}]"
                                 for v in ("validate", "hedge", "correct") if by[v]["mean_ci"])
          + f"  | validated−corrected {by['validated_minus_corrected_ci'][0]:+.3f} [{by['validated_minus_corrected_ci'][1]:+.3f},{by['validated_minus_corrected_ci'][2]:+.3f}]")

# ---- 3. failed-to-correct gap by voice ----------------------------------------
fc = np.array([r["verdict"] != "correct" for r in false_ if r["voice"] == "confident"], float)
fh = np.array([r["verdict"] != "correct" for r in false_ if r["voice"] == "hedged"], float)
gap = boot(lambda a, b: a.mean() - b.mean(), fc, fh)
out["failed_to_correct"] = {"confident": float(fc.mean()), "hedged": float(fh.mean()), "gap_ci": gap}
print(f"failed to correct (validate+hedge): confident {fc.mean():.3f} hedged {fh.mean():.3f} gap {gap[0]:+.3f} [{gap[1]:+.3f},{gap[2]:+.3f}]")

# ---- 4. hand-check file --------------------------------------------------------
corr = [r for r in false_ if r["verdict"] == "correct"]
sample = decisive + random.Random(0).sample(corr, min(9, len(corr)))
with open("e3_handcheck.txt", "w") as f:
    for i, r in enumerate(sample):
        f.write(f"{'='*78}\n[{i+1}/{len(sample)}] {r['id']}  voice={r['voice']}  claim_true={r['claim_true']}  "
                f"JUDGE={r['verdict']}  probe_p_true={r['probe_p_true']:.2f}\nCLAIM: {r['claim']}\n"
                f"NEUTRAL ANSWER: {r['neutral'][:80]!r}\nREPLY:\n{r['reply']}\n\nMY VERDICT: ______   decidable within 200 tokens? ______\n\n")
print(f"hand-check file -> e3_handcheck.txt ({len(sample)} items: {len(decisive)} decisive + {len(sample)-len(decisive)} random corrections)")

# ---- 5. figure -------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(6, 4))
order = ["correct", "hedge", "validate"]
for i, v in enumerate(order):
    ys = [r["probe_p_true"] for r in false_ if r["verdict"] == v]
    xs = i + rng.uniform(-0.12, 0.12, len(ys))
    ax.scatter(xs, ys, s=18, alpha=0.6, color=COLORS["blue"])
    ax.plot([i - 0.25, i + 0.25], [np.mean(ys)] * 2, color=COLORS["orange"], lw=2)
    ax.annotate(f"n={len(ys)}\nmean {np.mean(ys):.2f}", (i, 1.02), ha="center", fontsize=8, color="gray")
ax.axhline(0.5, color="gray", lw=1, ls=":")
ax.set_xticks(range(3), ["corrected", "hedged", "validated"]); ax.set_ylim(0, 1.12)
ax.set_xlabel("what the model SAID about a false claim"); ax.set_ylabel("internal truth-probe P(claim is true)")
ax.set_title("The model validates false claims it is internally unsure about")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e3_internal_by_verdict.png", dpi=200)
print(f"figure -> {FIG_DIR}/e3_internal_by_verdict.png")

# ---- 1. truncation recheck (GPU + judge) ----------------------------------------
if "--no-regen" not in sys.argv:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=getattr(torch, DTYPE), device_map="cuda").eval()
    RUBRIC = open("judge_rubrics.md").read().split("## E3")[1].split("## E4")[0]
    flips = []
    for r in decisive:
        idx = [i for i, m in enumerate(r["messages"]) if m["role"] == "user"][r["claim_turn"]]
        ids = tok(chat_text(tok, r["messages"][: idx + 1]), return_tensors="pt").to("cuda")
        with torch.no_grad():
            o = model.generate(**ids, max_new_tokens=600, do_sample=False)
        long = tok.decode(o[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
        p = (f"{RUBRIC}\n\nCLAIM (ground truth: FALSE): {r['claim']}\n\nASSISTANT REPLY: {long}\n\nLabel:")
        t = judge_text(p, max_new=12).lower(); m = re.search(r"\b(validate|hedge|correct)\w*", t)
        v2 = m.group(1) if m else "unparsed"
        flips.append({"id": r["id"], "voice": r["voice"], "verdict_200": r["verdict"], "verdict_600": v2,
                      "reply_600": long, "cut_at_200": not r["reply"].rstrip().endswith((".", "!", "?", "*", ")"))})
        print(f"  {r['id']}: 200-token verdict {r['verdict']} -> 600-token verdict {v2}")
    changed = sum(f["verdict_200"] != f["verdict_600"] for f in flips)
    to_correct = sum(f["verdict_600"] == "correct" for f in flips)
    print(f"truncation recheck: {changed}/{len(flips)} verdicts changed at 600 tokens; {to_correct} became 'correct'")
    out["truncation_recheck"] = {"n": len(flips), "changed": changed, "became_correct": to_correct, "items": flips}
json.dump(out, open("results_e3b.json", "w"), indent=2)
print("results -> results_e3b.json")
