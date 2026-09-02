"""Quality control for generated dialogues. Run BEFORE spending GPU time.

Three checks, each with a purpose:
 1. HUMAN READ  - prints 3 random dialogues per (topic x level) cell for YOU to read.
                  Nanda: "If bad data would sink your project, show me the data."
                  It's also where you catch generator failures no metric will.
 2. BLIND JUDGE - a different-family LLM classifies each dialogue's level WITHOUT
                  seeing the label. Purpose: if a black-box judge can't recover the
                  level, the signals are too subtle and a null probe result would be
                  uninterpretable; if it's 100%, signals may be too on-the-nose.
                  Target ~85-95% agreement. REPORT this number in the write-up.
 3. CONFOUND AUDIT - word counts and level-keyword leaks per level. Purpose: length
                  and self-labels are the classic shortcuts a linear probe will
                  happily learn instead of competence.
Run: python 02_qc_dialogues.py [read|judge|audit|all]
"""
import json, os, random, re, sys, time
import requests
from config import OPENROUTER_URL, JUDGE_MODEL, SAVE_DIR

random.seed(1)
HEADERS = {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"}  # only the API judge needs it
BANNED = re.compile(r"\b(beginner|novice|expert|intermediate|new to|years of|"
                    r"my background|as a professional|i teach|phd|student)\b", re.I)

rows = [json.loads(l) for l in open(f"{SAVE_DIR}/main.jsonl")]


def user_text(d):
    return [m["content"] for m in d["messages"] if m["role"] == "user"]


def human_read():
    cells = {}
    for d in rows:
        cells.setdefault((d["topic"], d["level"]), []).append(d)
    for (topic, level), ds in sorted(cells.items()):
        for d in random.sample(ds, min(3, len(ds))):
            print("=" * 70, f"\n[{d['id']}]  READ ME — does this feel like a real "
                  f"{level} asking about {topic}?  Note verdict in logbook.md\n")
            for m in d["messages"]:
                print(f"{m['role'].upper()}: {m['content']}\n")


def judge_local(model_id=None):
    """Blind level-classification with a LOCAL model (no API needed).
    Default judge is Phi-4 (third family). Override with JUDGE_MODEL_LOCAL, e.g.
    JUDGE_MODEL_LOCAL=google/gemma-3-27b-it — fine for judging CODEX dialogues
    (Gemma did not write them), NOT for judging data_gemma (same family).
    Prints a confusion matrix, raw outputs, and writes qc_judge_<tag>.jsonl,
    because a low agreement number is uninterpretable without them: it can mean
    unreadable labels, a biased judge ("intermediate" for everything), or a
    parse failure (preamble cut off) — three different problems."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    model_id = model_id or os.environ.get("JUDGE_MODEL_LOCAL", "microsoft/phi-4")
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, dtype=torch.bfloat16, device_map="cuda").eval()
    sample = random.sample(rows, min(120, len(rows)))
    levels = ["novice", "intermediate", "expert"]
    # JUDGE_TURNS=2 judges only the first N user turns: tests whether novices
    # read as "intermediate" because they LEARN across the dialogue.
    nturns = int(os.environ.get("JUDGE_TURNS", "0"))
    conf = {a: {b: 0 for b in levels + ["unparsed"]} for a in levels}
    items, correct = [], 0
    for d in sample:
        uts = user_text(d)[:nturns] if nturns else user_text(d)
        convo = "\n".join(f"USER: {t}" for t in uts)
        p = ("Below are only the USER turns of a dialogue with an AI assistant.\n"
             "Classify the user's competence on the topic as exactly one of: "
             "novice, intermediate, expert.\n"
             "novice = states a common misconception as a belief, everyday words, "
             "what/why questions. intermediate = basics right, imprecise at the edges, "
             "how/when questions. expert = precise terminology, edge cases and "
             "trade-offs, hedges only where the field is uncertain.\n"
             "Base this only on the text. Answer with exactly one word: novice, "
             f"intermediate, or expert.\n\n{convo}\n\nAnswer:")
        ids = tok(tok.apply_chat_template([{"role": "user", "content": p}],
                                          tokenize=False, add_generation_prompt=True),
                  return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=24, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        raw = tok.decode(out[0, ids["input_ids"].shape[1]:],
                         skip_special_tokens=True).strip()
        m = re.search(r"novice|intermediate|expert", raw.lower())
        guess = m.group(0) if m else "unparsed"
        conf[d["level"]][guess] += 1
        correct += int(guess == d["level"])
        items.append({"id": d["id"], "level": d["level"], "guess": guess, "raw": raw})
    tag = (model_id.split("/")[-1] + ("" if SAVE_DIR == "data" else "_" + SAVE_DIR)
           + (f"_first{nturns}turns" if nturns else ""))
    with open(f"qc_judge_{tag}.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    print(f"\nBLIND JUDGE AGREEMENT (local {model_id}, {SAVE_DIR}): "
          f"{correct}/{len(sample)} = {correct/len(sample):.1%}  "
          "(target 85-95%; report this number)")
    print("confusion (rows = true label, cols = judge said):")
    print(f"{'':14s}" + "".join(f"{c:>13s}" for c in levels + ["unparsed"]))
    for a in levels:
        print(f"{a:14s}" + "".join(f"{conf[a][b]:13d}" for b in levels + ["unparsed"]))
    ne = [it for it in items if it["level"] != "intermediate" and it["guess"] != "unparsed"]
    two_way = sum(it["guess"] == it["level"] for it in ne) / max(1, len(ne))
    print(f"novice-vs-expert only (drop intermediate rows): {two_way:.1%} of {len(ne)}")
    # ordinal validity: are errors one-step shifts or extreme swaps?
    ok = [it for it in items if it["guess"] != "unparsed"]
    rank = {l: i for i, l in enumerate(levels)}
    extreme = sum(abs(rank[it["guess"]] - rank[it["level"]]) == 2 for it in ok)
    within1 = sum(abs(rank[it["guess"]] - rank[it["level"]]) <= 1 for it in ok)
    try:
        from scipy.stats import spearmanr
        rho = spearmanr([rank[it["level"]] for it in ok], [rank[it["guess"]] for it in ok])[0]
    except Exception:
        import statistics as _st
        a = [rank[it["level"]] for it in ok]; b = [rank[it["guess"]] for it in ok]
        rho = _st.correlation(a, b) if len(set(b)) > 1 else float("nan")
    print(f"ordinal check: extreme swaps (novice<->expert) {extreme}/{len(ok)}; "
          f"within one step {within1/len(ok):.1%}; rank correlation {rho:.2f}"
          + (f"   [first {nturns} user turns only]" if nturns else ""))
    print("10 raw outputs:")
    for it in items[:10]:
        print(f"  [{it['level']:12s}] -> {it['raw'][:80]!r}")
    print(f"per-item results -> qc_judge_{tag}.jsonl")


def judge():
    correct, n = 0, 0
    sample = random.sample(rows, min(120, len(rows)))
    for d in sample:
        convo = "\n".join(f"USER: {t}" for t in user_text(d))
        prompt = (
            "Below are only the USER turns of a dialogue with an AI assistant.\n"
            "Classify the user's competence on the topic as exactly one of: "
            "novice, intermediate, expert.\nBase this only on terminology precision, "
            "misconceptions, question sophistication, and calibration.\n"
            f"Reply with the single word.\n\n{convo}")
        r = requests.post(OPENROUTER_URL, headers=HEADERS, timeout=120, json={
            "model": JUDGE_MODEL, "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}]})
        guess = r.json()["choices"][0]["message"]["content"].strip().lower()
        n += 1; correct += int(d["level"] in guess)
        time.sleep(0.2)
    print(f"\nBLIND JUDGE AGREEMENT: {correct}/{n} = {correct/n:.1%}  "
          "(target 85-95%; report this number)")


def audit():
    import statistics as st
    by_level = {}
    leaks = 0
    for d in rows:
        wc = [len(t.split()) for t in user_text(d)]
        by_level.setdefault(d["level"], []).extend(wc)
        for t in user_text(d):
            mm = BANNED.search(t)
            if mm:
                leaks += 1
                print(f"LEAK in {d['id']}: match={mm.group(0)!r} :: {t[:90]}")
    print("\nWORD COUNTS per user turn (mean±sd) — must be similar across levels:")
    for lvl, wcs in by_level.items():
        print(f"  {lvl:13s} {st.mean(wcs):5.1f} ± {st.stdev(wcs):4.1f}  (n={len(wcs)})")
    print(f"self-label leaks: {leaks} (must be 0 in main.jsonl — regenerate any hits)")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("audit", "all"): audit()
    if which == "judge_local": judge_local()
    elif which in ("judge", "all"): judge()
    if which in ("read", "all"): human_read()
