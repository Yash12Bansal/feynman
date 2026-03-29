# The Complete Engineering Guide to Fine-Tuning LLMs

## Context

Engineering-level reference for fine-tuning: data preparation (formats, types, quality), training code (Unsloth, TRL, Axolotl, API providers), LoRA mechanics, hyperparameter tuning, evaluation, how world-class orgs do it (Meta, OpenAI, Anthropic, Google, ETH Zurich), deployment, and failure modes. Everything an engineer needs to go from raw data to a deployed fine-tuned model.

---

# Part 1: Data — The Thing That Actually Matters

## 1.1 Data Formats

There are 5 formats you'll encounter. They all encode the same thing (conversation turns) differently.

### OpenAI JSONL (used by: OpenAI API, Together AI)

```json
{"messages": [
  {"role": "system", "content": "You are a Socratic math tutor."},
  {"role": "user", "content": "What is the derivative of x²?"},
  {"role": "assistant", "content": "Before I tell you — what rule do you think applies when you see a variable raised to a power?"}
]}
```

Multi-turn — just keep alternating user/assistant:
```json
{"messages": [
  {"role": "system", "content": "You are a Socratic math tutor."},
  {"role": "user", "content": "What is the derivative of x²?"},
  {"role": "assistant", "content": "What rule do you think applies when you see a variable raised to a power?"},
  {"role": "user", "content": "The power rule?"},
  {"role": "assistant", "content": "Exactly. So if the power rule says bring the exponent down and reduce it by 1 — what do you get for x²?"}
]}
```

With tool/function calling:
```json
{"messages": [
  {"role": "user", "content": "Draw the force diagram for a block on an incline."},
  {"role": "assistant", "tool_calls": [
    {"id": "call_1", "type": "function", "function": {
      "name": "draw_diagram",
      "arguments": "{\"type\": \"force_diagram\", \"objects\": [\"block\", \"incline\"], \"forces\": [\"gravity\", \"normal\", \"friction\"]}"
    }}
  ]},
  {"role": "tool", "tool_call_id": "call_1", "content": "{\"status\": \"rendered\"}"},
  {"role": "assistant", "content": "I've drawn the three forces acting on the block. Which one do you think acts parallel to the surface?"}
]}
```

One JSONL line per conversation. UTF-8. Double quotes only.

### HuggingFace Conversational (used by: TRL, Unsloth)

Identical structure to OpenAI format — `messages` array with `role`/`content` dicts. This is the target format for all open-source training.

```json
{"messages": [
  {"role": "user", "content": "What color is the sky?"},
  {"role": "assistant", "content": "It is blue."}
]}
```

Or prompt-completion format (loss computed on completion only by default):
```json
{
  "prompt": [{"role": "user", "content": "What color is the sky?"}],
  "completion": [{"role": "assistant", "content": "It is blue."}]
}
```

### ShareGPT (used by: LLaMA-Factory, older Axolotl, community datasets)

```json
{"conversations": [
  {"from": "human", "value": "What is photosynthesis?"},
  {"from": "gpt", "value": "Photosynthesis is the process by which plants convert light energy..."}
],
 "system": "You are a biology teacher."
}
```

**Hard constraint:** `human` must appear in odd positions (1st, 3rd, 5th...), `gpt` in even positions. Violating this causes silent data corruption in LLaMA-Factory.

**ShareGPT is being deprecated.** Axolotl now recommends `chat_template` format. Unsloth provides `standardize_sharegpt()` to convert.

### Alpaca (used by: simple instruction-following tasks)

```json
{
  "instruction": "Explain the Pythagorean theorem using a real-world example.",
  "input": "",
  "output": "Imagine you're standing at a corner of a rectangular field...",
  "system": "You are a math teacher who uses everyday analogies."
}
```

Use Alpaca for single-turn instruction tasks. Use conversational format for anything multi-turn.

### ChatML (template, not a storage format)

ChatML is the Jinja2 template that converts `{role, content}` JSON into the token sequence the model actually sees:

```
<|im_start|>system
You are a Socratic math tutor.<|im_end|>
<|im_start|>user
What is the derivative of x²?<|im_end|>
<|im_start|>assistant
What rule do you think applies here?<|im_end|>
```

You store data as JSON. The chat template converts it to this during tokenization.

### Provider-Specific Notes

| Provider | Format | Notes |
|---|---|---|
| OpenAI | Their JSONL | Min 10 examples, recommended 50+ |
| Together AI | Same JSONL or Parquet | Has `train_on_inputs` param ("auto" masks user msgs) |
| Axolotl | YAML config points to dataset | Modern: `type: chat_template`. Deprecated: ShareGPT |

---

## 1.2 Chat Templates — The Silent Killer

A chat template is a Jinja2 string in the tokenizer config that converts JSON messages → token sequence. **Using the wrong template causes silent performance degradation.** No error. No exception. Just worse outputs.

Each model family has its own template:

**Qwen (ChatML):**
```
<|im_start|>system\n{content}<|im_end|>\n<|im_start|>user\n{content}<|im_end|>\n<|im_start|>assistant\n
```

**Llama 3:**
```
<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{content}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{content}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n
```

**Mistral:**
```
[INST] {user_msg} [/INST]{assistant_msg}</s>[INST] {user_msg_2} [/INST]
```

**The rule:** Always use `tokenizer.apply_chat_template(messages, tokenize=False)` and verify the output matches what the base model was trained with. When fine-tuning further, the template must stay EXACTLY the same.

```python
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
formatted = tokenizer.apply_chat_template(messages, tokenize=False)
print(formatted)  # Verify this looks right before training
```

---

## 1.3 Loss Masking (train_on_inputs)

When computing cross-entropy loss during SFT, should you include prompt tokens or only assistant response tokens?

**Mechanically:** PyTorch's `CrossEntropyLoss` has `ignore_index=-100`. Tokens with label `-100` are excluded from loss. When you mask prompts, all user/system message labels become `-100`, only assistant tokens retain their IDs.

**The answer: mask prompt tokens.** Set `train_on_inputs: false`.

| Framework | Default | How to mask |
|---|---|---|
| Axolotl | Masked (good) | `train_on_inputs: false` |
| Unsloth | Masked (good) | Default behavior |
| TRL | NOT masked | Use `DataCollatorForCompletionOnlyLM` |
| Together AI | `"auto"` | Automatically masks user msgs in chat format |

Research finding: masking helps for short completions, is neutral for long completions. Always mask — it's the safer default.

---

## 1.4 System Prompts in Training Data

**Yes, include them.** If your model uses system prompts at inference time, it MUST see them during training. Otherwise → distribution shift → silent quality degradation.

Google's LearnLM specifically used "pedagogical instruction following" — every training conversation started with a system instruction describing desired teaching behaviors. This was core to their approach.

**Best practice:** Vary your system prompts across examples. Some with detailed system prompts, some with short ones, some with none. This teaches robustness to system prompt variation.

---

## 1.5 Tokenization Gotchas

### EOS Token as Pad Token — The #1 Mistake

Many models (Llama 2) ship without a dedicated pad token. The naive fix:
```python
tokenizer.pad_token = tokenizer.eos_token  # WRONG. DO NOT DO THIS.
```

**Why it breaks:** Pad tokens are masked during training (attention_mask=0, label=-100). If EOS=PAD, the model learns to ignore EOS. At inference → generates endlessly, never stops.

**Correct fixes:**
```python
# Option 1: Use UNK token (Meta's approach)
tokenizer.pad_token = tokenizer.unk_token

# Option 2: Add dedicated pad token
tokenizer.add_special_tokens({'pad_token': '[PAD]'})
model.resize_token_embeddings(len(tokenizer))  # CRITICAL
```

Llama 3 and Qwen 2.5 ship with dedicated pad tokens — this is mainly a Llama 2 / older model issue.

### Left-Padding vs Right-Padding

```
Right-pad (training): [BOS] The sky is blue [EOS] [PAD] [PAD]
Left-pad  (batch inference): [PAD] [PAD] [BOS] The sky is blue [EOS]
```

- **Training: RIGHT-padding** (always)
- **Batch inference: LEFT-padding** (so generated tokens align at right edge)

```python
tokenizer.padding_side = "right"  # For training
tokenizer.padding_side = "left"   # For batch inference
```

### Duplicate BOS Tokens

Chat template adds BOS + `tokenizer(text, add_special_tokens=True)` adds another → `<s><s>`.

Fix: `dataset_kwargs={"add_special_tokens": False}` in SFTTrainer, or verify with `tokenizer.apply_chat_template()`.

### Resize Embeddings When Adding Tokens

If you add ANY new special token, you MUST resize:
```python
tokenizer.add_special_tokens({'pad_token': '[PAD]'})
model.resize_token_embeddings(len(tokenizer))  # Forgetting this → index errors
```

---

## 1.6 Preference Data (DPO/ORPO)

### Format

**HuggingFace TRL (recommended — explicit prompt):**
```json
{
  "prompt": [{"role": "user", "content": "I don't understand derivatives."}],
  "chosen": [{"role": "assistant", "content": "Let's build intuition first. Imagine you're driving a car — the speedometer shows your rate of change of position. That's what a derivative is."}],
  "rejected": [{"role": "assistant", "content": "The derivative of f(x) is defined as the limit of [f(x+h)-f(x)]/h as h approaches 0."}]
}
```

**OpenAI DPO format:**
```json
{
  "input": {"messages": [{"role": "user", "content": "I don't understand derivatives."}]},
  "preferred_output": [{"role": "assistant", "content": "Let's build intuition first..."}],
  "non_preferred_output": [{"role": "assistant", "content": "The derivative is defined as..."}]
}
```

### How to Generate Chosen vs Rejected

**Method 1: Multiple sampling + scoring** (best for verifiable domains)
1. Generate 4+ responses per prompt from your SFT model
2. Score via rule-based eval (regex for math, unit tests for code)
3. Correct → chosen, incorrect → rejected
4. Skip prompts lacking both

**Method 2: AI-as-judge** (best for subjective quality)
- Generate responses, use Claude/GPT-4 to evaluate against principles
- Cost: <$0.01/comparison vs $1+ for human annotators
- Anthropic's Constitutional AI uses this at scale

**Method 3: Human annotation** (gold standard)
- Meta Llama 3: annotators ranked outputs AND edited them ("edited > chosen > rejected" — three tiers)
- 40+ labelers with screening tests

**Method 4: Reward model scoring**
- Train or use existing reward model to score generations
- Highest → chosen, lowest → rejected

---

## 1.7 Data Quality Engineering — How the Best Do It

### The LIMA Insight

1,000 carefully curated examples on LLaMA-65B, no RLHF → outperformed RLHF-trained DaVinci003 and 52K-example Alpaca.

**The lesson: 500 perfect examples beat 50,000 mediocre ones.** SFT teaches format/style, not knowledge. Knowledge is from pretraining. Quality >> quantity.

### Meta's Llama 3 Pipeline

1. Heuristic filters (unsafe sites, PII, adult content)
2. Custom HTML parser for boilerplate removal
3. Text quality classifiers (trained using Llama 2 — "surprisingly good at identifying high-quality data")
4. Semantic deduplication: cluster with RoBERTa embeddings → greedy selection by quality × difficulty, keeping only examples below cosine similarity threshold to selected set
5. Difficulty scoring: Llama 3 70B tags "intentions" per example — more intentions = more complex
6. Domain-specific: static analysis for code, unit test execution, API executability for tool use

### Google's LearnLM Pipeline

1. SFT: conversations with pedagogical system instructions, co-trained with Gemini's standard post-training mix
2. Reward model: 228 pedagogy experts (advanced degrees + 2yr tutoring experience) label model samples for pedagogical adherence
3. RLHF: reward model scores policy samples

**Key finding:** "SFT improves pedagogical instruction following somewhat, RL is significantly more effective."

### Microsoft Phi-4's Data-First Approach

- Tune one domain at a time, NOT all mixed together
- Pick highest-value domain first, craft small focused SFT dataset
- Use "teachable" edge examples that push the model's reasoning
- Combine with synthetic rewrites

### Data Selection: The "Fit" Principle

2025 paper: SFT is most effective when data aligns with the model's pretrained distribution. Gather responses from various sources, select ones with highest normalized probability under the pretrained model. **The best SFT data is data the model "almost" already knows how to produce.**

---

# Part 2: Training Code

## 2.1 Unsloth — The Recommended Starting Point

Free, Apache 2.0. 2-5x faster, 60-70% less VRAM. Single GPU only.

### Complete SFT Pipeline

```python
from datasets import load_dataset
from transformers import TrainingArguments
from trl import SFTTrainer
from unsloth import FastLanguageModel, is_bfloat16_supported
from unsloth.chat_templates import get_chat_template

# ── Load Model ──
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-7B-Instruct-bnb-4bit",  # Pre-quantized
    max_seq_length=2048,
    load_in_4bit=True,
    dtype=None,  # Auto-detect (bf16 on Ampere+)
)

# ── Add LoRA Adapters ──
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=16,
    lora_dropout=0,                                # Unsloth recommends 0
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    use_rslora=True,
    use_gradient_checkpointing="unsloth",          # String "unsloth" = optimized, 30% less VRAM
    bias="none",
)

# ── Chat Template ──
tokenizer = get_chat_template(tokenizer, chat_template="chatml")

# ── Prepare Dataset ──
dataset = load_dataset("your_dataset", split="train")

def apply_template(examples):
    text = [tokenizer.apply_chat_template(msg, tokenize=False, add_generation_prompt=False)
            for msg in examples["messages"]]
    return {"text": text}

dataset = dataset.map(apply_template, batched=True)

# ── Train ──
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=2048,
    packing=True,                                   # Pack multiple short examples per sequence
    args=TrainingArguments(
        learning_rate=3e-4,
        lr_scheduler_type="cosine",
        per_device_train_batch_size=8,
        gradient_accumulation_steps=2,               # Effective batch = 16
        num_train_epochs=1,
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        optim="adamw_8bit",
        weight_decay=0.05,
        warmup_steps=10,
        logging_steps=1,
        output_dir="output",
        save_strategy="steps",
        save_steps=100,
        eval_strategy="steps",
        eval_steps=100,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
    ),
)
trainer.train()
```

### DPO with Unsloth

```python
from trl import DPOConfig, DPOTrainer

# Load model same as above, then:
training_args = DPOConfig(
    output_dir="./dpo_output",
    beta=0.1,                     # DPO temperature (0.1-0.5)
    per_device_train_batch_size=4,
    learning_rate=5e-6,           # 40x LOWER than SFT
    num_train_epochs=3,
    max_prompt_length=512,
    max_length=1024,
)

dpo_trainer = DPOTrainer(
    model,
    ref_model=None,               # With LoRA, None = frozen base as reference
    args=training_args,
    train_dataset=train_dataset,  # Must have prompt/chosen/rejected columns
    tokenizer=tokenizer,
)
dpo_trainer.train()
```

### ORPO with Unsloth (SFT + Preference in One Pass)

```python
from trl import ORPOTrainer, ORPOConfig

trainer = ORPOTrainer(
    model=model,
    args=ORPOConfig(
        learning_rate=8e-6,
        beta=0.1,
        lr_scheduler_type="cosine",
        output_dir="./orpo_output",
        num_train_epochs=3,
    ),
    train_dataset=train_dataset,  # Same format as DPO (prompt/chosen/rejected)
    tokenizer=tokenizer,
)
trainer.train()
```

### Saving & Exporting

```python
# Save LoRA adapter only
model.save_pretrained("lora_model")

# Merge LoRA into base and save as 16-bit (for further training or vLLM serving)
model.save_pretrained_merged("merged_model", tokenizer, save_method="merged_16bit")

# Export to GGUF for Ollama / llama.cpp
model.save_pretrained_gguf("gguf_dir", tokenizer, quantization_method="q4_k_m")

# Push to HuggingFace Hub
model.push_to_hub_merged("username/model-name", tokenizer, save_method="merged_16bit")
model.push_to_hub_gguf("username/model-GGUF", tokenizer, quantization_method="q4_k_m")
```

### Common Unsloth Mistakes

1. `lora_dropout > 0` — Unsloth recommends 0
2. `use_gradient_checkpointing=True` instead of `"unsloth"` — the string enables their optimized version
3. Forgetting `FastLanguageModel.for_inference(model)` before inference — enables 2x faster native inference
4. `max_seq_length` too high for testing — start at 2048
5. Using both `load_in_4bit` and `load_in_16bit`

---

## 2.2 Axolotl — When You Need Multi-GPU

YAML-driven, supports FSDP/DeepSpeed, 30+ model architectures. Use when Unsloth's single-GPU limit isn't enough.

### When to use which

| | Unsloth | Axolotl |
|---|---|---|
| Single GPU speed | Best (2x faster) | Standard |
| Multi-GPU | Not supported | First-class (FSDP/DeepSpeed) |
| Config style | Python code | YAML |
| Experiment iteration | Rewrite code | Change YAML |

### YAML Config Example (QLoRA)

```yaml
base_model: Qwen/Qwen2.5-7B-Instruct
load_in_4bit: true
adapter: qlora
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
lora_target_modules:
  - q_proj
  - k_proj
  - v_proj
  - o_proj
  - gate_proj
  - up_proj
  - down_proj

chat_template: chatml
datasets:
  - path: my_teaching_data.jsonl
    type: chat_template
    field_messages: messages
    roles_to_train: ["assistant"]     # Only compute loss on assistant turns

val_set_size: 0.1
sequence_len: 2048
sample_packing: true

micro_batch_size: 2
gradient_accumulation_steps: 4
num_epochs: 3
learning_rate: 0.0003
optimizer: adamw_torch_fused
lr_scheduler: cosine
weight_decay: 0.01

bf16: auto
gradient_checkpointing: true
flash_attention: true
output_dir: ./outputs/teaching-lora
```

### Multi-GPU with DeepSpeed

```yaml
deepspeed: deepspeed_configs/zero2.json
```

```bash
accelerate launch -m axolotl.cli.train config.yml
```

### DPO in Axolotl

Just add to your YAML:
```yaml
rl: dpo
```

---

## 2.3 API Fine-Tuning (Together AI — Cheapest Validation)

```python
import together

client = together.Together()

# Upload data
file = client.files.upload(file="teaching_data.jsonl")

# Fine-tune
job = client.fine_tuning.create(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct-Reference",
    training_file=file.id,
    n_epochs=3,
    learning_rate=1e-5,
    batch_size=4,
    lora=True,
    warmup_ratio=0.1,
    train_on_inputs="auto",
    suffix="feynman-teacher",
)

# Use it (serverless — no deployment needed for LoRA)
response = client.chat.completions.create(
    model=job.output_name,
    messages=[{"role": "user", "content": "Hello"}],
)
```

**Cost:** $0.48/1M tokens for models ≤16B, $1.50/1M for 16-69B. A 5K example run on 7B ≈ $3.46.

### OpenAI API Fine-Tuning

```bash
# Upload
curl https://api.openai.com/v1/files \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F purpose="fine-tune" \
  -F file="@data.jsonl"

# Train
curl https://api.openai.com/v1/fine_tuning/jobs \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"training_file": "file-abc123", "model": "gpt-4.1-mini-2025-04-14"}'
```

**Limitations:** No access to weights, no LoRA config control, can't self-host, can't export.

---

# Part 3: LoRA Mechanics — What the Parameters Actually Mean

## 3.1 How LoRA Works

Instead of updating full weight matrix W (d_in × d_out), LoRA freezes W and adds two small matrices:
- A: (d_in × r)
- B: (r × d_out)

Forward pass: `output = Wx + (alpha/r) * BAx`

Only A and B are trained. For a 7B model with r=16, this is ~0.1-0.5% of total parameters.

## 3.2 Rank (r)

| Rank | Use Case | When |
|---|---|---|
| 4-8 | Simple tasks (classification, sentiment) | Minimal behavioral change |
| 16-32 | Standard instruction tuning, style transfer | **Start here** |
| 64-128 | Complex behavioral changes, multi-task | Demanding use cases |
| 256+ | Approaching full fine-tune quality | Maximum expressiveness |

**Key insight:** Once rank meets the task's intrinsic dimensionality, higher ranks give marginal gains. Start at 16, go higher if underfitting.

## 3.3 Alpha

Effective scaling = `alpha / r`. Controls how much the adapter's update affects the output.

| Ratio | Effect |
|---|---|
| alpha = r (1.0) | Balanced baseline |
| alpha = 2r (2.0) | Most common default — doubles adaptation strength |
| alpha = r/2 (0.5) | Conservative, preserves pretrained behavior |

**Common practice:** Set alpha = 2 × rank. Many people fix alpha at 16 or 32 and vary rank.

## 3.4 Target Modules — Which Layers

**Attention:**
- `q_proj` — How the model "asks questions" about input
- `k_proj` — How tokens present themselves for matching
- `v_proj` — What info gets passed when attended to
- `o_proj` — Output projection

**MLP/FFN:**
- `gate_proj` — Gate in SwiGLU
- `up_proj` — Up-projection
- `down_proj` — Down-projection

**Targeting strategies (ordered by param count):**

1. **Q, V only** (~0.5% params) — Original LoRA paper. Lightest.
2. **All attention** (~1%) — Better coverage
3. **All attention + FFN** (~2.5%) — Better for new knowledge
4. **All linear** (~5%) — **Recommended starting point** (Unsloth default, Raschka's findings)

## 3.5 DoRA vs LoRA

DoRA decomposes pretrained weight into magnitude + direction, fine-tunes both. **1-4% improvement over LoRA** across most benchmarks. More robust to rank selection. No additional inference overhead (components merge back).

Enable: `peft_use_dora: true` (Axolotl) or `LoraConfig(use_dora=True)` (PEFT)

## 3.6 rsLoRA

Standard LoRA scaling: `alpha/r`. rsLoRA scaling: `alpha/sqrt(r)`.

**Solves:** At high ranks, standard LoRA's effective learning rate per parameter decreases → gradient collapse. rsLoRA stabilizes gradients so r=64 and r=256 train comparably.

**Use when:** r ≥ 64. Below that, negligible difference.

---

# Part 4: Hyperparameters

## 4.1 Learning Rate

| Method | Range | Starting Point |
|---|---|---|
| Full fine-tuning | 1e-5 to 5e-5 | 2e-5 |
| LoRA/QLoRA SFT | 1e-4 to 3e-4 | **2e-4** |
| DPO | 1e-6 to 5e-5 | **5e-6** (40x lower than SFT!) |
| ORPO | 5e-6 to 8e-6 | **8e-6** |

**Why LoRA uses higher LR:** Only small adapter matrices are trained → need larger updates to have impact.

**Critical:** Using SFT learning rates for DPO causes catastrophic forgetting. Drop 40x.

## 4.2 Other Key Parameters

| Parameter | Typical Value | Notes |
|---|---|---|
| Epochs | 1-3 | Overfitting risk beyond 3 for small datasets |
| Batch size (effective) | 16-64 | = per_device × grad_accum × num_GPUs |
| Warmup ratio | 0.03-0.1 | Higher for larger LR or smaller datasets |
| Weight decay | 0.01-0.05 | Regularization |
| LR scheduler | cosine | Most popular, smooth decay |
| Max seq length | 2048 (dev), up to model max (prod) | Memory scales linearly with FlashAttn |
| Optimizer | adamw_8bit | Saves memory vs standard AdamW |
| Beta (DPO/ORPO) | 0.1-0.5 | Higher = more conservative |

## 4.3 Quantization for Training

```python
from transformers import BitsAndBytesConfig
import torch

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",            # NF4 > FP4 (always)
    bnb_4bit_use_double_quant=True,       # Extra 0.4 bits/param savings (always enable)
    bnb_4bit_compute_dtype=torch.bfloat16, # bf16 for computation
)
```

- **NF4:** Information-theoretically optimal for normally distributed weights. Always use over FP4.
- **Double quant:** Quantizes the quantization constants. ~3% more memory savings. Always enable.
- **QLoRA matches 16-bit fine-tuning quality** per the original paper.

### VRAM Requirements (LoRA r=16)

| Model | 4-bit QLoRA | 8-bit LoRA | Full Fine-Tune (16-bit) |
|---|---|---|---|
| 7-8B | ~6-10 GB | ~12-16 GB | ~60+ GB |
| 13B | ~10-16 GB | ~20-28 GB | ~100+ GB |
| 70B | ~40-48 GB | ~80+ GB | ~500+ GB |

---

# Part 5: Training Monitoring

## 5.1 What to Track

**SFT:** `loss`, `eval_loss`, `mean_token_accuracy`, `entropy`, `learning_rate`, `grad_norm`

**DPO:** `rewards/chosen` (↑), `rewards/rejected` (↓), `rewards/accuracies` (→ 1.0), `rewards/margins` (↑)

## 5.2 Loss Curves — What Good vs Bad Looks Like

| Pattern | Diagnosis | Action |
|---|---|---|
| Both losses decrease smoothly, small gap | Healthy | Continue |
| Train loss ↓, eval loss ↑ | **Overfitting** | Reduce epochs, add dropout/weight decay, early stopping |
| Both plateau high | **Underfitting** | Increase LR, increase rank, train longer, check data |
| Wild oscillations/spikes | **Unstable** | Reduce LR, increase batch size, gradient clipping |

## 5.3 Detecting Catastrophic Forgetting

1. Benchmark before/after on general tasks (MMLU, HellaSwag)
2. Include general-purpose examples in validation set
3. Ask the model general questions it should still know
4. Monitor eval loss on held-out general data during training

## 5.4 W&B Setup

```python
# In TrainingArguments:
report_to="wandb",
logging_steps=10,

# Optional explicit init:
import wandb
wandb.init(project="feynman-finetune", name="qwen-7b-teaching-lora-r16")
```

---

# Part 6: How World-Class Orgs Do It

## 6.1 Meta — Llama 3 (6 Iterative Rounds)

The entire post-training runs **6 rounds**, each containing:

1. **SFT** on instruction data
2. **Rejection Sampling:** Sample K outputs (10-30) per prompt, reward model picks best
3. **DPO** on preference pairs

**The data is almost entirely synthetic.** Llama 3 used the previous round's model to generate next round's data. Essentially zero human-written answers.

**Data mix:** 2.4% human annotations, 44.2% NLP tasks, 18.8% rejection-sampled, 34.6% translated reasoning. 25M+ synthetic examples total.

**Reward model:** Three-tier ranking (edited > chosen > rejected). Annotators also create "edited" versions — the chosen response further improved. Similar-quality pairs discarded.

**No PPO.** They found the simple SFT → Rejection Sampling → DPO loop performed best AND was more reproducible than PPO-based RLHF.

## 6.2 OpenAI — InstructGPT / RLHF

**Step 1: SFT** — ~13K prompts, humans write ideal responses, fine-tune GPT-3
**Step 2: Reward Model** — ~33K prompts, labelers rank multiple outputs, train 6B RM (175B RM was unstable)
**Step 3: PPO** — ~31K prompts, RM as reward signal, KL penalty prevents divergence from SFT model

**Result:** 1.3B InstructGPT beat 175B GPT-3 in human preferences. Used <2% of pretraining compute.

**Labeler setup:** ~40 labelers, screening tests, separate eval labelers (never produced training data). Agreement: 72-77%.

## 6.3 Anthropic — Constitutional AI (RLAIF)

**Phase 1 — Critique & Revision:**
- Model generates response
- Model critiques own response against constitutional principles
- Model revises → this creates SFT data without human labels

**Phase 2 — RLAIF:**
- AI evaluates which of two outputs better follows principles
- Train reward model on AI-generated preferences
- Run RL (same as RLHF but AI feedback)

Only ~10 human-written principles instead of thousands of labels. Models are both more helpful AND more harmless (Pareto improvement). Cost: <$0.01/comparison.

## 6.4 Google — LearnLM

Reframes pedagogy as **instruction following**. System instructions describe desired teaching behaviors. Avoids hardcoding "be a good tutor."

Pipeline: SFT (pedagogical conversations) → Reward Model (228 pedagogy experts with advanced degrees + 2yr tutoring) → RLHF

**Key finding:** "SFT improves pedagogical instruction following somewhat, **RL is significantly more effective**" — preference data matters more than demonstrations for behavioral fine-tuning.

**Results:** +31% over GPT-4o, +11% over Claude 3.5 Sonnet, +13% over base Gemini 1.5 Pro.

## 6.5 ETH Zurich — PedagogicalRL

Simulates multi-turn dialogues between tutor model and student simulator (Llama 3.1 8B prompted as student).

**Reward function (3 metrics):**
1. **Delta Solve Rate:** Did the student actually learn? (positive reward)
2. **Leak Rate:** Did the tutor give away the answer? (penalty)
3. **Helpful Rate:** Was guidance meaningful? (positive reward)

Uses **GRPO** (no value model needed). 16 problems × 8 rollouts = 128 dialogues per batch. Problems filtered to 1-60% student solve rate (not too easy, not too hard).

**Result:** 7B model matches LearnLM (based on Gemini 1.5 Pro — vastly larger). **No human annotations required.**

---

# Part 7: Post-Training Pipeline & Deployment

## 7.1 SFT → DPO (Two-Stage) vs ORPO (Single-Pass)

| | SFT + DPO | ORPO |
|---|---|---|
| Training steps | 2 separate jobs | 1 job |
| Reference model | Required (frozen SFT checkpoint) | Not needed |
| Compute | More (train twice) | Less |
| Quality ceiling | Higher (proven at Meta/OpenAI scale) | Competitive |
| SFT quality dependence | High (~35% improvement from better SFT init) | Low (~15%) |
| **Best for** | Max quality, large-scale | Rapid iteration, limited compute |

## 7.2 Merging & Quantization

**Critical rule: Merge LoRA into UNQUANTIZED base model, THEN quantize.** Quantization is not invertible.

```python
# Unsloth handles this correctly:
model.save_pretrained_merged("merged", tokenizer, save_method="merged_16bit")
model.save_pretrained_gguf("gguf", tokenizer, quantization_method="q4_k_m")
```

**Quantization for deployment:**

| Format | Best For | Quality Retention | Speed |
|---|---|---|---|
| GGUF Q4_K_M | CPU/hybrid, Ollama, llama.cpp | ~92% | Good |
| GPTQ | Full GPU, ExLlama | ~90% | 5x faster than GGUF on GPU |
| AWQ | GPU, best quality | ~95% | Good |
| FP8 | H100/A100 production | ~99% | Best |

## 7.3 Serving

| Engine | Best For | LoRA Support |
|---|---|---|
| **vLLM** | High-throughput production GPU serving | Yes (but ~50% throughput penalty vs merged) |
| **TGI** | HuggingFace ecosystem production | Yes |
| **Ollama** | Local dev/testing | Via GGUF |
| **llama.cpp** | Edge/resource-constrained | Via GGUF |

**For Feynman (real-time, low latency):** Use merged model (not runtime LoRA) on vLLM with chunked prefill for stable inter-token latency. FP8 on A100/H100 for speed.

## 7.4 The Data Flywheel

```
Deploy → Collect interactions → Extract preference signals → Retrain → Deploy improved → Repeat
```

**Production signals:** thumbs up/down, conversation length, regeneration frequency, confusion detection, student comprehension outcomes, teacher ratings.

**Meta's CharacterFlywheel:** 15 model versions in 20 months. Production traffic → annotation pipeline → preference models → SFT + DPO datasets → retrain.

---

# Part 8: Failure Modes

## Catastrophic Forgetting
Model forgets pretrained knowledge. **Prevention:** LoRA (freezes base), low LR, few epochs, mix general data into training, KL penalty.

## Mode Collapse
Increasingly repetitive/sycophantic outputs. **Prevention:** KL penalty, entropy bonuses, diverse training data, monitor generation diversity.

## Reward Hacking
Model exploits reward model flaws (verbose = high score). **Prevention:** Bound RL reward, ensemble reward models, KL penalty, retrain RM on adversarial examples.

## Overfitting on Small Data
Memorizes instead of generalizing (<1K examples). **Prevention:** LoRA, early stopping, 1-3 epochs, data augmentation, validation monitoring.

## Safety Degradation
**GPT-3.5 Turbo's guardrails were jailbroken with 10 adversarial examples at $0.20.** Even benign fine-tuning can degrade safety.

**Prevention:** Include safety data in fine-tuning mix, post-fine-tuning safety evaluation (always), EMA for optimal safety/performance balance.

---

# Part 9: The Complete Recipe for Feynman

**Starting config for Week 1 validation ($30):**
```
Model: Qwen 2.5 7B Instruct
Method: QLoRA via Together AI ($3.46/run) or Unsloth on RunPod
Data: 500-1000 converted teaching dialogues (from 3B1B via Sonnet Batch API)
Format: OpenAI JSONL (messages array)
LoRA: r=16, alpha=32, all linear layers
Training: ORPO (single pass), 3 epochs, lr=8e-6
Eval: LLM-as-judge with teaching rubrics (Socratic behavior, answer withholding, confusion detection)
```

**Production pipeline (after validation):**
```
1. SFT on 5K teaching dialogues (Qwen 2.5 7B, Unsloth, 1 epoch, lr=2e-4)
2. ORPO with preference pairs (chosen=Socratic, rejected=answer-giving, 3 epochs, lr=8e-6)
3. Merge LoRA → GGUF Q4_K_M for testing, FP8 for production
4. Eval: LLM-as-judge + delta solve rate (PedagogicalRL approach)
5. Serve: vLLM with merged model, chunked prefill
6. Flywheel: classroom interactions → preference pairs → iterative ORPO
```
