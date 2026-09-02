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
HEADERS = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
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
    Uses a third family (Phi by default) so the judge is neither the subject
    model (Qwen) nor the generator (Mistral)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    model_id = model_id or os.environ.get("JUDGE_MODEL_LOCAL", "microsoft/phi-4")
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, dtype=torch.bfloat16, device_map="cuda").eval()
    sample = random.sample(rows, min(120, len(rows)))
    correct = 0
    for d in sample:
        convo = "\n".join(f"USER: {t}" for t in user_text(d))
        p = ("Below are only the USER turns of a dialogue with an AI assistant.\n"
             "Classify the user's competence on the topic as exactly one of: "
             "novice, intermediate, expert.\nBase this only on terminology "
             "precision, misconceptions, question sophistication, and calibration."
             f"\nReply with the single word.\n\n{convo}")
        ids = tok(tok.apply_chat_template([{"role": "user", "content": p}],
                                          tokenize=False, add_generation_prompt=True),
                  return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=8, do_sample=False)
        guess = tok.decode(out[0, ids["input_ids"].shape[1]:],
                           skip_special_tokens=True).strip().lower()
        correct += int(d["level"] in guess)
    print(f"\nBLIND JUDGE AGREEMENT (local {model_id}): "
          f"{correct}/{len(sample)} = {correct/len(sample):.1%}  "
          "(target 85-95%; report this number)")


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
            if BANNED.search(t):
                leaks += 1
                print(f"LEAK in {d['id']}: {t[:90]}")
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
