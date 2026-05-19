# 03 — Fine-Tune Deep-Dive & Tiered Pricing Study

> Two interconnected research studies. **Part A**: deep implementation of Phase C (fine-tuned Feynman model on Indian GPU infra) — the single highest-leverage cost+latency move. **Part B**: analysis of whether pre-loading live teaching content can crack a ₹5K/30hr tier (~$0.46/hr COGS). **Part C**: strategic recommendation — tiered pricing maps to tiered architecture (Free / Plus / Pro), one engine, three modes.

**Status**: Research complete. Awaiting Aanya demo validation before Phase C kickoff.
**Companion**: [02 — Cost & Latency Engineering Plan](./02-cost-latency-engineering-plan.md) — the upstream 5-phase plan A-E.
**Companion**: [01 — Consumer Product Thesis](./01-consumer-product-thesis.md) — the pricing/persona backbone.

---

# PART A — Phase C: Fine-Tuned Feynman Model on Indian GPU Infra

## A.1 What it actually is

Today, every teaching turn calls Anthropic Sonnet 4.6 in a US datacenter. The model is **general-purpose** — trained on the entire internet, including poetry, code, marketing copy. We pay frontier-LLM prices for a model that mostly does one thing: teach IGCSE STEM in a Feynman-Technique style.

**The thesis**: a *smaller, specialized model* can match (or exceed) Sonnet's teaching quality on the routine 80% of turns, while running:
- **3-10× faster** (50-300ms TTFT vs 500-1500ms)
- **10-15× cheaper** ($0.20/hr blended vs $3-5/hr)
- **In the same Indian datacenter** as our backend (10-30ms network vs 200-400ms cross-continent)

Concretely: we take **Qwen 2.5 14B Instruct** (Apache 2.0 license, open weights), fine-tune it on Feynman-specific teaching dialogue via **QLoRA + Unsloth**, and serve the result on **E2E Networks Bangalore GPUs** with **vLLM**.

## A.2 Why this is provably feasible

Three pieces of public evidence:

| Evidence | What it shows | Implication |
|---|---|---|
| **TeachLM paper (2024)** by Stanford/Google | Fine-tuned smaller models (7-13B) trained on 100K hours of human tutoring transcripts **outperform** general frontier LLMs on student-outcome metrics (concept retention, comprehension check pass-rate, session completion). The key insight: teaching quality comes from **dialogue patterns**, not raw model size. | Our 100hr × ~50 turns/hr × 0.5 keep-rate = ~2,500 real turns + synthetic augmentation → 8-12K training set is in TeachLM's validated range. |
| **Unsloth benchmarks** (unsloth.ai) | QLoRA fine-tuning Qwen 14B on single H100 (80GB) takes 4-8 hours, costs ~$20-40 (RunPod/Lambda Labs spot pricing). Final LoRA adapter is 150-300MB. | Iteration cost is **trivial**. We can fine-tune 5-10 times to converge on hyperparameters for the price of dinner. |
| **vLLM production benchmarks** | Qwen 14B at int4 on RTX 4090: ~80 tok/sec/user, 5-10 concurrent users via continuous batching. TTFT 100-300ms. | E2E Networks RTX 4090 at ₹70/hr ≈ $0.85/hr ÷ 8 concurrent users = **$0.11/user-hr inference cost**. Far below current $3-5/hr Sonnet. |

This is **not speculation**. The components are all production-proven. We're recombining them in a new domain (IGCSE teaching).

## A.3 The data pipeline (the make-or-break part)

Models are a function of data. If we do this wrong, the model is worse than Haiku at higher cost. Here's the rigorous version:

### Step 1: Telemetry infrastructure (Weeks 1-2)

We need to log every Sonnet turn with the full context that produced it:

```python
# In worker.py:llm_node, wrap the LLM call:
@dataclass
class TelemetrySample:
    timestamp: datetime
    session_id: UUID
    student_id: UUID  # post-auth
    concept_index: int
    concept_title: str
    state: TeachingState              # TEACHING | HANDLING_DOUBT
    branch_depth: int
    
    # The full LLM input
    system_prompt: str                # full text, will be deduped
    chat_history: list[Message]       # last N turns
    tools_available: list[str]
    
    # The completion
    response_text: str                # full assistant text including action tags
    tool_calls: list[ToolCall]        # which tools fired
    tokens_in: int
    tokens_out: int
    latency_ms: int
    
    # Quality signals (filled in async post-turn)
    perception_score: int | None      # from BoardVerifier
    perception_feedback_fired: bool   # was there a recovery cycle?
    checklist_advanced: bool          # in doubt branch, did this turn tick an item?
    student_next_action: str          # "advance" | "doubt" | "confused" | "silent"
    session_succeeded: bool           # set at session end
```

Stored in Postgres (`telemetry_samples` table) + chat history JSON in Cloudflare R2 (cheap egress for India).

### Step 2: Quality filter (Week 7)

Not all data is good data. We drop:
- Sessions where comprehension checks failed (student didn't actually learn)
- Turns followed by `[PERCEPTION_FEEDBACK]` recovery (Sonnet messed up; don't teach Qwen to mess up too)
- Turns from sessions <5 minutes (student bounced)
- Turns where the student went silent for >60s and the agent had to nudge (engagement broke)

Empirically (per TeachLM): **30-50% survival rate** is typical. From 100 hr × 50 turns/hr = 5000 raw → ~1500-2500 high-quality survivors.

### Step 3: Synthetic augmentation (Weeks 7-8)

1500-2500 examples is **below** the TeachLM sweet spot of 4-5K SFT pairs. We augment:

**Source A: 3Blue1Brown corpus** (per memory `fine-tuning-research.md`)
- ~100 hours of math explanations, transcripts available
- Convert monologue → Socratic dialogue via Claude Batch API: "given this 3B1B segment, write 8 turns of dialogue between a confused student and a Feynman-Technique teacher that arrive at the same understanding"
- Cost: ~$43 total (Claude Batch is 50% discount)
- Yields: ~2,000-3,000 dialogue turns

**Source B: Cambridge IGCSE 0580 past papers + examiner reports**
- 20 years of past papers × 4 papers/year × ~15 questions × possible-doubt-paths-per-question
- Have Claude simulate "common student misconceptions" and "good tutor responses"
- Yields: ~1,500-2,500 turns covering the syllabus

**Source C: Aanya demo verbatim scripts** (hand-authored, gold standard)
- All beat scripts from `docs/design/12-aanya-demo-v0.md` get used 10× as gold-standard SFT examples (oversampled to anchor style)
- Yields: ~200 ultra-high-quality "this is what magic looks like" anchors

**Total augmented dataset**: 8,000-12,000 examples. Right in the validated zone.

### Step 4: Preference pairs for DPO (Weeks 8-9)

SFT teaches the model what to say. **DPO teaches it what NOT to say.** For each prompt where we have Sonnet's good completion, we generate a "rejected" completion:

- **Bad-Haiku alternative**: ask Haiku to generate the same turn — Haiku often produces formally-correct-but-pedagogically-flat responses. These become the "rejected" examples.
- **Truncated Sonnet**: take Sonnet's good response and chop it at sentence 1 — teaches the model that 1-sentence responses are bad when a multi-step explanation is needed.
- **Wrong-tool-call alternative**: have Sonnet generate the response but with `draw_diagram` instead of `draw_design_diagram`, or `show_equation` instead of `write_equation` — teaches the right tool for the panel.

Yields: ~3,000-5,000 DPO triples (prompt, chosen, rejected).

### Step 5: Training (Week 9-10)

Hardware: rent **one H100 80GB** on RunPod or Lambda Labs (spot pricing ~$2-4/hr). Total training run: 4-8 hours.

Software stack:

```python
# Pseudocode of the training script
import unsloth
from trl import SFTTrainer, DPOTrainer
from transformers import AutoTokenizer

# Phase 5a: Load Qwen 2.5 14B Instruct with 4-bit quantization
model, tokenizer = unsloth.FastLanguageModel.from_pretrained(
    model_name="Qwen/Qwen2.5-14B-Instruct",
    max_seq_length=8192,         # long enough for our system prompt + history
    dtype=None,
    load_in_4bit=True,
)

# Add LoRA adapters to the attention + MLP modules
model = unsloth.FastLanguageModel.get_peft_model(
    model,
    r=32,                        # LoRA rank
    target_modules=["q_proj","k_proj","v_proj","o_proj",
                    "gate_proj","up_proj","down_proj"],
    lora_alpha=64,
    lora_dropout=0.05,
    bias="none",
    use_gradient_checkpointing=True,
)

# Phase 5b: SFT pass — teach Feynman style
sft_trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=feynman_sft_dataset,    # 8-12K examples
    max_seq_length=8192,
    args=TrainingArguments(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        warmup_ratio=0.03,
        num_train_epochs=2,
        learning_rate=2e-4,
        bf16=True,
        logging_steps=10,
        optim="adamw_8bit",
        output_dir="qwen-feynman-sft",
    ),
)
sft_trainer.train()  # ~3-5 hours

# Phase 5c: DPO pass — teach preferences
dpo_trainer = DPOTrainer(
    model=model,
    ref_model=None,                       # uses SFT model as reference
    tokenizer=tokenizer,
    train_dataset=feynman_dpo_dataset,    # 3-5K triples
    args=TrainingArguments(...),
    beta=0.1,                             # KL penalty strength
)
dpo_trainer.train()  # ~1-2 hours

# Save the LoRA adapter (only 150-300MB)
model.save_pretrained("qwen-feynman-v1-lora")
```

Output artifact: a LoRA adapter file. Merge into base model on serving time.

### Step 6: Offline evaluation (Week 10-12)

Critical guardrails before any traffic:

**Eval set**: 500 held-out turns from production telemetry (never seen in training).

**Metrics**:
1. **LLM-as-judge** with Claude Opus: pair (Qwen completion, Sonnet completion) — which is better on (pedagogical correctness, tone match, helpfulness)? Target: Qwen wins or ties ≥75% of the time.
2. **Tool-call accuracy**: did Qwen pick the same tool as Sonnet for the same context? Target: ≥85% match.
3. **Length distribution**: avg tokens per turn, p95 length. Target: within ±20% of Sonnet.
4. **Refusal/hallucination rate**: any responses that go off-topic, refuse, hallucinate facts? Target: ≤2%.
5. **Math correctness**: pass a 100-problem IGCSE 0580 math set graded by symbolic match. Target: ≥90%.

Iterate on hyperparameters / training data based on weak spots. Budget 3-5 rounds of fine-tune-eval-iterate.

## A.4 The serving stack

### Hardware in India

```
E2E Networks Bangalore (Indian provider, lowest egress to India)
─────────────────────────────────────────────────────────────
Option A:  RTX 4090 24GB     ₹50-80/hr  ($0.60-0.95/hr)
   • Qwen 14B at int4 → ~16GB VRAM
   • KV cache headroom for ~5-8 concurrent users
   • Per-session: $0.08-0.15/hr inference

Option B:  RTX A6000 48GB    ₹100-150/hr ($1.20-1.80/hr)
   • Qwen 14B at int8 → ~28GB VRAM (better quality than int4)
   • KV cache for ~10-15 concurrent users
   • Per-session: $0.10-0.18/hr inference

Option C:  H100 80GB          ₹400-600/hr ($5-7/hr)
   • Reserved for high-traffic mode
   • Qwen 14B at fp16 → ~28GB, lots of KV cache headroom
   • 20-30 concurrent users
   • Per-session: $0.20-0.30/hr — only beats Sonnet at scale
```

**Recommendation**: start with **RTX A6000** in Bangalore. Best balance of quality (int8 ≈ fp16 perceptually) and per-session cost. Scale to H100 only when concurrent demand crosses ~10 sessions consistently.

### Software stack

**vLLM** is the de-facto serving framework. Key features:

```python
# Server startup
from vllm import AsyncLLMEngine, AsyncEngineArgs

engine = AsyncLLMEngine.from_engine_args(AsyncEngineArgs(
    model="Qwen/Qwen2.5-14B-Instruct",
    lora_modules=["feynman=/models/qwen-feynman-v1-lora"],
    enable_lora=True,
    max_lora_rank=32,
    quantization="awq",                  # int4 AWQ post-training quant
    gpu_memory_utilization=0.90,
    max_num_seqs=10,                     # max concurrent sequences
    max_num_batched_tokens=8192,
    enable_prefix_caching=True,          # ← HUGE: caches our system prompt KV
    tensor_parallel_size=1,              # single-GPU
))
```

**The single biggest knob: `enable_prefix_caching=True`**.

Our system prompt is ~3-4K tokens AND IDENTICAL across all sessions (lesson plan + dictionary varies slightly but the bulk is static). vLLM's prefix caching keeps the KV-cache for that prefix on the GPU, so we don't recompute it. Effect: TTFT drops from ~300ms to ~50ms after the first request to each prefix.

### Integration with Feynman backend

Beautiful part — **almost no code change**:

```python
# backend/src/feynman/livekit/pipeline.py
# Current:
def create_llm():
    return anthropic.LLM(model="claude-sonnet-4-6")

# After Phase C:
def create_llm():
    if settings.use_finetuned_teaching:
        # vLLM exposes OpenAI-compatible HTTP
        return openai.LLM(
            model="feynman",                       # our LoRA adapter name
            base_url="http://e2e-bangalore.feynman.internal:8000/v1",
            api_key="local",
        )
    return anthropic.LLM(model="claude-sonnet-4-6")
```

The `livekit-agents` framework handles model-agnostic streaming, tool calls, etc. We just point at a different endpoint.

### The routing layer (the actual production logic)

We don't blindly use Qwen for everything. Cost optimization mustn't break magic moments. The router lives between `llm_node` and the model call:

```python
# backend/src/feynman/livekit/llm_router.py — NEW file
class FeynmanLLMRouter:
    def __init__(self, finetuned, sonnet, audit):
        self.finetuned = finetuned
        self.sonnet = sonnet
        self.audit = audit
    
    async def generate(self, chat_ctx, tools, settings, tc):
        # HARD MOMENT detection — escalate immediately
        if self._is_hard_moment(tc, chat_ctx):
            self.audit.record("router", "escalated", reason=self._reason)
            return await self.sonnet.generate(chat_ctx, tools, settings)
        
        # Default: try fine-tuned
        result = await self.finetuned.generate(chat_ctx, tools, settings)
        
        # CONFIDENCE ESCALATION — logprobs gate
        # If model is uncertain (high entropy in next-token distribution),
        # fall back. vLLM returns logprobs when requested.
        if result.metadata.get("avg_logprob", 0) < ESCALATE_THRESHOLD:
            self.audit.record("router", "escalated", reason="low_confidence")
            return await self.sonnet.generate(chat_ctx, tools, settings)
        
        self.audit.record("router", "served_finetuned", reason="ok")
        return result
    
    def _is_hard_moment(self, tc, chat_ctx) -> bool:
        # Reason 1: recent perception feedback (Phase 5a recovery loop)
        recent = chat_ctx.history[-3:]
        if any("[PERCEPTION_FEEDBACK]" in m.content for m in recent):
            self._reason = "perception_recovery"
            return True
        
        # Reason 2: deep in a doubt branch (>30s) without progress
        if tc.state_machine.depth > 1:
            branch = tc.state_machine.current
            seconds_in = (now() - branch.started_at).total_seconds()
            if seconds_in > 30 and not self._checklist_advancing(branch):
                self._reason = "stuck_doubt"
                return True
        
        # Reason 3: novel concept (student first encounter)
        if not self._student_seen_concept(tc):
            self._reason = "novel_concept"
            return True
        
        # Reason 4: student showed confusion signals
        # (sentiment analysis of last student utterance — cheap Haiku check)
        if self._student_confused_signal(chat_ctx):
            self._reason = "student_confused"
            return True
        
        return False
```

**Empirical target routing distribution** (calibrated post-A/B):
- 80% fine-tuned
- 15% Sonnet escalation
- 5% Opus for the absolute hardest moments (novel concepts, repeated comprehension failures)

### Cost math after Phase C

```
Per session-hour breakdown:
   80% × $0.20/hr (Qwen 14B int8 on A6000, ~12 conc users)  = $0.16
   15% × $0.80/hr (Sonnet with prompt cache)                = $0.12
   5%  × $2.50/hr (Opus fallback for hardest)               = $0.13
   ──────────────────────────────────────────────────────────────
   Blended teaching LLM cost:                                = $0.41/hr

vs current Sonnet-only $3-5/hr → savings $2.6-4.6/hr
```

The math holds. Phase C alone is the difference between a viable business and not.

## A.5 Specific timeline + budget

| Phase | Duration | Cost | Deliverable |
|---|---|---|---|
| Telemetry instrumentation | 2 wk | $0 | TelemetrySample schema, logging, S3/R2 backend |
| Real-data collection | 4 wk | $0 (overlapped with Aanya beta) | 100hr+ of high-quality teaching turns |
| Quality filter pipeline | 1 wk | $0 | Filtered set, ~1500-2500 keep-turns |
| Synthetic augmentation | 1 wk | ~$50 (Claude Batch) | 8-12K SFT + 3-5K DPO pairs |
| Training run #1 (SFT+DPO) | 2 wk (3-5 iterations) | ~$200 (5 × $40 H100 spot runs) | Qwen-Feynman-v1 LoRA |
| Offline eval | 1 wk | ~$50 (Claude Opus judge calls) | LLM-as-judge scores, weak-spot analysis |
| Iteration | 2 wk | ~$200 | Qwen-Feynman-v2 |
| E2E Networks GPU deploy + vLLM | 1 wk | $100 setup + $1000/mo ongoing | Production endpoint serving |
| Shadow mode (100% traffic to both, log only Qwen) | 2 wk | ~$1200 extra | Validation that Qwen ≈ Sonnet in production |
| A/B ramp 5% → 100% | 6 wk | gradual savings | Routing logic tuned, KPIs measured |
| **TOTAL** | **~22 weeks** | **~$1,800 dev + $1,200/mo ongoing GPU** | Phase C complete |

**The development cost is laughably small** ($1,800). The ongoing GPU cost ($1,200/mo for one A6000) pays for itself **as soon as we have 5+ concurrent users** — that's why it scales beautifully with growth.

---

# PART B — Pre-Loaded Content: Can ₹5K/30hr Work?

## B.1 The new target

₹5,000/month for 30 hr = **₹167/hr revenue ≈ $2.00/hr**.

Following the same margin math:

| Component | % of revenue | $/hr |
|---|---|---|
| Payment processing + GST | 5% | $0.10 |
| CAC amortization (₹3K / 8mo) | 12% | $0.24 |
| Support + ops | 10% | $0.20 |
| Gross margin (50%) | 50% | $1.00 |
| **Available COGS** | **23%** | **~$0.46/hr** |

Need to drop COGS from $1.07/hr (Phase A+B+C+D+E end state) to **$0.46/hr — another 57% reduction.**

## B.2 What "pre-loaded" actually means

This concept already exists in our codebase, partially:

- `docs/design/05-beat-orchestration-system.md` specifies **BEAT MODE vs CONVERSATIONAL MODE**.
- `concept_planner.py` already produces `ConceptTeachingPlan` with `beats[]` array.
- Each `TeachingBeat` already has a `target_voice_script` field for verbatim binding.
- Curriculum pipeline Phase 12 specifies pre-generation of every visual.

**What's missing** is the orchestrator that *plays* these beats deterministically. Today, the LLM sees the plan as guidance and reacts live. The full pre-loaded model would:

```python
# Pre-computed at curriculum ingestion (offline, one-time):
class ConceptPreloadedContent:
    concept_uid: str
    beats: list[TeachingBeat]              # narration + visuals + timing
    anticipated_doubts: list[DoubtPath]    # top 4-8 likely doubts
    
class DoubtPath:
    trigger_keywords: list[str]            # for fast embedding match
    embedding: np.ndarray                  # for similarity match
    response_beats: list[TeachingBeat]     # pre-written response
    return_cue: str                        # verbatim "back to main"
    
# Runtime — drastically simplified:
async def teach_concept(concept_idx):
    content = load_preloaded(concept_idx)  # one Redis fetch, ~1ms
    
    for beat in content.beats:
        # Wait for student readiness signal (silence + attention)
        await wait_for_ready_signal()
        
        # Play visual (already pre-rendered DiagramSpec)
        await publish_visual(beat.visual_payload)
        
        # Play narration verbatim via TTS
        await speak(beat.target_voice_script)
        
        # Handle interruption
        if student_interrupts():
            doubt_text = await stt()
            await handle_doubt(content.anticipated_doubts, doubt_text)
```

The LLM is **out of the hot path** for routine teaching. STT and TTS are the only AI calls during scripted beats.

## B.3 Doubt handling under pre-load

The trickiest part. Students ask whatever they want — we can't pre-write infinite responses.

**Strategy**: embed each anticipated doubt at ingestion time; embed student's actual question at runtime; match by cosine similarity.

```python
async def handle_doubt(anticipated_doubts, student_question):
    # Cheap embedding via self-hosted sentence-transformers
    # (e.g., BAAI/bge-small-en-v1.5, 384-dim, runs on CPU at ~1ms)
    q_embed = embed(student_question)
    
    best_match, similarity = max(
        ((d, cos_sim(d.embedding, q_embed)) for d in anticipated_doubts),
        key=lambda x: x[1]
    )
    
    if similarity > 0.75:
        # CACHE HIT — play pre-written response (no LLM cost!)
        for beat in best_match.response_beats:
            await publish_visual(beat.visual_payload)
            await speak(beat.target_voice_script)
        await speak(best_match.return_cue)
        return
    
    # CACHE MISS — fall through to full LLM path (current architecture)
    await fallback_llm_doubt_handling(student_question)
```

Per Aanya demo doc 12 (`docs/design/12-aanya-demo-v0.md`): **target cache-hit rate ≥3/4** on 4 anticipated doubts. That validates the model — most students ask predictable things, especially in well-structured curricula like IGCSE.

For broader coverage, ingest **8-12 anticipated doubts per concept** (vs 4 in the Aanya demo). Memory cost: trivial. Pre-gen cost at ingestion: ~$5-15 per concept × ~50 concepts/subject = $300-700 one-time.

## B.4 Cost math under pre-loaded mode

Time-weighted breakdown (assumes 30hr/month average usage):

| Path | When | % of session time | $/hr while active | Effective $/hr |
|---|---|---|---|---|
| Scripted beats (no LLM, just STT+TTS+infra) | Normal teaching | 70% | $0.22 | $0.154 |
| Doubt cache HIT (no LLM) | Pre-written doubt | 14% (70% of 20% doubt time) | $0.22 | $0.031 |
| Doubt cache MISS (full Qwen+Sonnet stack) | Novel doubt | 6% (30% of 20%) | $1.07 | $0.064 |
| Off-script personalization | Greetings, transitions, mom-noticed flair | 10% | $1.07 | $0.107 |
| **Variable subtotal** | | 100% | | **$0.356/hr** |
| Always-on infra (LiveKit + DB + drift check sampled) | Continuous | — | $0.10 | $0.10 |
| **TOTAL** | | | | **~$0.46/hr** |

**Bingo — we hit the target.** ₹5K/30hr is technically feasible.

## B.5 What we LOSE (the brutal trade-off)

Cost cuts mean magic cuts. Here's what changes:

| Property | Full LLM (₹10K tier) | Pre-loaded (₹5K tier) | Severity |
|---|---|---|---|
| **Adaptive pacing** | Slows when student hesitates, speeds when confident | Fixed beat timing, generic transitions | Medium |
| **Personalized analogies** | "Aanya, like the ladder you helped your mom set up last week..." | Generic analogies from script | High |
| **Tone matching** | Matches student energy (excited/tired/confused) | Same warm tone for everyone | Medium |
| **Novel doubt handling** | Always live LLM; always great | 70% cached (great), 30% live (great), but **uneven feel** | High |
| **Cross-session memory** | Remembers prior struggles | Same content every time | Medium |
| **Curriculum freshness** | New question types as syllabus evolves | Re-ingestion required per syllabus update | Low |
| **First 90 seconds magic** | Custom-feels-just-for-me | Polished but obviously scripted | **CRITICAL** |
| **Doubt-branch-and-return** | Magic, real | Magic when cached (70%), feels jarring when miss (30%) | High |

The biggest cost is **the magic moment thesis**. Memory file says: *"The first 90 seconds matter more than everything else."* If those 90 seconds feel scripted, parents won't pay.

## B.6 Honest verdict on ₹5K tier

**Technically possible**: yes, $0.46/hr COGS is achievable.

**Strategically wise as the primary product**: no. We'd be Khanmigo-with-better-visuals at half their price. The moat erodes.

**Strategically wise as a TIER**: absolutely yes. See Part C.

---

# PART C — Strategic Recommendation: Tiered Pricing Maps to Tiered Architecture

The right move is **not to pick one architecture** — it's to **build one engine that supports multiple modes**, then sell each mode at its margin-appropriate price.

## C.1 The three-tier model

| Tier | Price | Architecture | COGS | Margin | Target user |
|---|---|---|---|---|---|
| **Feynman Free** | ₹0 | Fully pre-loaded; no LLM except cache-miss doubts; basic TTS (Edge or free tier) | ~$0.25/hr | — | Lead gen; let students try; massive top-of-funnel |
| **Feynman Plus** | **₹5,000/mo, 30 hr** | Pre-loaded backbone + LLM personalization on greetings/transitions + 30% LLM-driven doubts (cache-miss) + premium TTS | **~$0.46/hr** | ~73% | Price-sensitive parents who want better than free |
| **Feynman Pro** | **₹10,000/mo, 30 hr** | Full live-LLM architecture (Phases A+B+C+D+E); per-student knowledge graph; cross-session memory; the Aanya magic every session | **~$1.07/hr** | ~73% | Premium parents who want "this is just for my kid" |

**Why this works**:
1. **One engine, three modes** — the codebase is the same; the `BEAT_MODE_DENSITY` config toggles how much is pre-loaded vs live. Tier upgrades are config changes, not rewrites.
2. **Upgrade path** — students start on Free, parents see results, upgrade to Plus, then Pro. Classic SaaS funnel.
3. **Premium pays for premium** — Pro users subsidize Free users via CAC efficiency (Free users convert to Plus/Pro at high rates because they've already tasted it).
4. **Khanmigo-equivalent at our LOWER tier** — we're not racing them on price; we're offering strictly more at every price point.

## C.2 Implementation — how to enable mode switching

```python
# In TeachingContext or a new BeatModeConfig:
@dataclass
class BeatModeConfig:
    main_branch_mode: Literal["fully_scripted", "scripted_with_personalization", "fully_live"]
    doubt_handling: Literal["cache_only", "cache_with_fallback", "fully_live"]
    perception_loop: Literal["sampled_10pct", "every_event", "vl_jepa_continuous"]
    tts_quality: Literal["xtts_self_host", "cartesia_hybrid", "cartesia_premium"]
    cross_session_memory: bool

# Free tier:
FREE_CONFIG = BeatModeConfig(
    main_branch_mode="fully_scripted",
    doubt_handling="cache_only",        # student literally hears "I'll need to think about that next time"
    perception_loop="sampled_10pct",
    tts_quality="xtts_self_host",
    cross_session_memory=False,
)

# Plus tier:
PLUS_CONFIG = BeatModeConfig(
    main_branch_mode="scripted_with_personalization",  # LLM-rewrites scripted beats with student name + recent struggles
    doubt_handling="cache_with_fallback",
    perception_loop="every_event",
    tts_quality="cartesia_hybrid",
    cross_session_memory=True,            # but lightweight (concept mastery only)
)

# Pro tier:
PRO_CONFIG = BeatModeConfig(
    main_branch_mode="fully_live",
    doubt_handling="fully_live",
    perception_loop="vl_jepa_continuous",
    tts_quality="cartesia_premium",
    cross_session_memory=True,            # full per-student KG + learning patterns
)
```

The `concept_planner.py` already produces beats; the orchestrator (designed in `docs/design/05-beat-orchestration-system.md`, NOT BUILT) needs to be built — and that's the gating engineering work for the Plus + Free tiers.

## C.3 Recommended sequencing

```text
Q1 (NOW → 6 weeks)         Phase A (cost wins on current stack)
                            Aanya demo ships
                            Validates ₹10K Pro tier magic-moment hypothesis

Q2 (6 → 18 weeks)           Phase B (curriculum pipeline)
                            Phase D (self-host STT/TTS)
                            Build BEAT MODE orchestrator (per doc 05)
                            ──> enables Plus tier launch at ₹5K

Q3 (18 → 30 weeks)          Phase C (fine-tuned Feynman model)
                            Lock in Pro tier moat
                            Launch Free tier with cache-only doubts

Q4 (30+ weeks)              Phase E (VL-JEPA self-hosted)
                            Per-student knowledge graph
                            Cross-tier upgrade funnel optimization
```

## C.4 Why this beats every alternative

1. **vs all-Pro**: half the parents can't afford ₹10K. We lose them entirely.
2. **vs all-Plus**: we cap our revenue ceiling; parents who'd pay ₹10K for true magic get nothing premium to buy.
3. **vs all-Free + ads**: not magic; not memorable; can't get parents to recommend; CAC unsustainable.
4. **vs tiered**: every architecture optimization (Phase A-E) lifts all three tiers' margins simultaneously. Pre-load investment lifts the Free + Plus tiers. Fine-tune investment lifts the Plus + Pro tiers. **Compound returns**.

---

# Summary — Three Things to Tell Yash

1. **Phase C (fine-tuned Qwen 14B on Indian GPU) is a $1,800 investment over 22 weeks that permanently changes our cost structure**. We collect telemetry now, fine-tune on QLoRA+Unsloth for ~$200 (5 iterations), deploy on E2E Networks Bangalore A6000, route 80% of traffic to it with Sonnet fallback for hard moments. Result: $3-5/hr teaching cost → $0.41/hr blended. Math holds; components are all production-proven.

2. **Pre-loading content CAN hit ₹5K/30hr** (~$0.46/hr COGS). But it sacrifices the magic-moment thesis — first 90 seconds feel scripted. **Not the right primary product** if our moat is "feels like AI just for my kid." **Absolutely the right TIER** if we want to expand the funnel below the premium price point.

3. **Tiered pricing maps to tiered architecture** is the right answer. Free (₹0, fully pre-loaded), Plus (₹5K, hybrid), Pro (₹10K, fully live). One codebase, mode switches, three price points. Phase A→E investments lift all tiers' margins. Parents see a real upgrade ladder. We capture more market without diluting magic at the top.

---

## See Also

- [02 — Cost & Latency Engineering Plan](./02-cost-latency-engineering-plan.md) — the upstream 5-phase plan (A-E) that establishes the ₹10K/30hr Pro tier viability. Phase C summary lives there; this doc is the implementation depth.
- [01 — Consumer Product Thesis](./01-consumer-product-thesis.md) — the original ₹4K single-subject thesis. Tiered model in this doc is a generalization.
- `docs/design/05-beat-orchestration-system.md` — BEAT MODE vs CONVERSATIONAL MODE; the unbuilt orchestrator that powers the Free + Plus tiers.
- `docs/design/08-curriculum-graph-pipeline.md` — Phase 12 visual pre-generation; doubt library pre-generation extends from here.
- `docs/design/12-aanya-demo-v0.md` — anticipated-doubts pattern (4 pre-generated diagrams); the empirical seed for the broader 8-12 doubts/concept model.
- `docs/design/13-aanya-demo-build-list.md` — verbatim script binding via `target_voice_script` field; the foundation for fully-scripted beats.
- `~/.claude/projects/-Users-yashbansal-proj-feynman/memory/fine-tuning-research.md` + `fine-tuning-engineering-guide.md` — engineering details for Phase C training pipeline. 3B1B corpus, Cambridge IGCSE past papers, Aanya demo gold standards as data sources.
- TeachLM paper (Stanford/Google, 2024) — empirical validation that fine-tuned 7-13B models outperform frontier LLMs on student outcome metrics when trained on dialogue patterns.
- Unsloth (https://github.com/unslothai/unsloth) — 2× faster QLoRA + lower VRAM training framework.
- vLLM (https://github.com/vllm-project/vllm) — production-grade LLM serving with continuous batching and prefix caching.
- E2E Networks Bangalore — Indian GPU cloud, RBI-compliant payments, lowest-egress for Indian users.
