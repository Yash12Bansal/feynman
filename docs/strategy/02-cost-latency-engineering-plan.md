# 02 — Cost & Latency Engineering Plan: From $5–8/hr to $1.07/hr COGS

> Five-phase research-backed engineering plan to bring Feynman's per-teaching-hour COGS down 80% while *reducing* latency by 40–70% across the stack. Targets the ₹10,000/month / 30hr Pro tier at sustainable 73% gross margin.

**Status**: Research complete. Phases A–E sequenced.
**Companion**: [03 — Fine-Tune Deep-Dive & Tiered Pricing Study](./03-fine-tune-and-tiered-pricing-study.md) — explains Phase C in implementation depth and explores the ₹5K/30hr tier via pre-loading.
**Companion**: [01 — Consumer Product Thesis](./01-consumer-product-thesis.md) — the upstream pricing/persona thesis this plan operationalizes.

---

## 1. The Math — Where We Need to Land

**Target**: 30 hours/month × ₹10,000/month ceiling → **₹333/hr = ~$4.00/hr revenue**

But revenue is not COGS budget. To survive Indian edtech you need:

| Component | % of revenue | ₹ per hour |
|---|---|---|
| Razorpay/Stripe + GST | ~5% | ~₹17/hr |
| CAC amortization (₹3K CAC / 8mo retention) | ~12% | ~₹40/hr |
| Support + dashboard + ops | ~10% | ~₹33/hr |
| Gross margin target | ~50% | ~₹167/hr |
| **Available for AI/infra COGS** | **~23%** | **~₹77/hr ≈ $0.93/hr** |

That's the actual target: **COGS ≤ $1.00/hour** to be a sustainably scalable business at ₹10K/30hr.

**Caveat**: 30 hr/month is heavy. Empirically, EdTech tools see 5-15 hr/month for engaged users, 25-30 hr for power users. If average usage is 12 hr, then $1.00/hr COGS × 12 hr = ₹1,000 against ₹10K revenue = comfortable. **Plan for the worst-case 30 hr utilization** — design for it; benefit from the typical.

---

## 2. Current State — What We're Spending

Baseline per teaching hour:

| Component | $/hr (today) | % of total |
|---|---|---|
| Anthropic Sonnet (teaching) | 3.00–5.00 | **60-65%** ← dominant |
| Anthropic Sonnet (design_agent diagrams) | 0.50–1.50 | 10-20% |
| Anthropic Sonnet (concept_planner) | 0.20–0.50 | 5-7% |
| Anthropic Haiku (perception loop 5a) | 0.30–0.34 | 5% |
| Deepgram STT | ~0.50 | 7-9% |
| Cartesia TTS | 0.30–0.60 | 5-9% |
| LiveKit Cloud | 0.10–0.30 | 2-5% |
| Postgres + Redis + Neo4j | ~0.06 | <1% |
| **TOTAL** | **$5.00–8.00** | 100% |

**Verdict**: 80% of cost is in three buckets: teaching LLM, design_agent, concept_planner. **Attack those first.**

---

## 3. The Five Phases — Concrete Engineering Plan

### Phase A — Quick Wins on Existing Stack (4-6 weeks)
**Goal**: $5-8/hr → $2-3/hr without architectural change.

| Lever | Mechanism | Savings | Effort |
|---|---|---|---|
| **A1: Aggressive prompt caching** | Anthropic offers 90% discount on cached input tokens (`cache_control: {"type": "ephemeral"}`, 5-min TTL). Today: ~50-70% input cached. Push to 90%+ by restructuring `build_teaching_prompt` so the static portion (system prompt + lesson plan + concept plan + dictionary) is cache-flagged and dynamic chat history is the only uncached portion. | $1.5-2.0/hr | 1 week |
| **A2: Move planning + non-teaching LLM calls to Haiku** | Haiku 4.5 pricing: $1 in / $5 out per M tokens (vs Sonnet $3/$15) = **67% cheaper**. `concept_planner.py`, `plan_doubt`, prompt-rebuild summaries: all structured tasks where Haiku matches Sonnet. | $0.3-0.5/hr | 1 week |
| **A3: Self-host LiveKit** | LiveKit OSS runs on a single $5/mo Hetzner CX22 VPS for hundreds of concurrent rooms. LiveKit Cloud is ~$0.005/participant-min = $0.30/participant-hr; self-hosted is ~$0.01-0.02/hr amortized. | $0.10-0.25/hr | 3 days |
| **A4: Aggressive context trimming** | Today the system prompt carries the full dictionary (often 20+ roles), full lesson plan, full board state summary. Paginate: only top-relevant roles, only current concept ±1, only last 10 board entries. Reduces input tokens by ~50%. | $0.5-1.0/hr | 1 week |
| **A5: Cross-session Redis design cache** | Current `design_bridge` cache is in-memory FIFO, 64 entries, per-worker. Promote to Redis: every Feynman worker shares the same diagram cache. A diagram drawn once for any student is hit for all future students. | $0.3-0.5/hr | 1 week |

**Phase A total savings: $2.7-4.2/hr → New baseline: $1.8-5.3/hr**

**Validation**: ship as feature flags; A/B against control on cache hit rate, response quality (no regression), and per-session cost.

---

### Phase B — Curriculum Pipeline (8-12 weeks)
**Goal**: Eliminate live design_agent gen for ~70% of teaching visuals; eliminate live concept planning entirely.

This is the 13-phase pipeline documented in `docs/design/08-curriculum-graph-pipeline.md`. The two big payoffs:

| Lever | Mechanism | Savings | Effort |
|---|---|---|---|
| **B1: Phase 12 visual pre-generation** | At ingestion time, every Concept with a `visual_hint` gets a `DiagramSpec` pre-computed (via design_agent in batch). Stored on `Concept.pre_generated_visuals`. At session boot, anticipation engine loads from Neo4j. ~70% of teaching diagrams cache-hit. **One-time ingestion cost ~$100-300 per subject** (12-24h runtime). | $0.5-1.0/hr | 4 weeks |
| **B2: Pre-computed ConceptTeachingPlans** | Phase 11 — ConceptTeachingPlan generated once at ingestion (Haiku-grade structured output), not per session. Stored on Concept node. Loaded at boot. Zero LLM cost at session time. | $0.2-0.5/hr | 1 week |

**Phase B total savings: $0.7-1.5/hr → New baseline: $1.1-3.8/hr**

The pipeline itself is a one-time engineering investment. Reference implementation patterns in `/Users/yashbansal/proj/patient-medical-graph` (PMG). 8-12 weeks for the first subject (IGCSE 0580 Math), then 4-6 weeks each for Physics/Chemistry/Biology.

---

### Phase C — Fine-tuned Feynman Teaching Model (12-16 weeks)
**Goal**: Replace 80% of Sonnet teaching turns with a self-hosted fine-tuned model. This is THE big lever.

> **For implementation detail**, see [03 — Fine-Tune Deep-Dive & Tiered Pricing Study](./03-fine-tune-and-tiered-pricing-study.md) Part A. Below is the summary.

#### Why this works

The **TeachLM paper (2024)** validated the core hypothesis: teaching quality comes from **dialogue patterns**, not raw model size. 4-5K SFT + DPO training examples from real tutoring transcripts is the sweet spot. Smaller fine-tuned models can match or *exceed* general frontier models on teaching-specific tasks.

Our memory file (`fine-tuning-research.md`) already has the engineering guide:
- Base: Qwen 2.5 14B (Apache 2.0; instruction-following baseline strong)
- Fine-tune via **QLoRA + Unsloth** (4-bit quantized, single-GPU friendly)
- Training cost: **~$50-200** on rented H100 for 4-6 hours
- Inference: self-hosted with vLLM, continuous batching

#### Stack

| Component | Detail | Per-session cost |
|---|---|---|
| **Inference GPU** | E2E Networks Bangalore RTX 4090 (~₹50-80/hr ≈ $0.70/hr) OR A6000 (₹100-150/hr ≈ $1.50/hr) | Amortized: 5-10 concurrent sessions per GPU via vLLM batching = $0.10-0.30/hr per session |
| **vLLM serving** | Continuous batching, prefix caching, PagedAttention. Latency: TTFT 50-150ms for Qwen 14B on H100; 100-300ms on RTX 4090. | — |
| **Model** | Qwen 2.5 14B Instruct → QLoRA fine-tune → ~16GB VRAM at int4 | — |
| **Routing layer** | Conservative: route to fine-tuned model when student turn is routine (greeting, explanation, basic Q&A). Escalate to Sonnet on novel doubts, comprehension failures, anything tagged hard. ~80/20 split. | — |

#### Cost math

| Path | Cost/hr | % traffic |
|---|---|---|
| Fine-tuned Qwen 14B (E2E India RTX 4090, vLLM batch 8) | $0.20 | 80% |
| Sonnet fallback for hard moments | $0.80 | 20% |
| **Blended** | **$0.32** | 100% |

**vs current Sonnet-only $3-5/hr → Savings: $2.5-4.5/hr**

#### Latency bonus
- Sonnet TTFT from India: 500-1500ms (network + model)
- Qwen 14B in India region: 50-300ms TTFT
- **3-10× faster on the dominant code path**

#### Validation

1. **Quality**: A/B test on 20 real student sessions. Measure doubt resolution rate, comprehension check pass rate, "would you ask Feynman again" survey. Target: no regression vs Sonnet on routine turns.
2. **Reliability**: 99.5% uptime target. Sonnet always available as fallback.
3. **Routing correctness**: track "escalate to Sonnet" rate. Target 15-25%.

**Phase C savings: $1.5-2.5/hr (after routing) → New baseline: $0.5-2.0/hr**

---

### Phase D — Self-host STT + TTS (4-6 weeks)
**Goal**: Eliminate Deepgram + Cartesia spend.

| Lever | Mechanism | Savings | Latency impact |
|---|---|---|---|
| **D1: Self-host Whisper-Large-V3-Turbo** | Co-located on the same GPU as the fine-tuned LLM (Whisper Turbo is ~800M params, 2-3GB VRAM, batches alongside vLLM). Open-source, MIT licensed. Word-level timestamps available. **Latency: 150-250ms** vs Deepgram ~200-400ms — equivalent or better. | $0.40-0.45/hr | -50ms |
| **D2: Self-host XTTS-v2 or Coqui TTS** | XTTS-v2 supports voice cloning, multi-lingual (English + Indic). Co-located on inference GPU. **Latency**: 200-400ms TTFA vs Cartesia 150-250ms. Quality: ~80% of Cartesia per blind tests. **Hybrid option**: Cartesia for Aanya demo + marketing (premium feel), XTTS for scaled operation. | $0.20-0.55/hr | +100ms |

**Phase D savings: $0.6-1.0/hr → New baseline: $0.3-1.4/hr** (range narrowing because we're approaching floor)

**Risk**: TTS quality matters for "magic feel." Mitigate by hybrid — use Cartesia for greetings/transitions (low volume), XTTS for bulk narration (high volume). Or wait until Cartesia ships INR pricing.

---

### Phase E — VL-JEPA Self-hosted Perception (16-20 weeks, post-traction)
**Goal**: Replace Haiku perception with vision-language joint-embedding predictive architecture.

| Lever | Mechanism | Savings | Latency impact |
|---|---|---|---|
| **E1: VL-JEPA self-hosted** | Meta's V-JEPA architecture, fine-tuned on board state ↔ correction pairs. ~142ms inference vs Haiku 600-1500ms. Co-located on inference GPU. | $0.15-0.20/hr | -1.3s on every perception cycle |

**The latency win is the bigger story**: sub-sentence correction becomes feasible. The agent can self-interrupt: *"...this is the hypoten— sorry, this side here is the hypotenuse."* This is impossible with Haiku because the LLM only sees feedback at the next turn (3-30s late).

**Phase E savings: $0.15-0.20/hr → Final baseline: $0.15-1.2/hr**

---

## 4. Final Cost — Where We Land

Per-hour costs after all 5 phases, on an Indian student session:

| Component | $/hr | ₹/hr (₹83/USD) |
|---|---|---|
| Fine-tuned Qwen 14B teaching (80% traffic) | 0.20 | 17 |
| Anthropic Sonnet fallback (20% traffic) | 0.30 | 25 |
| Design agent (Haiku + 70% cache from Phase B) | 0.10 | 8 |
| Concept planner (pre-computed, $0 runtime) | 0.00 | 0 |
| Perception (VL-JEPA self-hosted) | 0.20 | 17 |
| STT (self-hosted Whisper Turbo) | 0.05 | 4 |
| TTS (self-hosted XTTS-v2) | 0.10 | 8 |
| LiveKit (self-hosted) | 0.02 | 2 |
| Postgres + Redis + Neo4j (self-hosted) | 0.05 | 4 |
| Egress + storage | 0.05 | 4 |
| **TOTAL** | **~$1.07/hr** | **~₹89/hr** |

**At 30 hrs/month**: ₹89 × 30 = **₹2,670/month COGS** against **₹10,000 revenue** = **73% gross margin**

**Comfortable margin for**:
- ₹3K CAC amortized over ~8 months
- 5% payment processing
- ~₹2K/month/user operational overhead
- Profit headroom for paid acquisition campaigns

**Worst case** (30 hr power user, 100% Sonnet fallback because fine-tune underperforms):
- Cost ~$2.50/hr × 30 hr = ₹6,225/month COGS = 38% margin. Still positive but tight.

---

## 5. Latency — Where We Land

| Stage | Current (US providers) | After phases A-E (India self-host) | Delta |
|---|---|---|---|
| Voice turn round-trip (E2E) | 1.5-3.0s | **0.4-1.0s** | **-66%** |
| ├ Network India→Anthropic US RTT | 200-400ms | 10-30ms (Bangalore→Bangalore) | -90% |
| ├ LLM TTFT (Sonnet US vs Qwen14B IN) | 500-1500ms | 50-300ms | -80% |
| └ TTS TTFA | 150-250ms | 200-400ms | +100ms (acceptable) |
| Inline pointing (mid-sentence) | ≤300ms | ≤200ms | -33% |
| Diagram cache HIT | ≤800ms | ≤600ms | -25% |
| Diagram cache MISS | 5-15s | 3-8s (Qwen14B JSON path) | -40% |
| Perception cycle | 1.5s (Haiku) | **142ms (VL-JEPA)** | **-90%** |
| Annotation re-point | next LLM turn (3-30s) | **sub-sentence (142ms)** | **transformative** |

The **dominant latency reductions** come from:
1. India region → eliminate cross-continent network hops (-200-300ms everywhere)
2. Fine-tuned smaller model → faster TTFT (-500-1000ms)
3. VL-JEPA perception → sub-sentence correction (-1.3s)

---

## 6. Risk Register — Brutally Honest

| Risk | Severity | Mitigation |
|---|---|---|
| **Fine-tuned Qwen quality regression** | HIGH — could break "magic feel" | (a) Conservative routing — escalate aggressively on uncertainty. (b) Continuous A/B testing on real cohorts. (c) Sonnet always available as fallback. (d) Quality bar is doubt-resolution rate, not subjective preference. |
| **Self-hosted reliability** | MEDIUM — outages, GPU failures, deployment bugs | (a) Multi-AZ on E2E (Bangalore + Mumbai). (b) Anthropic fallback wired automatically on inference failure. (c) Graceful degradation: if all self-hosted fails, fall back to Sonnet (5× cost spike for short duration is survivable). |
| **TTS quality drop** | MEDIUM — magic moments depend on voice feel | (a) Hybrid: Cartesia for first 10 sessions per user (build trust); XTTS for scaled retention. (b) Voice clone Cartesia's character on XTTS so it sounds the same. (c) Reserve Cartesia for emotional beats (greeting, doubt resolution, kid-solves-it). |
| **Curriculum pipeline scope** | HIGH — 13 phases, $100-300 ingest cost each, multi-week effort | (a) Sequence behind Aanya demo. (b) v0 ship with hand-authored LessonPlan (already designed). (c) Pipeline development can parallelize with consumer launch. |
| **Cold start latency** | MEDIUM — first user on a worker hits cold model load | (a) Keep models warm with constant heartbeat (1 req/min). (b) Pre-load on deploy. (c) vLLM continuous batching means cold start is per-worker, not per-request. |
| **CAC reality** | HIGH — $30-80 CAC for Indian parents per memory file | Out of scope here (architecture won't fix marketing) but: don't paid-acquire until retention validated. Warm-network seeding first. |
| **Anthropic pricing changes** | LOW-MEDIUM — they could raise or lower | Self-hosted plan reduces exposure. If Anthropic drops Haiku to $0.50/M, the math gets *better*; if they 2× Sonnet, fine-tune ROI gets *better*. |

---

## 7. Sequencing — What to Build First

Given Aanya demo is the upcoming gate (system design §14.2), the **right sequence is**:

```text
WEEK    0   4   8   12  16  20  24  28  32  36  40
        │   │   │   │   │   │   │   │   │   │   │
Phase A ████████                                       ← 4-6 wk, $2-3/hr immediate
Aanya demo  ████                                       ← validate magic moment
Phase B         ████████████                           ← 8-12 wk, pipeline
Phase D                 ██████                         ← 4-6 wk, STT/TTS self-host
Phase C                     ████████████████          ← 12-16 wk, fine-tune
Phase E                                 ████████████  ← 16-20 wk, post-traction
                │           │                  │
                │           │                  └─ COGS $1.07/hr, ready to scale
                │           └─ COGS ~$1.5/hr, viable for v0 launch at ₹10K
                └─ COGS ~$2.5/hr, viable for soft beta
```

**Phase A alone gets us viable for limited beta** (₹10K/15 hr utilization = 50%+ margin).
**Phase A + B + D gets us to v0 public launch** at the ₹10K/30hr price point with 50%+ margin.
**Phase C completes the moat** — without it we're price-vulnerable to OpenAI dropping GPT-4o-mini further.

---

## 8. Specific Stack Recommendations

### Compute providers

| Use | Recommended | Why | Cost |
|---|---|---|---|
| **GPU inference** (fine-tuned LLM + Whisper + XTTS + VL-JEPA) | **E2E Networks Bangalore** RTX 4090 or A6000 nodes | Indian region, lowest egress, RBI-compliant payments | RTX 4090: $0.60-0.80/hr; A6000: $1.20-1.50/hr |
| **General compute** (FastAPI + LiveKit + workers) | **Hetzner Falkenstein** CX22-CX42 | 80% cheaper than AWS, EU PoP fast to India | $5-30/mo |
| **Postgres + Redis + Neo4j** | **Self-hosted on Hetzner** dedicated boxes | No managed-service premium | $30-60/mo total |
| **CDN + frontend** | **Cloudflare** R2 + Workers + Pages | Zero egress, edge near India | Mostly free tier |

### Model stack

| Layer | Model | Why |
|---|---|---|
| Teaching (80%) | **Fine-tuned Qwen 2.5 14B Instruct** via QLoRA + Unsloth, served by vLLM | TeachLM-validated pattern; small enough to batch; fast TTFT |
| Teaching fallback (20%) | **Anthropic Sonnet 4.6+** with prompt caching | Quality safety net for hard moments |
| Design agent (cache-miss) | **Anthropic Haiku 4.5** or **fine-tuned Qwen 7B** for JSON gen | Structured output, lower cost than Sonnet |
| Concept planner | **Pre-computed at curriculum-ingestion** (Phase B) | Zero runtime cost |
| Perception (5a) | **Anthropic Haiku 4.5** → **VL-JEPA self-hosted** (Phase E) | Visual reasoning, then sub-sentence speed |
| STT | **Whisper-Large-V3-Turbo self-hosted** | English-IN strong, $0.05/hr amortized |
| TTS | **XTTS-v2 self-hosted** + Cartesia hybrid for premium moments | Cost + voice cloning |
| VAD | **Silero** (already done) | Free, local, fast |
| Turn detection | **LiveKit turn-detector** (already done) | Built-in |

### Infrastructure

| Component | Setup |
|---|---|
| LiveKit | Self-hosted OSS on Hetzner CX42 (~$25/mo, 500+ concurrent rooms) |
| Inference orchestration | **vLLM** with continuous batching, prefix caching |
| Model storage | Cloudflare R2 (free egress) |
| Observability | OpenTelemetry → Tempo + Loki + Grafana self-hosted; SessionAudit unchanged |
| Payment processing | **Razorpay** (Indian, INR-native, ~2.5% fees vs Stripe ~3.5% + currency conversion) |

---

## 9. What Counts as "Proven" vs "Estimated" Here

| Claim | Status |
|---|---|
| Anthropic prompt caching gives 90% discount on cached input | **PROVEN** (Anthropic docs) |
| Haiku 4.5 at $1/$5 per M tokens | **PROVEN** (current public pricing) |
| Qwen 2.5 14B + QLoRA + Unsloth fits on single 24GB GPU | **PROVEN** (Unsloth benchmarks) |
| vLLM continuous batching handles 5-10 concurrent users on RTX 4090 | **PROVEN** (vLLM benchmarks Llama 13B class) |
| Whisper-Large-V3-Turbo matches Deepgram accuracy at 150-250ms | **PROVEN** (HuggingFace benchmarks) |
| XTTS-v2 achieves ~80% Cartesia quality blind | **ESTIMATED** (no direct head-to-head; informed by demos) |
| Fine-tuned Qwen 14B matches Sonnet on teaching tasks | **ESTIMATED** (TeachLM validates pattern; not yet our domain-specific) |
| 70% diagram cache hit rate after Phase 12 | **ESTIMATED** (depends on curriculum coverage of teaching cases) |
| VL-JEPA gives 142ms perception | **MEASURED IN PAPER** (Meta's V-JEPA 2 results, not yet domain-tuned) |
| 80/20 fine-tune/Sonnet routing split | **ESTIMATED** (calibrated by analogous EdTech routing systems; needs A/B) |
| ₹89/hr COGS final | **DERIVED** from above; conservative |

The **biggest unknowns** are: XTTS quality, fine-tune teaching match, diagram cache hit rate, VL-JEPA domain transfer, routing split. They require live validation. Suggest milestone checks at Phase C end (after fine-tune live for 4 weeks) to recalibrate the model.

---

## 10. The Honest Verdict

**Is ₹10K for 30 hr/month at sustainable margins possible? Yes.**

**Is it possible without 6-9 months of focused engineering investment? No.**

**The single highest-leverage move** is Phase C (fine-tuned Feynman model on Indian GPU infra). It cuts the dominant cost line by 80% AND cuts the dominant latency line by 50-90%. Everything else is around the edges by comparison.

**Order of investment for max-leverage-first**:
1. Phase A wins immediately (1 month, $2-3/hr savings, no risk to product)
2. Phase B is the highest-leverage pre-product-launch work (curriculum pipeline = compounding moat)
3. Phase C is the long-term cost moat
4. Phase D is operationally important for unit economics scale
5. Phase E is the latency moat that makes Feynman feel super-human

**Bottom line**: today at ~$5-8/hr we cannot sustainably price at ₹10K/30hr — we'd lose money on power users and barely break even on average users after CAC. With Phase A alone (4-6 weeks, no new dependencies) we drop to $2-3/hr and the price point is viable for a tight beta. With Phase B + D we hit $1.50/hr which is sustainable across utilization patterns. Phase C is where we get to **$1.07/hr COGS with 73% gross margin** which is the foundation for paid acquisition and scale. The path is real and the math holds; the engineering risk is concentrated in the fine-tune quality validation, which is testable on real students for ~$200 and 4-6 weeks.

---

## See Also

- [03 — Fine-Tune Deep-Dive & Tiered Pricing Study](./03-fine-tune-and-tiered-pricing-study.md) — implementation depth for Phase C; analysis of pre-loaded ₹5K/30hr tier; tiered pricing recommendation.
- [01 — Consumer Product Thesis](./01-consumer-product-thesis.md) — the ₹4K/month single-subject ↔ ₹6–8K/month all-subjects original pricing thesis this plan operationalizes.
- `docs/design/08-curriculum-graph-pipeline.md` — Phase B's 13-phase ingestion pipeline.
- `docs/design/16-diagram-awareness-rearchitecture.md` — Phase 5a perception loop (already shipped through 5a-3).
- `~/.claude/projects/-Users-yashbansal-proj-feynman/memory/fine-tuning-research.md` — engineering guide for Phase C training.
