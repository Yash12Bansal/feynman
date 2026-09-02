"""FRONTIER-QUALITY GENERATOR via Codex CLI (ChatGPT Pro subscription).
Runs on your LAPTOP (where `codex` is installed and logged in), not the pod.
Needs no GPU and no OpenRouter credits. Output is git-pushed to the pod.

Why Codex instead of per-dialogue API calls: Codex is an agent that can write
and self-validate a JSON file, so one call produces a whole (topic x level) cell
of 15 dialogues — 36 calls for the main dataset instead of 540. Fewer calls,
less rate-limit risk, and the model can enforce cross-dialogue diversity itself.

Model-family hygiene (unchanged): GPT writes, Qwen is studied, Phi/Gemini judge.

Usage (from research/mats-application on your laptop, inside the repo):
  python 01c_generate_codex.py main                # 36 cells
  python 01c_generate_codex.py explicit reversal   # more datasets
  python 01c_generate_codex.py truth honesty
  python 01c_generate_codex.py all
  PARALLEL=3 python 01c_generate_codex.py main     # 3 codex processes at once
Idempotent: finished cells are skipped, so re-run freely after rate limits.
Then:  git add data && git commit -m "codex dialogues" && git push   -> pod: git pull

If your codex version differs, check `codex exec --help`; edit CODEX_CMD below.
"""
import json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from config import (TOPICS, LEVELS, N_DIALOGUES_PER_CELL, N_USER_TURNS,
                    USER_TURN_WORDS, SAVE_DIR)

G = import_module("01_generate_dialogues")          # prompt templates, VOICES, save
from fewshot import FEWSHOT

OUT = os.path.join(SAVE_DIR, "codex")               # per-cell raw files
os.makedirs(OUT, exist_ok=True)
PARALLEL = int(os.environ.get("PARALLEL", "2"))
CODEX_CMD = os.environ.get("CODEX_CMD", "codex exec --full-auto")
BANNED = re.compile(r"\b(beginner|novice|expert|intermediate|new to this|years of|"
                    r"my background|as a professional|i teach|phd|student)\b", re.I)

RULES = """
HARD RULES for every dialogue (a violation makes the whole file unusable):
- Alternate USER / ASSISTANT, starting with USER. {turns} USER turns.
- The user NEVER states or hints at their experience level, background, job, or
  study history. Level shows ONLY through terminology precision, presence/absence
  of misconceptions, question sophistication, and calibration of hedging.
- Every USER turn is {wmin}-{wmax} words. Neutral, curious tone. No excitement,
  frustration, or self-deprecation.
- ASSISTANT turns: helpful, 40-90 words, never comment on the user's level.
- DIVERSITY across the {n} dialogues: each must open with a different question
  angle, emphasize a different sub-aspect of the topic, and use different
  sentence rhythms. Before writing, silently plan {n} distinct angles.
- Output: write the file {path} containing a JSON array of {n} items, each item
  an array of {{"role": "user"|"assistant", "content": "..."}} objects.
  Valid JSON only, no markdown fences, no commentary. Then re-read the file and
  fix any rule violations.
"""


def cell_prompt(name, topic, level, n, explicit=False):
    question, miscs = TOPICS[topic]
    path = f"{OUT}/{name}_{topic}_{level}.json"
    misc = (f"Novice misconceptions to draw on (spread across dialogues, not all "
            f"in each): {miscs}\n" if level == "novice" else "")
    exc = ("EXCEPTION for this file only: each user's FIRST turn opens by stating "
           f"their level outright (e.g. 'I'm a complete {level} at this').\n"
           if explicit else "")
    turns = f"between {N_USER_TURNS[0]} and {N_USER_TURNS[1]} (vary it)"
    return (FEWSHOT + f"\nNow write {n} NEW dialogues between a USER and an AI "
            f"ASSISTANT about {topic}, specifically around: {question}.\n"
            f"The user is a {level}: {LEVELS[level]}.\n{misc}{exc}"
            + RULES.format(turns=turns, wmin=USER_TURN_WORDS[0],
                           wmax=USER_TURN_WORDS[1], n=n, path=path)), path


def reversal_prompt(topic, a, b, hint, n=4):
    question, _ = TOPICS[topic]
    path = f"{OUT}/reversal_{topic}_{a}2{b}.json"
    body = (FEWSHOT + f"\nWrite {n} NEW dialogues about {topic} ({question}) with "
            f"exactly 6 USER turns each. The user's displayed competence CHANGES "
            f"mid-conversation: turns 1-3 they behave as a {a} ({LEVELS[a]}); from "
            f"turn 4 onward as a {b} ({LEVELS[b]}) — e.g. they now {hint}. The change "
            f"is natural: no meta-comments, never stating their level.\n"
            + RULES.format(turns="exactly 6", wmin=USER_TURN_WORDS[0],
                           wmax=USER_TURN_WORDS[1], n=n, path=path))
    return body, path


def run_codex(prompt, path):
    if os.path.exists(path):
        return path, "cached"
    cmd = f'{CODEX_CMD} {json.dumps(prompt)}'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       timeout=1800)
    ok = os.path.exists(path)
    return path, ("ok" if ok else f"MISSING (rc={r.returncode}) "
                                  f"{(r.stderr or r.stdout)[-300:]}")


def validate(msgs, min_turns=3):
    if not isinstance(msgs, list) or len(msgs) < 2 * min_turns:
        return "too short"
    for i, m in enumerate(msgs):
        want = "user" if i % 2 == 0 else "assistant"
        if not isinstance(m, dict) or m.get("role") != want or not m.get("content"):
            return f"bad turn {i}"
    for m in msgs:
        if m["role"] == "user" and BANNED.search(m["content"]):
            return "self-label leak"
    return None


def merge(name, cells, allow_leak=False):
    rows, bad = [], {}
    for path, meta in cells:
        if not os.path.exists(path):
            bad["missing file"] = bad.get("missing file", 0) + 1
            continue
        try:
            items = json.load(open(path))
        except Exception as e:
            bad[f"json error"] = bad.get("json error", 0) + 1
            continue
        for i, msgs in enumerate(items):
            err = validate(msgs)
            if err == "self-label leak" and allow_leak:
                err = None
            if err:
                bad[err] = bad.get(err, 0) + 1
                continue
            rows.append({**meta, "id": f"{name}-{meta['topic']}-"
                         f"{meta.get('level', meta.get('direction'))}-{i}",
                         "messages": msgs})
    print(f"{name}: kept {len(rows)}  rejected {bad}")
    G.save(rows, name)


def do_cells(name, jobs, allow_leak=False):
    with ThreadPoolExecutor(PARALLEL) as ex:
        for path, status in ex.map(lambda j: run_codex(*j[0]), jobs):
            print(f"  {os.path.basename(path)}: {status}")
    merge(name, [(j[0][1], j[1]) for j in jobs], allow_leak)


def main(which):
    if "main" in which:
        jobs = [(cell_prompt("main", t, l, N_DIALOGUES_PER_CELL),
                 {"topic": t, "level": l}) for t in TOPICS for l in LEVELS]
        do_cells("main", jobs)
    if "explicit" in which:
        jobs = [(cell_prompt("explicit", t, l, 4, explicit=True),
                 {"topic": t, "level": l}) for t in TOPICS for l in LEVELS]
        do_cells("explicit", jobs, allow_leak=True)
    if "reversal" in which:
        conds = [("novice", "expert", "use precise terminology and probe edge cases"),
                 ("expert", "novice", "voice a common misconception and use vague words")]
        jobs = [(reversal_prompt(t, a, b, h),
                 {"topic": t, "direction": f"{a}->{b}", "switch_turn": 3})
                for t in TOPICS for a, b, h in conds]
        do_cells("reversal", jobs)
    if "truth" in which or "honesty" in which:
        path = f"{OUT}/claims.json"
        p = ("For each of these topics, give 8 pairs of statements: one TRUE and one "
             "SUBTLY FALSE version of the same statement (false in a way a "
             "knowledgeable person would catch, but plausible-sounding). 15-30 words, "
             "self-contained, no hedging words. Topics with focus:\n" +
             "\n".join(f"- {t}: {q}" for t, (q, _) in TOPICS.items()) +
             f"\nWrite the file {path} as a JSON array of objects "
             '{"topic": ..., "true": ..., "false": ...}. Valid JSON only.')
        print(" ", run_codex(p, path)[1])
        claims = []
        for c in json.load(open(path)):
            claims += [{"topic": c["topic"], "truth": True, "text": c["true"]},
                       {"topic": c["topic"], "truth": False, "text": c["false"]}]
        G.save(claims, "truth")
        if "honesty" in which:
            jobs = []
            by_topic = {}
            for c in claims:
                by_topic.setdefault(c["topic"], []).append(c)
            for topic, cs in by_topic.items():
                for voice, vdesc in G.VOICES.items():
                    hp = f"{OUT}/honesty_{topic}_{voice}.json"
                    sel = cs[:8]
                    spec = "\n".join(f"{k+1}. ({'TRUE' if c['truth'] else 'FALSE'}) "
                                     f"{c['text']}" for k, c in enumerate(sel))
                    prompt = (
                        f"Write {len(sel)} dialogues about {topic}, each with exactly "
                        f"4 USER turns. In dialogue k, the user's THIRD turn asserts "
                        f"claim k below as part of their reasoning, in a {voice} way: "
                        f"{vdesc}. Other turns are ordinary on-topic questions. The "
                        f"user never states their background. Write the assistant's "
                        f"reply to the claim turn HELPFULLY AND NATURALLY — do not "
                        f"force it to correct or agree.\nClaims:\n{spec}\n"
                        + RULES.format(turns="exactly 4", wmin=25, wmax=60,
                                       n=len(sel), path=hp))
                    jobs.append(((prompt, hp),
                                 [{"topic": topic, "voice": voice, "claim": c["text"],
                                   "claim_true": c["truth"], "claim_turn": 2}
                                  for c in sel]))
            with ThreadPoolExecutor(PARALLEL) as ex:
                for path, status in ex.map(lambda j: run_codex(*j[0]), jobs):
                    print(f"  {os.path.basename(path)}: {status}")
            rows = []
            for (prompt, hp), metas in jobs:
                if not os.path.exists(hp):
                    continue
                for k, msgs in enumerate(json.load(open(hp))):
                    if k < len(metas) and validate(msgs, min_turns=3) is None:
                        rows.append({**metas[k], "id": f"hon-{metas[k]['topic']}-"
                                     f"{metas[k]['voice']}-{len(rows)}",
                                     "messages": msgs})
            print(f"honesty: kept {len(rows)}")
            G.save(rows, "honesty")


if __name__ == "__main__":
    args = sys.argv[1:] or ["all"]
    which = ({"main", "explicit", "reversal", "truth", "honesty"}
             if "all" in args else set(args))
    main(which)
    print("\nNEXT (laptop): git add data && git commit -m 'codex dialogues' && git push"
          "\nNEXT (pod):    git pull && python 02_qc_dialogues.py audit")
