"""Inter-judge agreement: re-judge a random sample of E3 verdicts (and/or E4
scores) with a SECOND backend and report how often the two judges agree.

Why: an LLM judge is the weakest link in E3/E4 (verification checklist: "judge
gamed?"). Your 30 hand-checks are the primary guard; a second judge on a larger
sample is the cheap secondary one. Report both numbers in the write-up.

Usage (after 06/07 have run with the primary judge):
  GEMINI_API_KEY=... python 08_judge_agreement.py e3 gemini      # 60 items
  GEMINI_API_KEY=... python 08_judge_agreement.py e4 gemini
  JUDGE_MODEL_LOCAL=microsoft/phi-4 python 08_judge_agreement.py e3 local
"""
import json, random, re, sys
from judge import judge_text, judge_name

which = sys.argv[1] if len(sys.argv) > 1 else "e3"
backend = sys.argv[2] if len(sys.argv) > 2 else "gemini"
N = int(sys.argv[3]) if len(sys.argv) > 3 else 60
rng = random.Random(0)
rub = open("judge_rubrics.md").read()

if which == "e3":
    import os
    src = os.environ.get("E3_RESULTS", "results_e3_raw.json")   # E3_RESULTS=results_e3_600.json
    rf, vf = ("reply_600", "verdict_600") if "600" in src else ("reply", "verdict")
    raw = json.load(open(src))
    rows = [{**r, "reply": r[rf], "verdict": r[vf]} for r in raw["results"] if not r["filtered"] and rf in r]
    if "600" in src:
        rows = [r for r in rows if not r["claim_true"]]                # only false claims were regenerated
    rubric = rub.split("## E3")[1].split("## E4")[0]
    sample = rng.sample(rows, min(N, len(rows)))
    agree, out = 0, []
    for r in sample:
        p = (f"{rubric}\n\nCLAIM (ground truth: {'TRUE' if r['claim_true'] else 'FALSE'}): "
             f"{r['claim']}\n\nASSISTANT REPLY: {r['reply']}\n\nLabel:")
        t = judge_text(p, max_new=12, backend=backend).lower()
        m = re.search(r"\b(validate|hedge|correct)\w*", t)
        v2 = m.group(1) if m else "unparsed"
        agree += int(v2 == r["verdict"])
        out.append({"id": r["id"], "primary": r["verdict"], "second": v2})
        print(f"{r['id']}: {raw['judge']}={r['verdict']}  {judge_name(backend)}={v2}")
    print(f"\nE3 inter-judge agreement: {agree}/{len(sample)} = {agree/len(sample):.1%}")
    json.dump({"primary": raw["judge"], "second": judge_name(backend),
               "agreement": agree / len(sample), "items": out},
              open(f"results_e3_agreement_{backend}{'_600' if '600' in src else ''}.json", "w"), indent=2)
else:
    raw = json.load(open("results_e4_raw.json"))
    rows = [r for r in raw["results"] if r.get("level") is not None]
    rubric = rub.split("## E4")[1]
    sample = rng.sample(rows, min(N, len(rows)))
    d_level, d_coh, ack_agree, out = [], [], 0, []
    for r in sample:
        t = judge_text(f"{rubric}\n\nTEXT:\n{r['text']}", max_new=40, backend=backend).lower()
        g = lambda k: (re.search(rf"{k}\s*:\s*([0-9]+)", t) or [None, None])[1]
        m = re.search(r"mentions_level\s*:\s*(yes|no)", t)
        lvl, coh = g("level"), g("coherence")
        if lvl and coh:
            d_level.append(abs(int(lvl) - r["level"])); d_coh.append(abs(int(coh) - r["coherence"]))
        if m and r.get("mentions_level_judge") is not None:
            ack_agree += int((m.group(1) == "yes") == r["mentions_level_judge"])
        out.append({"prompt": r["prompt"], "dir": r["dir"], "alpha": r["alpha"],
                    "primary": [r["level"], r["coherence"], r["mentions_level_judge"]],
                    "second_raw": t})
    within1 = sum(d <= 1 for d in d_level) / max(1, len(d_level))
    print(f"\nE4 inter-judge: level within ±1 on {within1:.1%} of {len(d_level)}; "
          f"mean |Δlevel| {sum(d_level)/max(1,len(d_level)):.2f}; "
          f"mean |Δcoherence| {sum(d_coh)/max(1,len(d_coh)):.2f}; "
          f"mentions_level agreement {ack_agree}/{len(sample)}")
    json.dump({"primary": raw["judge"], "second": judge_name(backend), "level_within_1": within1,
               "items": out}, open(f"results_e4_agreement_{backend}.json", "w"), indent=2)
