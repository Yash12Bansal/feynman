"""Extract residual-stream activations at end-of-user-turn positions, all layers.

HOW (the newbie-proof way, no hooks needed):
  For user turn t of a dialogue, run the model on the conversation truncated to
  turns 0..t with the chat template's generation prompt appended, request
  output_hidden_states=True, and keep hidden_states[layer][0, -1] — the residual
  stream at the LAST position of every layer.

WHY this position: it's the exact state from which the model would begin writing
its reply — whatever it has inferred about the user must be usable here.
WHY all layers: concepts crystallize at unknown depth; the probe layer-sweep
(04_probe_e1.py) finds where. WHY truncated re-runs instead of one pass + fancy
indexing: chat-template token indexing is the #1 source of silent bugs for
newcomers; O(turns) short forward passes cost only minutes on an A100 and cannot
be wrong. (Optimization is allowed AFTER the science works, never before.)

Run: python 03_extract_activations.py main   (then: reversal, honesty, truth)
Output: activations/<dataset>.pt with
  acts   float16 [n_examples, n_layers+1, d_model]
  meta   list of dicts (dialogue id, topic, level/labels, turn index)
"""
import json, os, sys
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from tqdm import tqdm
from config import MODEL_ID, SAVE_DIR, ACT_DIR, DTYPE

dataset = sys.argv[1] if len(sys.argv) > 1 else "main"
rows = [json.loads(l) for l in open(f"{SAVE_DIR}/{dataset}.jsonl")]

print(f"loading {MODEL_ID} …")
tok = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, torch_dtype=getattr(torch, DTYPE), device_map="cuda")
model.eval()


@torch.no_grad()
def last_pos_all_layers(messages):
    """Residual stream at final position, every layer. [n_layers+1, d_model]"""
    text = tok.apply_chat_template(messages, tokenize=False,
                                   add_generation_prompt=True)
    ids = tok(text, return_tensors="pt").to("cuda")
    out = model(**ids, output_hidden_states=True, use_cache=False)
    return torch.stack([h[0, -1].float() for h in out.hidden_states]).half().cpu()


acts, meta = [], []
for d in tqdm(rows):
    if dataset == "truth":
        # bare statement, framed minimally as a user message the model reads
        msgs = [{"role": "user", "content": d["text"]}]
        acts.append(last_pos_all_layers(msgs))
        meta.append({"topic": d["topic"], "truth": d["truth"], "text": d["text"]})
        continue
    msgs = d["messages"]
    user_idx = [i for i, m in enumerate(msgs) if m["role"] == "user"]
    for t, i in enumerate(user_idx):
        acts.append(last_pos_all_layers(msgs[: i + 1]))
        m = {"id": d["id"], "topic": d["topic"], "turn": t,
             "n_turns": len(user_idx)}
        for k in ("level", "direction", "switch_turn", "claim_true", "voice",
                  "claim_turn", "claim"):
            if k in d:
                m[k] = d[k]
        meta.append(m)

os.makedirs(ACT_DIR, exist_ok=True)
torch.save({"acts": torch.stack(acts), "meta": meta, "model": MODEL_ID},
           f"{ACT_DIR}/{dataset}.pt")
print(f"saved {len(meta)} examples x {acts[0].shape[0]} layers "
      f"x {acts[0].shape[1]} dims -> {ACT_DIR}/{dataset}.pt")
