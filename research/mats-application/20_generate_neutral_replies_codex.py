"""T2.2 — level-neutral but RESPONSIVE assistant replies for the reversal dialogues
(runs on the LAPTOP with Codex, like 01c).

Why: the neutral-placeholder control (reversal_neutralassistant) replaced the model's
three pre-switch replies with one fixed line. That removes the replies' pitch but also
their content, and a repeated line is off-distribution. So "half of the anchoring is
carried by the content of the model's own replies" rests on a control that changed two
things at once. This dataset changes one: every pre-switch reply is rewritten as a real
answer to the user's question, 40-90 words, but written so it would read the same
whether the asker were a beginner or a professional.

One Codex call per topic (8 dialogues: 4 novice->expert, 4 expert->novice).
  -> data/codex/neutral_<topic>.json  = [{"id": ..., "replies": [r1, r2, r3]}, ...]
Merge -> data/reversal_neutralresponsive.jsonl (same ids/fields as reversal.jsonl, only
the three pre-switch assistant turns replaced; word counts checked).

Usage: python 20_generate_neutral_replies_codex.py ; git add data ; commit ; push
Pod:   python 03_extract_activations.py reversal_neutralresponsive
       PROBE_FILE=probe_e1_pooled.joblib python 17_e2_history_decomposition.py
"""
import json, os
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from config import TOPICS, SAVE_DIR

C = import_module("01c_generate_codex")
OUT = C.OUT
K = 3                                      # first switched user turn (0-indexed)

NEUTRAL_RULES = """
Rewrite ONLY the assistant replies that come BEFORE the user's fourth message (that is,
assistant replies 1, 2 and 3 of each dialogue). Leave everything else untouched.
Each rewritten reply must:
- Actually answer the user's question in that turn, accurately (if the user states
  something wrong, give the correct account plainly; correctness is not pitch).
- Be 40-90 words.
- Be LEVEL-NEUTRAL: it would read identically whether the asker were a complete beginner
  or a professional. So: no analogies, no "simply put", no "in other words", no defining of
  basic terms, no reassurance, no praise, no "great question", and no jargon beyond the
  terms the user's own message already used plus what is strictly needed to answer.
- Never comment on, or adapt to, the user's apparent knowledge, tone, or wording.
Output: write the file {path} as a JSON array of {n} objects {{"id": "<dialogue id>",
"replies": ["...", "...", "..."]}} in the same order as the input. Valid JSON only, no
markdown fences, no commentary. Then re-read the file and check every rule.
"""


def prompt_for(topic, dlgs):
    path = f"{OUT}/neutral_{topic}.json"
    shown = [{"id": r["id"], "messages": r["messages"][: 2 * K]} for r in dlgs]   # first 3 user turns + 3 replies
    p = (f"Below are {len(dlgs)} dialogues (as JSON) between a USER and an AI ASSISTANT about "
         f"{topic}. Only the first three exchanges of each are shown.\n\n{json.dumps(shown, indent=1)}\n"
         + NEUTRAL_RULES.format(path=path, n=len(dlgs)))
    return p, path


def main():
    rev = [json.loads(l) for l in open(f"{SAVE_DIR}/reversal.jsonl")]
    by_topic = {}
    for r in rev:
        by_topic.setdefault(r["topic"], []).append(r)
    jobs = [prompt_for(t, by_topic[t]) for t in TOPICS if t in by_topic]
    with ThreadPoolExecutor(C.PARALLEL) as ex:
        for path, status in ex.map(lambda j: C.run_codex(*j), jobs):
            print(f"  {os.path.basename(path)}: {status}")
    out, bad = [], {}
    for r in rev:
        path = f"{OUT}/neutral_{r['topic']}.json"
        if not os.path.exists(path):
            bad["missing file"] = bad.get("missing file", 0) + 1; continue
        try:
            items = {it["id"]: it["replies"] for it in json.load(open(path))}
        except Exception:
            bad["json error"] = bad.get("json error", 0) + 1; continue
        reps = items.get(r["id"])
        if not reps or len(reps) != K or any(not isinstance(x, str) or not (25 <= len(x.split()) <= 110) for x in reps):
            bad["bad replies"] = bad.get("bad replies", 0) + 1; continue
        msgs = json.loads(json.dumps(r["messages"]))
        ai = [i for i, m in enumerate(msgs) if m["role"] == "assistant"][:K]
        for i, txt in zip(ai, reps):
            msgs[i]["content"] = txt
        out.append({**r, "messages": msgs, "variant": "neutral_responsive"})
    with open(f"{SAVE_DIR}/reversal_neutralresponsive.jsonl", "w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    print(f"reversal_neutralresponsive: kept {len(out)} / {len(rev)}  rejected {bad}")
    print("NEXT (laptop): git add data && git commit -m 'neutral responsive replies' && git push"
          "\nNEXT (pod):    git pull && python 03_extract_activations.py reversal_neutralresponsive && "
          "PROBE_FILE=probe_e1_pooled.joblib python 17_e2_history_decomposition.py")


if __name__ == "__main__":
    main()
