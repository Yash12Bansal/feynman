"""FALLBACK GENERATOR — builds the same five datasets with a LOCAL model on your
own GPU, so the project never blocks on an API balance.

Why this exists: OpenRouter credit purchases via Indian cards go through an RBI
e-mandate that can take a day to settle. The science does not care who writes the
dialogues, as long as it is NOT the model we study (Qwen) — otherwise the subject
model's own stylistic fingerprints could leak the label into the activations we
probe. So we generate with a different family entirely.

Defaults (both ungated on HuggingFace, no license click-through):
  generator : mistralai/Mistral-Small-24B-Instruct-2501  (apache-2.0, ~48GB bf16)
  judge     : microsoft/phi-4                            (MIT, ~28GB bf16)
Three distinct families: Qwen (studied) / Mistral (writes) / Phi (judges).

Speed: batched generation on an A100. ~1000 dialogues takes roughly 30-60 min.
Cost: $0 beyond GPU time you are already paying for.

Usage:
  python 01b_generate_local.py all              # every dataset
  python 01b_generate_local.py main explicit    # a subset
  GEN_MODEL=microsoft/phi-4 python 01b_generate_local.py main   # smaller/faster
"""
import json, os, random, re, sys
import torch
from importlib import import_module
from transformers import AutoModelForCausalLM, AutoTokenizer
from tqdm import tqdm
from config import (TOPICS, LEVELS, N_DIALOGUES_PER_CELL, N_USER_TURNS,
                    USER_TURN_WORDS, SAVE_DIR, DTYPE)

G = import_module("01_generate_dialogues")   # reuse prompt templates + parser
random.seed(0)

GEN_MODEL = os.environ.get("GEN_MODEL", "mistralai/Mistral-Small-24B-Instruct-2501")
BATCH = int(os.environ.get("GEN_BATCH", "8"))


# ---------------------------------------------------------------- prompt build
def build_main(explicit=False):
    name = "explicit" if explicit else "main"
    tasks = []
    for topic, (question, miscs) in TOPICS.items():
        for level, desc in LEVELS.items():
            for i in range(4 if explicit else N_DIALOGUES_PER_CELL):
                override = ("\n- EXCEPTION for this sample: the user's FIRST turn "
                            f"opens by stating their level outright (e.g. 'I'm a "
                            f"complete {level} at this')." if explicit else "")
                p = G.DIALOGUE_PROMPT.format(
                    topic=topic, question=question,
                    n_turns=random.randint(*N_USER_TURNS), level=level,
                    level_desc=desc, wmin=USER_TURN_WORDS[0],
                    wmax=USER_TURN_WORDS[1],
                    misconception_line=(f"Novice misconceptions to draw on: {miscs}"
                                        if level == "novice" else ""),
                    explicit_override=override)
                tasks.append({"prompt": p, "meta": {
                    "id": f"{name}-{topic}-{level}-{i}", "topic": topic,
                    "level": level}})
    return name, tasks, 900


def build_reversal():
    tasks = []
    conds = [("novice", "expert", "use precise terminology and probe edge cases"),
             ("expert", "novice", "voice a common misconception and use vague words")]
    for topic, (question, _) in TOPICS.items():
        for a, b, hint in conds:
            for i in range(4):
                p = G.REVERSAL_PROMPT.format(
                    n_turns=6, topic=topic, question=question, k=3, k1=4,
                    lvl_a=a, desc_a=LEVELS[a], lvl_b=b, desc_b=LEVELS[b],
                    shift_hint=hint, wmin=USER_TURN_WORDS[0],
                    wmax=USER_TURN_WORDS[1])
                tasks.append({"prompt": p, "meta": {
                    "id": f"rev-{topic}-{a}2{b}-{i}", "topic": topic,
                    "direction": f"{a}->{b}", "switch_turn": 3}})
    return "reversal", tasks, 900


# ------------------------------------------------------------------ local model
class LocalLLM:
    def __init__(self, model_id):
        print(f"loading generator {model_id} …")
        self.tok = AutoTokenizer.from_pretrained(model_id)
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.tok.padding_side = "left"      # required for batched decoder generation
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, dtype=getattr(torch, DTYPE), device_map="cuda").eval()

    @torch.no_grad()
    def batch(self, prompts, max_new_tokens=900, temperature=1.0):
        outs = []
        for i in tqdm(range(0, len(prompts), BATCH), desc="generating"):
            chunk = prompts[i:i + BATCH]
            texts = [self.tok.apply_chat_template(
                        [{"role": "user", "content": p}], tokenize=False,
                        add_generation_prompt=True) for p in chunk]
            enc = self.tok(texts, return_tensors="pt", padding=True).to("cuda")
            gen = self.model.generate(**enc, max_new_tokens=max_new_tokens,
                                      do_sample=True, temperature=temperature,
                                      top_p=0.95,
                                      pad_token_id=self.tok.pad_token_id)
            for j in range(len(chunk)):
                outs.append(self.tok.decode(gen[j, enc["input_ids"].shape[1]:],
                                            skip_special_tokens=True))
        return outs


# ------------------------------------------------------------------------ main
def run(which):
    llm = LocalLLM(GEN_MODEL)

    for wanted, builder in [("main", lambda: build_main(False)),
                            ("explicit", lambda: build_main(True)),
                            ("reversal", build_reversal)]:
        if wanted not in which:
            continue
        name, tasks, mx = builder()
        texts = llm.batch([t["prompt"] for t in tasks], max_new_tokens=mx)
        rows, fails = [], 0
        for t, txt in zip(tasks, texts):
            msgs = G.parse_dialogue(txt)
            if msgs:
                rows.append({**t["meta"], "messages": msgs})
            else:
                fails += 1
        print(f"{name}: kept {len(rows)}, parse-failed {fails}")
        G.save(rows, name)

    if "truth" in which or "honesty" in which:
        # 1) claim pairs
        cp = [G.CLAIM_PROMPT.format(n=8, topic=t, question=q)
              for t, (q, _) in TOPICS.items()]
        outs = llm.batch(cp, max_new_tokens=700, temperature=0.8)
        claims = []
        for (topic, _), text in zip(TOPICS.items(), outs):
            for line in text.splitlines():
                m = re.match(r".*TRUE:\s*(.+?)\s*\|\|\|\s*FALSE:\s*(.+)", line)
                if m:
                    claims += [{"topic": topic, "truth": True,
                                "text": m.group(1).strip()},
                               {"topic": topic, "truth": False,
                                "text": m.group(2).strip()}]
        print(f"claims parsed: {len(claims)}")
        G.save(claims, "truth")

        if "honesty" in which:
            by_topic = {}
            for c in claims:
                by_topic.setdefault(c["topic"], []).append(c)
            tasks = []
            for topic, cs in by_topic.items():
                for c in cs[:8]:
                    for voice, vdesc in G.VOICES.items():
                        tasks.append({"prompt": G.HONESTY_PROMPT.format(
                            topic=topic, claim=c["text"], voice=voice,
                            voice_desc=vdesc), "meta": {
                            "topic": topic, "claim": c["text"],
                            "claim_true": c["truth"], "voice": voice,
                            "claim_turn": 2}})
            outs = llm.batch([t["prompt"] for t in tasks], max_new_tokens=800)
            rows, fails = [], 0
            for t, txt in zip(tasks, outs):
                msgs = G.parse_dialogue(txt)
                if msgs and len(msgs) >= 6:
                    rows.append({**t["meta"],
                                 "id": f"hon-{t['meta']['topic']}-"
                                       f"{t['meta']['voice']}-{len(rows)}",
                                 "messages": msgs})
                else:
                    fails += 1
            print(f"honesty: kept {len(rows)}, parse-failed {fails}")
            G.save(rows, "honesty")


if __name__ == "__main__":
    args = sys.argv[1:] or ["all"]
    which = ({"main", "explicit", "reversal", "truth", "honesty"}
             if "all" in args else set(args))
    os.makedirs(SAVE_DIR, exist_ok=True)
    run(which)
    print("\nNEXT: python 02_qc_dialogues.py audit   (then read dialogues yourself)")
