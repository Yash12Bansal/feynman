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

PRE-REGISTERED (logbook Section 0):
  * 12 prompts (was 4): noise on the per-strength mean grade drops from ~1.5 to
    ~0.8 grade levels.
  * Strength rule, fixed BEFORE seeing results: alpha* = largest |alpha| whose
    mean coherence (both signs) is >= 4/5. Report H4 at alpha*.
  * H4 statistic: [FK(+a*) - FK(-a*)] for the competence direction minus the
    same span averaged over the random directions; threshold 2 grade levels,
    judged level must move >= 1 point the same way.
  * H4b statistic: share of replies that mention the reader's level — steered
    (all nonzero alphas with coherence >= 3) vs system-prompted. Counted two ways
    (phrase list + judge line) and every reply is printed for human reading.

Judge: OpenRouter Gemini if OPENROUTER_API_KEY is set, else local Phi-4 (judge.py).
Run: python 07_steering_e4.py
"""
import json, re
import numpy as np, torch, joblib
import matplotlib.pyplot as plt
from transformers import AutoModelForCausalLM, AutoTokenizer
from config import FIG_DIR, MODEL_ID, DTYPE, COLORS, chat_text, act_path
from judge import judge_text, judge_name

L = joblib.load("probe_e1.joblib")["layer"]

# ---- direction --------------------------------------------------------------
d = torch.load(act_path("main"))
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

# 12 neutral questions, one per topic (8 training + 4 held-out topics)
PROMPTS = ["Can you explain how a lens forms an image?",
           "Why does a streak of heads not make tails more likely?",
           "Is picking individual stocks better than an index fund?",
           "Why do some chords sound tense and others restful?",
           "Why does bread rise?",
           "How does a vaccine make you immune?",
           "How does an index make a database query faster?",
           "How does carbon dioxide warm the planet?",
           "Why can a well-placed knight be worth more than a rook?",
           "Why do metals bend but ceramics shatter?",
           "What does a p-value actually tell you?",
           "What is the difference between latency and bandwidth?"]


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


ACK = re.compile(r"\b(as an? (?:expert|beginner|novice|professional|specialist)|"
                 r"since you(?:'re| are) (?:an? )?(?:expert|beginner|new|familiar|already)|"
                 r"you(?:'re| are) (?:clearly |obviously )?(?:an? )?(?:expert|beginner|novice)|"
                 r"you already know|you probably know|you(?:'re| are) new to|"
                 r"for (?:a |someone )?(?:beginner|novice|new(?:comer)?)|"
                 r"given your (?:background|expertise|experience|level)|"
                 r"your (?:expertise|background|experience) in|"
                 r"at your level|(?:someone|a person) (?:with|at) your)\b", re.I)
RUBRIC = open("judge_rubrics.md").read().split("## E4")[1]


def judge(text):
    raw = judge_text(f"{RUBRIC}\n\nTEXT:\n{text}", max_new=40).lower()
    g = lambda k: (re.search(rf"{k}\s*:\s*([0-9]+)", raw) or [None, None])[1]
    lvl, coh = g("level"), g("coherence")
    m = re.search(r"mentions_level\s*:\s*(yes|no)", raw)
    return {"level": int(lvl) if lvl else None, "coherence": int(coh) if coh else None,
            "mentions_level_judge": (m.group(1) == "yes") if m else None, "raw": raw}


rng = np.random.default_rng(0)
rand_dirs = [torch.tensor(v / np.linalg.norm(v))
             for v in rng.standard_normal((3, len(direction)))]
ALPHAS = [-8, -4, 0, 4, 8]           # units of 0.1|d|; the strength RULE picks alpha*
results = []
for prompt in PROMPTS:
    for a in ALPHAS:
        for name, vec in ([("steer", unit)] +
                          [(f"rand{j}", rd) for j, rd in enumerate(rand_dirs)]):
            if a == 0 and name != "steer":
                continue
            text = generate(prompt, vec=vec * a * norm * 0.1)  # 0.1|d| granularity
            j = judge(text)
            results.append({"prompt": prompt, "alpha": a, "dir": name, "text": text,
                            "fk": fk_grade(text), "ack_phrase": bool(ACK.search(text)), **j})
            print(f"{name:6s} a={a:+d} fk={results[-1]['fk']:5.1f} lvl={j['level']} "
                  f"coh={j['coherence']} ack={results[-1]['ack_phrase']} :: {text[:60]}…")
    for sysmsg, tag in [("The user is a complete beginner on this topic.", "prompt_novice"),
                        ("The user is a domain expert on this topic.", "prompt_expert")]:
        text = generate(prompt, system=sysmsg)
        j = judge(text)
        results.append({"prompt": prompt, "alpha": None, "dir": tag, "text": text,
                        "fk": fk_grade(text), "ack_phrase": bool(ACK.search(text)), **j})

json.dump({"judge": judge_name(), "layer": L, "results": results},
          open("results_e4_raw.json", "w"), indent=2)


# ---- analysis ---------------------------------------------------------------
def sel(dir_, a=None):
    return [r for r in results if r["dir"] == dir_ and (a is None or r["alpha"] == a)]


def mean_of(rs, k):
    v = [r[k] for r in rs if r.get(k) is not None]
    return float(np.mean(v)) if v else float("nan")


# strength rule: largest |alpha| with mean coherence >= 4 at BOTH signs (steer dir)
alpha_star = None
for a in sorted({abs(x) for x in ALPHAS if x}, reverse=True):
    if min(mean_of(sel("steer", a), "coherence"), mean_of(sel("steer", -a), "coherence")) >= 4:
        alpha_star = a; break
if alpha_star is None:
    alpha_star = min(abs(x) for x in ALPHAS if x)
    print("WARNING: no strength kept coherence >= 4; reporting the weakest and flagging it")

span = lambda dir_, k: mean_of(sel(dir_, alpha_star), k) - mean_of(sel(dir_, -alpha_star), k)
fk_steer = span("steer", "fk"); lvl_steer = span("steer", "level")
fk_rand = float(np.mean([span(f"rand{j}", "fk") for j in range(3)]))
lvl_rand = float(np.mean([span(f"rand{j}", "level") for j in range(3)]))
per_prompt = [np.mean([r["fk"] for r in sel("steer", alpha_star) if r["prompt"] == p]) -
              np.mean([r["fk"] for r in sel("steer", -alpha_star) if r["prompt"] == p])
              for p in PROMPTS]
se = float(np.std(per_prompt, ddof=1) / np.sqrt(len(per_prompt)))

steered = [r for r in results if r["dir"] == "steer" and r["alpha"] not in (0, None)
           and (r.get("coherence") or 0) >= 3]
prompted = [r for r in results if r["dir"] in ("prompt_novice", "prompt_expert")]
ack = {
    "steered_phrase": mean_of(steered, "ack_phrase"), "steered_judge": mean_of(steered, "mentions_level_judge"),
    "prompted_phrase": mean_of(prompted, "ack_phrase"), "prompted_judge": mean_of(prompted, "mentions_level_judge"),
    "n_steered": len(steered), "n_prompted": len(prompted)}

summary = {
    "judge": judge_name(), "layer": L, "alpha_star": alpha_star,
    "coherence_by_alpha_steer": {a: mean_of(sel("steer", a), "coherence") for a in ALPHAS},
    "fk_by_alpha_steer": {a: mean_of(sel("steer", a), "fk") for a in ALPHAS},
    "fk_by_alpha_rand": {a: float(np.mean([mean_of(sel(f"rand{j}", a), "fk") for j in range(3)]))
                         for a in ALPHAS if a},
    "level_by_alpha_steer": {a: mean_of(sel("steer", a), "level") for a in ALPHAS},
    "H4_fk_span_steer": fk_steer, "H4_fk_span_random": fk_rand,
    "H4_statistic_steer_minus_random": fk_steer - fk_rand, "H4_se_over_prompts": se,
    "H4_level_span_steer": lvl_steer, "H4_level_span_random": lvl_rand,
    "prompt_baseline_fk": {"novice": mean_of(sel("prompt_novice"), "fk"),
                           "expert": mean_of(sel("prompt_expert"), "fk")},
    "prompt_baseline_level": {"novice": mean_of(sel("prompt_novice"), "level"),
                              "expert": mean_of(sel("prompt_expert"), "level")},
    "H4b_acknowledgment": ack,
}
print(json.dumps(summary, indent=2))
print(f"\nH4  at alpha*={alpha_star}: FK span steer {fk_steer:+.2f} vs random {fk_rand:+.2f} "
      f"-> {fk_steer - fk_rand:+.2f} grade levels (±{se:.2f} SE)  [threshold 2]; "
      f"judged level span {lvl_steer:+.2f} vs random {lvl_rand:+.2f}  [threshold 1]"
      f"\nH4b acknowledgment: steered {ack['steered_phrase']:.0%} (phrase) / "
      f"{ack['steered_judge']:.0%} (judge)  vs prompted {ack['prompted_phrase']:.0%} / "
      f"{ack['prompted_judge']:.0%}   [threshold: steered <=10%, prompted >=30%]")
json.dump(summary, open("results_e4.json", "w"), indent=2)

# dose-response figure
fig, ax = plt.subplots(figsize=(6.5, 4))
for name, c, lab in [("steer", "blue", "competence direction"), ("rand", "orange", "random directions")]:
    xs = [a for a in ALPHAS if a or name == "steer"]
    ys = ([summary["fk_by_alpha_steer"][a] for a in xs] if name == "steer"
          else [summary["fk_by_alpha_rand"][a] for a in xs])
    ax.plot(xs, ys, marker="o", lw=2, color=COLORS[c])
    ax.annotate(lab, (xs[-1], ys[-1]), textcoords="offset points", xytext=(6, 0),
                color=COLORS[c], fontsize=9, va="center")
pe, pn = summary["prompt_baseline_fk"]["expert"], summary["prompt_baseline_fk"]["novice"]
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
print("\nNOW: read EVERY steered and prompted reply in results_e4_raw.json for coherence "
      "and for level-acknowledgment (H4b is decided by your count, the judge is a cross-check).")
