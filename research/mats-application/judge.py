"""One judge entry point for E3/E4 (and QC): OpenRouter if a key is set, else a
LOCAL model. Exists so no experiment can block on API credits.

Backend choice (config.JUDGE_BACKEND):
  openrouter : JUDGE_MODEL (Gemini) via OPENROUTER_API_KEY
  local      : JUDGE_MODEL_LOCAL (microsoft/phi-4 by default), loaded ONCE,
               greedy decoding. Phi is a third family: not Qwen (subject), not
               GPT/Gemma (generators). Fits next to Qwen3-8B on an 80GB card.
Override: JUDGE_BACKEND=local python 06_honesty_e3.py
Whatever backend ran is recorded in results files, so the write-up can say so.
"""
import os, time
import requests
from config import (OPENROUTER_URL, JUDGE_MODEL, JUDGE_BACKEND, JUDGE_MODEL_LOCAL)

_local = {"tok": None, "model": None}


def _local_generate(prompt, max_new):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    if _local["model"] is None:
        print(f"[judge] loading local judge {JUDGE_MODEL_LOCAL} …")
        _local["tok"] = AutoTokenizer.from_pretrained(JUDGE_MODEL_LOCAL)
        _local["model"] = AutoModelForCausalLM.from_pretrained(
            JUDGE_MODEL_LOCAL, dtype=torch.bfloat16, device_map="cuda").eval()
    tok, model = _local["tok"], _local["model"]
    ids = tok(tok.apply_chat_template([{"role": "user", "content": prompt}],
                                      tokenize=False, add_generation_prompt=True),
              return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)


def _openrouter(prompt, max_new, retries=4):
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    for i in range(retries):
        try:
            r = requests.post(OPENROUTER_URL, headers=headers, timeout=120, json={
                "model": JUDGE_MODEL, "temperature": 0.0, "max_tokens": max_new,
                "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  judge retry {i}: {e}"); time.sleep(2 ** i)
    raise RuntimeError("judge call failed")


def judge_text(prompt, max_new=40):
    """Return the judge's raw text for a prompt. Caller parses it."""
    if JUDGE_BACKEND == "openrouter":
        return _openrouter(prompt, max_new).strip()
    return _local_generate(prompt, max_new).strip()


def judge_name():
    return JUDGE_MODEL if JUDGE_BACKEND == "openrouter" else JUDGE_MODEL_LOCAL
