"""E4: is the competence representation CAUSAL? Steer it, watch the behavior.
(CUT THIS FIRST if behind schedule — E1-E3 is already a complete story.)

Method: direction = mean(expert activations) - mean(novice activations) at the
best E1 layer (diff-of-means — how the refusal direction and the emergent-
misalignment direction were found; simple and repeatedly state-of-the-art).
During generation on NEUTRAL prompts, add alpha * unit_direction to that layer's
output at every position (a forward hook), sweep alpha.

Controls, each load-bearing:
  * random directions (3 seeds, same norm) — any big vector changes text; we must
    show THIS vector changes user-model-relevant behavior specifically.
  * alpha=0 baseline.
  * coherence judge — rules out "we just broke the model".
Baseline duel (Nanda's method minimalism):
  * system-prompt "the user is an expert/novice" — if prompting reproduces
    everything steering does, say so plainly; if steering adapts COVERTLY (no
    "since you're an expert" acknowledgments), that's a qualitative difference.

Metrics: Flesch-Kincaid grade, jargon rate, judged pitched-level + coherence.
Run: python 07_steering_e4.py
"""
import json, os, re, time
import numpy as np, torch, joblib, requests
import matplotlib.pyplot as plt
from transformers import AutoModelForCausalLM, AutoTokenizer
from config import (ACT_DIR, FIG_DIR, MODEL_ID, DTYPE, OPENROUTER_URL,
                    JUDGE_MODEL, COLORS, chat_text)

HEADERS = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
L = joblib.load("probe_e1.joblib")["layer"]

# ---- direction --------------------------------------------------------------
d = torch.load(f"{ACT_DIR}/main.pt")
X, meta = d["acts"].numpy()[:, L], d["meta"]
lv = np.array([m["level"] for m in meta])
direction = X[lv == "expert"].mean(0) - X[lv == "novice"].mean(0)
norm = np.linalg.norm(direction)
unit = torch.tensor(direction / norm)
print(f"layer {L} expert-novice direction, |d| = {norm:.1f}")

tok = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID,
                                             dtype=getattr(torch, DTYPE),
                                             device_map="cuda").eval()
# hidden_states[L] is the output of decoder layer L-1 (index 0 = embeddings),
# so we hook decoder layer L-1 to modify exactly what the probe read.
target_layer = model.model.layers[L - 1]
_steer = {"vec": None}


def hook(_, __, out):
    if _steer["vec"] is not None:
        h = out[0] if isinstance(out, tuple) else out
        h = h + _steer["vec"].to(h.dtype).to(h.device)
        return (h, *out[1:]) if isinstance(out, tuple) else h
    return out


target_layer.register_forward_hook(hook)

PROMPTS = ["Can you explain how a lens forms an image?",
           "How does an index make a database query faster?",
           "Why does bread rise?",
           "What does a p-value actually tell you?"]


@torch.no_grad()
def generate(prompt, vec=None, system=None):
    _steer["vec"] = vec
    msgs = ([{"role": "system", "content": system}] if system else []) + \
        [{"role": "user", "content": prompt}]
    ids = tok(chat_text(tok, msgs), return_tensors="pt").to("cuda")
    out = model.generate(**ids, max_new_tokens=250, do_sample=False)
    _steer["vec"] = None
    return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)


def fk_grade(text):
    sents = max(1, len(re.findall(r"[.!?]+", text)))
    words = text.split(); syll = sum(max(1, len(re.findall(r"[aeiouy]+", w.lower())))
                                     for w in words)
    return 0.39 * len(words) / sents + 11.8 * syll / max(1, len(words)) - 15.59


def judge(text):
    rubric = open("judge_rubrics.md").read().split("## E4")[1]
    r = requests.post(OPENROUTER_URL, headers=HEADERS, timeout=120, json={
        "model": JUDGE_MODEL, "temperature": 0.0,
        "messages": [{"role": "user", "content": f"{rubric}\n\nTEXT:\n{text}"}]})
    return r.json()["choices"][0]["message"]["content"].strip()


rng = np.random.default_rng(0)
rand_dirs = [torch.tensor(v / np.linalg.norm(v))
             for v in rng.standard_normal((3, len(direction)))]
ALPHAS = [-8, -4, 0, 4, 8]           # units of |d| fractions; tune on first outputs
results = []
for prompt in PROMPTS:
    for a in ALPHAS:
        for name, vec in ([("steer", unit)] +
                          [(f"rand{j}", rd) for j, rd in enumerate(rand_dirs)]):
            if a == 0 and name != "steer":
                continue
            text = generate(prompt, vec=vec * a * norm * 0.1)  # 0.1|d| granularity
            results.append({"prompt": prompt, "alpha": a, "dir": name,
                            "fk": fk_grade(text), "judge": judge(text),
                            "text": text})
            print(f"{name} a={a} fk={results[-1]['fk']:.1f} :: {text[:70]}…")
            time.sleep(0.2)
    # prompting baselines
    for sysmsg, tag in [("The user is a complete beginner on this topic.", "prompt_novice"),
                        ("The user is a domain expert on this topic.", "prompt_expert")]:
        text = generate(prompt, system=sysmsg)
        results.append({"prompt": prompt, "alpha": None, "dir": tag,
                        "fk": fk_grade(text), "judge": judge(text), "text": text})

json.dump(results, open("results_e4_raw.json", "w"), indent=2)

# dose-response figure
fig, ax = plt.subplots(figsize=(6.5, 4))
for name, c in [("steer", "blue"), ("rand0", "orange")]:
    xs = sorted({r["alpha"] for r in results if r["dir"] == name and r["alpha"] is not None})
    ys = [np.mean([r["fk"] for r in results if r["dir"] == name and r["alpha"] == a])
          for a in xs]
    ax.plot(xs, ys, marker="o", lw=2, color=COLORS[c])
    ax.annotate("competence direction" if name == "steer" else "random direction",
                (xs[-1], ys[-1]), textcoords="offset points", xytext=(6, 0),
                color=COLORS[c], fontsize=9, va="center")
pe = np.mean([r["fk"] for r in results if r["dir"] == "prompt_expert"])
pn = np.mean([r["fk"] for r in results if r["dir"] == "prompt_novice"])
ax.axhline(pe, color="gray", ls="--", lw=1)
ax.annotate('prompt "user is expert"', (ALPHAS[0], pe), fontsize=8, color="gray",
            xytext=(0, 3), textcoords="offset points")
ax.axhline(pn, color="gray", ls=":", lw=1)
ax.annotate('prompt "user is beginner"', (ALPHAS[0], pn), fontsize=8, color="gray",
            xytext=(0, 3), textcoords="offset points")
ax.set_xlabel("steering strength α (novice ← 0 → expert)")
ax.set_ylabel("Flesch-Kincaid grade of reply")
ax.set_title("Steering the user-competence direction changes explanation level")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(); fig.savefig(f"{FIG_DIR}/e4_dose_response.png", dpi=200)
print(f"figure -> {FIG_DIR}/e4_dose_response.png")
print("NOW: read steered outputs for coherence yourself; check judge coherence "
      "scores; note whether steering adapts covertly vs prompting acknowledging.")
