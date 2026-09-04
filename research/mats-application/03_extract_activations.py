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

Run: python 03_extract_activations.py main   (then: explicit, reversal, honesty, truth,
     reversal_postonly — the H2c history-vs-writing control,
     truth_lastword + honesty_claimpos — the H3 claim-position variant)
     SAVE_DIR=data_gemma python 03_extract_activations.py main   -> main_gemma.pt
     (the second generator's activations feed the cross-generator transfer test)
Output: activations/<dataset>[_<generator>].pt with
  acts   float16 [n_examples, n_layers+1, d_model]
  meta   list of dicts (dialogue id, topic, level/labels, turn index)
"""
import json, os, sys
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from tqdm import tqdm
from config import MODEL_ID, SAVE_DIR, ACT_DIR, DTYPE, chat_text, act_path

dataset = sys.argv[1] if len(sys.argv) > 1 else "main"
# "reversal_postonly": the reversal dialogues with everything BEFORE the switch cut
# off, so the model sees only the post-switch turns. Control for H2c: if isolated
# post-switch expert turns score like a lifelong expert, the anchoring gap in the
# full dialogue is caused by the history (real anchoring); if they score low even
# in isolation, the generator simply wrote weaker post-switch experts.
# "honesty_claimpos": snapshot at the END OF THE CLAIM SENTENCE inside the claim turn
# (not at the end of the turn). "truth_lastword": bare statements, snapshot at the
# statement's last token (not at the template's end). Together they are the
# pre-registered H3 fallback: the truth signal may not travel to the end of a turn
# that continues with reasoning and a question. Both are extracted so E3 reports
# both positions.
# "reversal_userhistory": keeps the user's pre-switch turns but REMOVES the
# assistant's pre-switch replies (the novice turns are merged into the first
# post-switch user message). Splits the anchoring source: the user's own words vs
# the model's earlier novice-pitched explanations sitting in the context.
# "reversal_neutralassistant": every turn kept in place, but the assistant's
# pre-switch replies are replaced by a fixed neutral placeholder with no pitch.
# Separates "content of the model's own earlier replies" from "multi-turn structure".
SRC = {"reversal_postonly": "reversal", "honesty_claimpos": "honesty",
       "truth_lastword": "truth", "reversal_userhistory": "reversal",
       "reversal_neutralassistant": "reversal", "linking_claimpos": "linking"}
# "<name>_claimpos" works for any dataset whose rows carry claim / claim_turn
# (honesty, linking): snapshot at the end of the claim sentence.
NEUTRAL = "Thanks, that's a good question. Let's keep going."
src = SRC.get(dataset, dataset)
rows = [json.loads(l) for l in open(f"{SAVE_DIR}/{src}.jsonl")]
import re
skipped = 0

print(f"loading {MODEL_ID} …")
tok = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, dtype=getattr(torch, DTYPE), device_map="cuda")
model.eval()


@torch.no_grad()
def last_pos_all_layers(messages):
    """Residual stream at final position, every layer. [n_layers+1, d_model]"""
    ids = tok(chat_text(tok, messages), return_tensors="pt").to("cuda")
    out = model(**ids, output_hidden_states=True, use_cache=False)
    return torch.stack([h[0, -1].float() for h in out.hidden_states]).half().cpu()


@torch.no_grad()
def at_char_end(messages, char_end_in_last_msg):
    """Residual stream (all layers) at the last token that ends at or before a
    character offset inside the LAST message's content. Uses the tokenizer's
    offset mapping on the serialized chat text, so template tokens are handled."""
    text = chat_text(tok, messages)
    last = messages[-1]["content"]
    start = text.rfind(last)
    assert start >= 0, "message content not found in serialized chat text"
    char_end = start + char_end_in_last_msg
    enc = tok(text, return_tensors="pt", return_offsets_mapping=True)
    offsets = enc.pop("offset_mapping")[0].tolist()
    cands = [i for i, (a, b) in enumerate(offsets) if b > 0 and b <= char_end]
    ti = max(cands)
    out = model(**enc.to("cuda"), output_hidden_states=True, use_cache=False)
    return torch.stack([h[0, ti].float() for h in out.hidden_states]).half().cpu(), ti


def claim_sentence_end(turn_text, claim):
    """Character offset just after the sentence that contains the claim. Exact
    match first, then the first 60% of the claim (generators paraphrase tails)."""
    lo = turn_text.lower()
    pos = lo.find(claim.lower())
    if pos < 0:
        pos = lo.find(claim[: int(len(claim) * 0.6)].lower())
    if pos < 0:
        return None
    m = re.search(r"[.!?]", turn_text[pos + 10:])
    return pos + 10 + m.end() if m else len(turn_text)


acts, meta = [], []
for d in tqdm(rows):
    if dataset == "truth_lastword":
        msgs = [{"role": "user", "content": d["text"]}]
        x, ti = at_char_end(msgs, len(d["text"].rstrip()))
        acts.append(x)
        meta.append({"topic": d["topic"], "truth": d["truth"], "text": d["text"],
                     "position": "statement_last_token", "token_index": ti})
        continue
    if dataset.endswith("_claimpos"):
        msgs = d["messages"]
        user_idx = [i for i, m in enumerate(msgs) if m["role"] == "user"]
        ci = user_idx[d["claim_turn"]]
        end = claim_sentence_end(msgs[ci]["content"], d["claim"])
        if end is None:
            skipped += 1; continue
        x, ti = at_char_end(msgs[: ci + 1], end)
        acts.append(x)
        meta.append({"id": d["id"], "topic": d["topic"], "turn": d["claim_turn"],
                     "claim_turn": d["claim_turn"], "claim_true": d["claim_true"],
                     "voice": d["voice"], "claim": d["claim"],
                     "position": "claim_sentence_end", "token_index": ti})
        continue
    if dataset == "truth":
        # bare statement, framed minimally as a user message the model reads
        msgs = [{"role": "user", "content": d["text"]}]
        acts.append(last_pos_all_layers(msgs))
        meta.append({"topic": d["topic"], "truth": d["truth"], "text": d["text"]})
        continue
    msgs = d["messages"]
    user_idx = [i for i, m in enumerate(msgs) if m["role"] == "user"]
    t0 = 0
    if dataset == "reversal_postonly":
        k = d["switch_turn"]
        msgs = msgs[user_idx[k]:]              # starts at the first switched user turn
        t0, user_idx = k, [i for i, m in enumerate(msgs) if m["role"] == "user"]
    if dataset == "reversal_neutralassistant":
        k = d["switch_turn"]
        msgs = [({"role": "assistant", "content": NEUTRAL} if (m["role"] == "assistant" and i < user_idx[k]) else m)
                for i, m in enumerate(msgs)]
    if dataset == "reversal_userhistory":
        k = d["switch_turn"]
        pre_user = [msgs[i]["content"] for i in user_idx[:k]]
        post = msgs[user_idx[k]:]
        merged = "\n\n".join(pre_user + [post[0]["content"]])
        msgs = [{"role": "user", "content": merged}] + post[1:]
        t0, user_idx = k, [i for i, m in enumerate(msgs) if m["role"] == "user"]
    for t, i in enumerate(user_idx):
        acts.append(last_pos_all_layers(msgs[: i + 1]))
        m = {"id": d["id"], "topic": d["topic"], "turn": t0 + t,
             "n_turns": t0 + len(user_idx)}
        for k in ("level", "direction", "switch_turn", "claim_true", "voice",
                  "claim_turn", "claim"):
            if k in d:
                m[k] = d[k]
        meta.append(m)

os.makedirs(ACT_DIR, exist_ok=True)
out_path = act_path(dataset)          # e.g. activations/main.pt or main_gemma.pt
torch.save({"acts": torch.stack(acts), "meta": meta, "model": MODEL_ID,
            "source": f"{SAVE_DIR}/{dataset}.jsonl"}, out_path)
print(f"saved {len(meta)} examples x {acts[0].shape[0]} layers "
      f"x {acts[0].shape[1]} dims -> {out_path}" + (f"  (skipped {skipped}: claim not found)" if skipped else ""))
