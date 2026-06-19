# VIDEO_TO_TEACHING_ENGINE.md

> Companion to `feynman_corpus_spec.md` and `TRAINING_PLAN.md`.
> Goal: turn a few hundred 3b1b-style teaching videos into a fine-tuned policy that lets the
> Feynman real-time agent **teach any new topic** with animations synced to TTS narration —
> in the browser, not as video.

---

## 0. The one idea (read this first)

You are **not** fine-tuning a model "on videos." You are fine-tuning a model on
`(student state + concept) → (pedagogical move + narration + animation directives)` triples
that you _extract_ from the videos. The video is the **source of supervision**, never the
training target.

And the output is **not** free-form animation code (Manim/Motion Canvas). It is a small,
**constrained scene DSL** (JSON) that a deterministic web renderer turns into animation. This one
choice is what makes the system (a) real-time, (b) robust enough to never "fail to render" live,
and (c) **verifiable** — which you need for the quiz-proxy RL reward.

Extraordinary teaching on _unseen_ topics is a **generalization property**. It can't come from
memorizing what's in the videos. It comes from learning a _content-independent policy_: how to
teach, decoupled from what is being taught. Three design decisions produce that generalization:

1. **Annotate teaching moves** in the data → the model learns the _mapping_, not the content.
2. **Keep facts in retrieval / Neo4j** → the model is never forced to memorize subject matter.
3. **Reward learning outcomes** (quiz proxy) → optimization pushes toward whatever generalizes.

---

## 1. What the literature actually supports

There is **no single published system** that does "fine-tune on teaching videos → real-time, synced,
web-native teaching agent" end to end. But every piece is independently demonstrated, and the hardest
piece is the freshest:

- **Speech-Synchronized Whiteboard Generation** (Prasad & Mahapatra, 2026 — arXiv 2603.25870).
  Closest precedent. Fine-tuned **Qwen2-VL-7B with LoRA** to emit **Excalidraw JSON stroke sequences
  synced to narration**, with millisecond-precision timestamps, across 8 STEM domains. Two findings
  that drive this whole plan: **explicit timestamp conditioning** dramatically improves alignment, and
  the model **generalized to unseen STEM topics** — _from only 24 demonstrations_, with no RL. This is
  your idea minus the agent loop, and it says the core mapping is learnable from very little data.

- **TheoremExplainAgent / TheoremExplainBench** (Ku et al., ACL 2025 — arXiv 2502.19400).
  Two-agent design: a **planner** (story + narration) and a **coder** (Manim). o3-mini hit **93.8%
  success / 0.77** on 240 theorems, scored on accuracy, depth, logical flow, visual relevance, layout.
  Crucially, its dominant failures were **Manim code hallucinations, LaTeX errors, layout problems** —
  the empirical case _against_ free-form code at inference time, and the reason we use a DSL.

- **AutomaTikZ / DeTikZify** (Belouadi et al., 2023/2024 — arXiv 2310.00367, 2405.15306).
  Fine-tuning an open model on `(intent → graphics-as-code)` **beat GPT-4 / Claude** on figure quality;
  analysis showed generalization, not memorization. DeTikZify adds **MCTS self-refinement** and flags
  **DPO / RL from reward functions** as the next step — i.e. exactly your post-training stack.

- **AutoLectures** (Holmberg, 2025 — arXiv 2505.02966). The sync trick: the LLM writes narration with
  inline `highlight(...)` markers; those markers drive both TTS and the visual cue alignment.

- **WonderFlow / Data Player** (IEEE VIS) — narration-centric "narration–animation interplay" design.

- **AnimatedLLM / Transformer Explainer** — the _deployment_ pattern: precompute a structured
  representation, serialize to JSON, render **entirely client-side in the browser**.

Bottom line: feasibility is well-supported; you are composing known-good pieces, and the riskiest one
(synced structured drawing from few examples) is the one with the strongest recent evidence.

---

## 2. Architecture overview

```mermaid
flowchart TD
  V[Teaching videos] --> SRC{Manim/code source available?}
  SRC -->|yes: 3b1b/videos, your own| A1[Parse code + transcript, align by timestamp]
  SRC -->|no| A2[ASR + scene-cut + VLM caption + diff + align]
  A1 --> T[(narration, animation, timing) triples]
  A2 --> T
  T --> D[Transcode to Scene DSL + annotate teaching moves]
  D --> SFT[Stage 1: QLoRA SFT cold-start]
  SFT --> DPO[Stage 2: DPO/ORPO on good/bad teaching pairs]
  DPO --> RL[Stage 3: GRPO / RLVR on render-validity + quiz-proxy reward]
  RL --> DIST[Stage 4: rejection-sampling + distillation flywheel]
  DIST --> POL[Teaching-policy model]
  POL --> PLAN[Serve: Planner storyboard + moves]
  PLAN --> GEN[Policy streams DSL beats]
  GEN --> TTS[TTS w/ word timestamps]
  GEN --> REND[Web renderer: SVG/Canvas/D3/KaTeX]
  TTS --> SCHED[Scheduler fires cues on word boundaries]
  REND --> SCHED
  KG[(Neo4j knowledge graph)] --> GEN
```

**Model choice.** The deployed teaching policy can be a **text LLM** (e.g. Qwen3-14B, or 8B/4B for
lower latency): at inference the input is text (question + dialogue state + retrieved facts) and the
output is the DSL. You do **not** need a vision model in the live loop. Vision is used as a _tool_
in two offline places: (1) extracting data from videos, (2) optionally a VLM "looks" at a rendered
frame to score layout quality during RL. Go to a VLM **policy** only if the live agent must also see
student artifacts (e.g. a photo of their scratch work). Note: vLLM doesn't serve LoRA on vision
layers, so a text-LLM policy is also the easier thing to serve fast.

---

## 3. The Scene DSL

A teaching session is an **ordered list of beats**. Each beat is one self-contained pedagogical
step: a chunk of narration + the animation directives that should fire while it's spoken + cue
timing. Beats are **streamable** — emit one, start TTS + rendering immediately, generate the next.
This maps directly onto Mayer's _segmenting_ and _temporal-contiguity_ principles (Section 4).

### 3.1 Why a DSL beats free-form code

| Property                     | Free-form Manim/MotionCanvas code     | Constrained Scene DSL (this)                  |
| ---------------------------- | ------------------------------------- | --------------------------------------------- |
| Can fail to render live      | **Yes** (TEA's #1 failure)            | No — invalid output is rejected before render |
| Generation latency           | High (long code, then compile/render) | Low (short JSON, no compile)                  |
| Synchronization              | Hard                                  | Built in (cue markers)                        |
| Learnable from little data   | Harder                                | Easier (small vocabulary)                     |
| **Verifiable for RL reward** | Hard                                  | **Trivial** (schema + render check)           |
| Expressivity ceiling         | Maximal                               | Bounded by your primitives (extend as needed) |

You keep Manim as a **data source** (and optional offline pre-render of canned segments), not as the
runtime.

### 3.2 Schema (informal)

```jsonc
{
  "concept": "derivative_as_local_slope",
  "target_misconception": "thinks derivative = average slope over the visible interval",
  "beats": [
    {
      "id": "b1",
      "move": "concrete_instance_first", // from the teaching-move taxonomy (Section 4)
      "narration": "Forget formulas for a second. Here's a curve, and here's a point on it [[cue:c1]]. Watch what happens as we zoom in [[cue:c2]].",
      "directives": [
        { "op": "draw_axes", "id": "ax", "x": [-3, 3], "y": [-1, 5] },
        {
          "op": "plot_function",
          "id": "f",
          "fn": "x**2",
          "domain": [-3, 3],
          "color": "accent",
        },
        { "op": "draw_point", "id": "p", "on": "f", "x": 1, "at": "c1" },
        {
          "op": "camera_zoom",
          "target": "p",
          "scale": 8,
          "duration": 1.6,
          "at": "c2",
        },
      ],
    },
    {
      "id": "b2",
      "move": "surface_and_resolve_misconception",
      "narration": "Up close, the curve looks like a straight line [[cue:c3]]. THAT slope — not the slope across the whole curve — is the derivative here.",
      "directives": [
        {
          "op": "draw_tangent",
          "id": "t",
          "on": "f",
          "x": 1,
          "at": "c3",
          "style": "dashed",
        },
        { "op": "highlight", "target": "t", "at": "c3" },
        {
          "op": "write_equation",
          "id": "eq",
          "latex": "f'(1)=2",
          "near": "t",
          "at": "c3",
        },
      ],
    },
  ],
}
```

### 3.3 Primitive vocabulary (starter set — extend per domain)

- **Math/graphs:** `draw_axes`, `plot_function`, `plot_parametric`, `number_line`, `draw_point`,
  `draw_tangent`, `draw_vector`, `draw_shape`, `draw_angle`, `write_equation` (LaTeX→KaTeX),
  `label`, `brace`, `area_under_curve`, `riemann_rects`.
- **Structure/animation:** `highlight`, `fade_in`, `fade_out`, `move`, `transform` (a→b),
  `morph`, `group`, `ungroup`, `arrange`, `camera_pan`, `camera_zoom`.
- **Diagrammatic:** `graph_node`, `graph_edge`, `box`, `arrow`, `table`, `draw_freehand` (Excalidraw-style path for whiteboard feel).
- **3D (physics):** `scene3d`, `mesh`, `field_lines`, `vector_field` (Three.js).

Every `op` maps to one deterministic renderer function. Targets carry `id`s so later beats can
`transform`/`highlight`/`move` earlier objects. Timing is **relative**: narration has `[[cue:cN]]`
markers; a directive with `"at": "cN"` fires when TTS reaches that word (Section 10).

### 3.4 Renderer stack (web-native, real-time)

- **KaTeX/MathJax** — equation typesetting (non-negotiable).
- **D3 / function-plot / JSXGraph** — plots, graphs, geometry, transitions.
- **SVG + GSAP** (or **Motion Canvas** as substrate) — general animated objects/transforms.
- **Three.js** — 3D physics when needed.
- **Excalidraw element model** — hand-drawn pedagogical style (this is what the 2026 whiteboard paper used).

---

## 4. Pedagogy layer — the part that makes teaching _transfer_

This is the section that determines whether the agent is merely an animator or an **extraordinary
teacher on topics it never saw in training**. The mechanism: the SFT data is annotated with
_teaching moves_, the moves are grounded in learning science, and the RL reward optimizes _learning
outcomes_. The model learns **when to do what**, independent of subject matter.

### 4.1 Teaching-move taxonomy (the `move` field)

Use your existing taxonomy from `feynman_corpus_spec.md`. A solid core set:

- `concrete_instance_first` — example before abstraction.
- `analogy` — map to a familiar domain (Feynman's signature move).
- `first_principles_decomposition` — break to axioms/primitives, rebuild.
- `surface_and_resolve_misconception` — state the likely wrong model, create conflict, resolve.
- `contrasting_cases` — show what it _is_ by contrast with what it _isn't_ (variation theory).
- `worked_example` → `faded_example` → `independent` — fading guidance (worked-example effect).
- `dual_coding` — pair the spoken idea with a simultaneous visual (not redundant on-screen text).
- `progressive_disclosure` — reveal in steps, never all at once.
- `check_for_understanding` / `retrieval_prompt` — make the student predict/recall.
- `summarize_and_link` — compress and connect to prior knowledge.

### 4.2 Learning-science grounding (why these moves, and how they shape DSL + reward)

- **Mayer's multimedia principles** (the whiteboard paper grounds on Mayer):
  - _Temporal contiguity_ → narration and its matching animation fire **together**. This is the entire
    reason for the cue-timing system; reward alignment error.
  - _Segmenting_ → beats. _Signaling_ → `highlight`. _Coherence_ → penalize extraneous directives.
  - _Modality / redundancy_ → speak it + show a graphic; **don't** dump identical text on screen and
    read it aloud. Encode as a DSL lint rule and a reward penalty.
  - _Pre-training_ → introduce key terms/objects before using them (a `move` ordering constraint).
- **Cognitive Load Theory (Sweller).** Sequence intrinsic load simple→complex; minimize extraneous
  load (clean layout — note TEA's layout failures are _literally_ extraneous load); the worked→faded
  progression manages this. Expertise-reversal: faded guidance as the student improves.
- **Feynman technique.** Plain language, find the gap, analogy, first principles → directly the
  `analogy` / `first_principles_decomposition` / `summarize_and_link` moves.
- **Constructivism / misconception-based instruction.** Diagnose the wrong model, induce conflict,
  resolve → `surface_and_resolve_misconception`. The DSL has an explicit `target_misconception` field.
- **Retrieval practice & spacing.** `check_for_understanding` / `retrieval_prompt`; this is also what
  the quiz proxy operationalizes as the reward.
- **Dual coding (Paivio).** Verbal + visual channels → `dual_coding`.

### 4.3 How transfer actually happens

At inference, the policy gets `(new concept structure from Neo4j) + (student's current
(mis)understanding)`. It has learned, from the move-annotated corpus, the **function**
`(concept shape, confusion) → (move, narration, animation)`. Because facts live in the graph and the
reward only credits _measured learning_, the optimizer can't win by memorizing content — it wins by
acquiring transferable teaching craft. The whiteboard paper's cross-topic generalization from 24 demos
is the empirical hint that this function is learnable and travels to unseen topics.

---

## 5. Data preparation

### 5a. The source-code path (do this if you can — it skips vision entirely)

If you authored your own videos in **Manim or any code-based tool**, you already have the gold
representation (script + code). For 3b1b-style external content, **3b1b publishes everything**:
`3b1b/videos` (full Manim source) + `3b1b/captions` (transcripts).

> ⚠️ **Licensing.** The Manim _engine_ is MIT, but **`3b1b/videos` is CC BY-NC-SA (NonCommercial)**.
> If the Feynman Engine is commercial, training on that source has real exposure — get this checked
> before it's load-bearing. **Your own videos carry no such issue.** Many other creators (e.g.
> vcubingx) publish Manim source under their own terms — check each.

```python
# extract_from_source.py  — align transcript with Manim scene by timestamp, emit triples.
# This is a SKELETON: the Manim parsing depends on how scenes are written. Treat TODOs as glue.
import ast
from pathlib import Path

def parse_transcript(srt_or_vtt_path: str):
    """Return [(t_start, t_end, text), ...]."""
    # TODO: use webvtt-py or pysrt. Returns time-ordered narration spans.
    ...

def parse_manim_scene(py_path: str):
    """Return [(approx_t, animation_action_dict), ...] for a Manim Scene.

    Approach: walk self.play(...) / self.add(...) / self.wait(t) calls in order; each .play is an
    animation step whose duration defaults to run_time (or 1s). Accumulate a virtual clock so each
    step gets an approximate start time, then map the Manim mobjects/animations onto YOUR DSL ops.
    """
    src = Path(py_path).read_text()
    tree = ast.parse(src)
    clock, steps = 0.0, []
    # TODO: visit Call nodes for self.play/self.wait/self.add; advance clock by run_time/wait;
    #       translate Write/Create/Transform/FadeIn/etc + the target mobject into a DSL directive.
    return steps

def align(transcript, anim_steps):
    """Greedy timestamp alignment: attach each animation step to the narration span it overlaps."""
    triples = []
    for (t0, t1, text) in transcript:
        acts = [a for (t, a) in anim_steps if t0 <= t < t1]
        triples.append({"t_start": t0, "t_end": t1, "narration": text, "directives": acts})
    return triples

# for each video: triples = align(parse_transcript(vtt), parse_manim_scene(scene_py))
# then hand to transcode_to_dsl() + annotate_moves() below.
```

### 5b. The video-extraction path (no source available)

Build a "video → structured teaching script" transcriber: ASR (with word timestamps) + scene-cut
keyframes + VLM captioning + OCR/MathPix for equations + frame-diff to infer the _action_ + align,
then **validate by re-rendering and visually comparing** (DeTikZify/TEA-style self-check loop).

```python
# extract_from_video.py — SKELETON. Runs on free Kaggle (CPU for cuts, T4 for ASR + local VLM).
# pip: faster-whisper / whisperx, scenedetect, opencv-python, (a VLM via transformers or an API)
import cv2
from scenedetect import detect, ContentDetector
# import whisperx  # word-level timestamps via forced alignment

def asr_with_word_timestamps(audio_path):
    # model = whisperx.load_model("large-v3", device="cuda")
    # result = model.transcribe(audio_path); aligned = whisperx.align(...)
    # return [(word, t_start, t_end), ...]
    ...

def scene_keyframes(video_path, threshold=27.0):
    scenes = detect(video_path, ContentDetector(threshold=threshold))
    cap = cv2.VideoCapture(video_path); fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    for (start, end) in scenes:
        mid = int((start.get_frames() + end.get_frames()) / 2)
        cap.set(cv2.CAP_PROP_POS_FRAMES, mid); ok, img = cap.read()
        if ok: frames.append((mid / fps, img))
    cap.release()
    return frames  # [(t_seconds, frame_bgr), ...]

def caption_frame(frame_bgr):
    """VLM: 'List the visual objects, their positions, and any equations (as LaTeX) on screen.'"""
    # Use Qwen2.5-VL-7B locally (Unsloth FastVisionModel) OR a frontier VLM API for higher quality.
    # OCR math separately with MathPix or pix2tex for reliable LaTeX.
    ...

def diff_to_action(prev_caption, curr_caption):
    """Infer what CHANGED between two keyframes → a DSL directive (appeared / transformed / highlighted)."""
    ...

def build_triples(video_path, audio_path):
    words = asr_with_word_timestamps(audio_path)
    kfs   = scene_keyframes(video_path)
    caps  = [(t, caption_frame(f)) for (t, f) in kfs]
    triples, prev = [], None
    for (t, cap) in caps:
        action = diff_to_action(prev, cap) if prev else {"op": "scene_init", "state": cap}
        narration = " ".join(w for (w, ws, we) in words if abs(ws - t) < 4.0)  # window; refine
        triples.append({"t": t, "narration": narration, "directives": [action]})
        prev = cap
    return triples
```

### 5c. Transcode to DSL + annotate moves + build SFT/DPO datasets

```python
# build_datasets.py
import json

DSL_SYSTEM = (
  "You are a master STEM teacher. Given a concept, the student's current understanding, and grounded "
  "facts, produce a teaching plan as a JSON list of BEATS in the Scene DSL. Each beat has: move, "
  "narration (with [[cue:cN]] markers), and directives (typed ops with `at` cues). Teach for "
  "understanding; never state quiz answers verbatim."
)

def annotate_move(beat) -> str:
    """Label the beat's pedagogical move. Bootstrap with an LLM-as-judge over (narration, directives),
    then hand-correct a seed set. A few hundred labeled beats is plenty to start."""
    ...  # returns one of the taxonomy strings

def to_sft_record(concept, student_state, grounded_facts, beats):
    user = json.dumps({"concept": concept, "student_state": student_state, "facts": grounded_facts})
    target = json.dumps({"beats": beats}, ensure_ascii=False)
    return {"messages": [
        {"role": "system", "content": DSL_SYSTEM},
        {"role": "user", "content": user},
        {"role": "assistant", "content": target},
    ]}

def to_dpo_record(prompt_msgs, chosen_beats, rejected_beats):
    return {"prompt": prompt_msgs,
            "chosen": json.dumps({"beats": chosen_beats}),
            "rejected": json.dumps({"beats": rejected_beats})}
# Build REJECTED examples by: ablating a move, dumping redundant on-screen text (Mayer violation),
# removing cue markers (desync), or using a weaker base-model generation vs. the extracted gold.
```

**Data volume.** A few hundred videos → a few thousand beats. That is comfortably enough for the SFT
cold-start (recall: 24 demos generalized in the whiteboard study). Spend effort on **move-annotation
quality and clean DSL targets**, not on raw quantity.

---

## 6. Fine-tuning methods — best vs. the others

| Method                        | VRAM                            | Quality                          | When                              | Verdict for you                           |
| ----------------------------- | ------------------------------- | -------------------------------- | --------------------------------- | ----------------------------------------- |
| **Full fine-tune**            | Huge (infeasible on budget >3B) | Highest ceiling                  | Big budget, broad behavior change | ❌ Skip                                   |
| **LoRA** (16-bit)             | Medium                          | ~full-FT on narrow tasks         | When you have a 24GB+ GPU         | ✅ If renting                             |
| **QLoRA** (4-bit base + LoRA) | Low (**7–14B on a free T4**)    | ~LoRA, slightly slower           | Free-tier / consumer GPU          | ✅✅ **Default cold-start**               |
| Prefix/prompt tuning, (IA)³   | Tiny                            | Weaker                           | Ultra-light                       | ❌ Not worth it                           |
| **DPO**                       | = QLoRA                         | Aligns to preferences post-SFT   | After SFT, with pairs             | ✅ Standard preference step               |
| **ORPO**                      | = QLoRA                         | SFT+preference in **one** stage  | Save a stage / save compute       | ✅ Good budget alternative to SFT→DPO     |
| **KTO**                       | = QLoRA                         | Needs only **binary** good/bad   | When pairwise labels are hard     | ✅ Easiest data                           |
| **GRPO / GSPO (RLVR)**        | Med (needs rollouts)            | Optimizes the _actual objective_ | Once outputs render reliably      | ✅✅ **The quiz-proxy stage**             |
| RLHF + PPO + reward model     | High                            | Powerful but heavy               | Large teams                       | ❌ GRPO supersedes for verifiable rewards |
| **On-policy distillation**    | Low (student)                   | Cheap quality transfer           | Flywheel from a strong teacher    | ✅ Use as flywheel                        |

**Recommended path (instantiates your six-stage plan):**
`QLoRA SFT` → `DPO (or ORPO)` → `GRPO/RLVR (render-validity + quiz-proxy + pedagogy)` →
`rejection-sampling + distillation flywheel`.

**Tooling: use Unsloth.** It's ~2× faster, ~70% less VRAM, fits Qwen3-14B on a **free T4**, supports
LoRA/QLoRA + DPO + **GRPO/GSPO** (even VLM-RL on consumer GPUs). To preserve reasoning, **mix ~75%
reasoning-style examples with ~25% direct** so the base model doesn't forget how to reason.

---

## 7. Training code

> All snippets target current Unsloth + TRL. They are accurate skeletons — wire in your dataset paths
> and reward bodies. Build checkpointing into every run (free sessions disconnect).

### 7a. SFT (QLoRA, text policy)

```python
# sft.py  — runs on a free Kaggle/Colab T4
from unsloth import FastLanguageModel
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name      = "unsloth/Qwen3-14B",   # use 8B/4B for lower live latency
    max_seq_length  = 4096,
    load_in_4bit    = True,                   # QLoRA
)
model = FastLanguageModel.get_peft_model(
    model, r = 32, lora_alpha = 32, lora_dropout = 0, bias = "none",
    target_modules = ["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    use_gradient_checkpointing = "unsloth", random_state = 3407,
)

ds = load_dataset("json", data_files="sft_records.jsonl", split="train")  # from build_datasets.py
def fmt(ex): return {"text": tokenizer.apply_chat_template(ex["messages"], tokenize=False)}
ds = ds.map(fmt)

trainer = SFTTrainer(
    model = model, tokenizer = tokenizer, train_dataset = ds,
    args = SFTConfig(
        per_device_train_batch_size = 2, gradient_accumulation_steps = 4,
        warmup_ratio = 0.05, num_train_epochs = 2, learning_rate = 2e-4,
        logging_steps = 10, optim = "adamw_8bit", lr_scheduler_type = "cosine",
        output_dir = "ckpt-sft", save_steps = 100,
    ),
)
trainer.train()
model.save_pretrained("feynman-sft-lora"); tokenizer.save_pretrained("feynman-sft-lora")
```

### 7b. DPO (or swap `ORPOTrainer`/`KTOTrainer` — same shape)

```python
# dpo.py
from unsloth import FastLanguageModel
from trl import DPOTrainer, DPOConfig
from datasets import load_dataset

model, tokenizer = FastLanguageModel.from_pretrained("feynman-sft-lora", max_seq_length=4096, load_in_4bit=True)
model = FastLanguageModel.get_peft_model(model, r=32, lora_alpha=32, use_gradient_checkpointing="unsloth")

ds = load_dataset("json", data_files="dpo_records.jsonl", split="train")  # prompt / chosen / rejected
trainer = DPOTrainer(model=model, args=DPOConfig(
    per_device_train_batch_size=1, gradient_accumulation_steps=8, beta=0.1,
    learning_rate=5e-6, num_train_epochs=1, optim="adamw_8bit", output_dir="ckpt-dpo"),
    train_dataset=ds, tokenizer=tokenizer)
trainer.train(); model.save_pretrained("feynman-dpo-lora")
```

### 7c. GRPO / RLVR (the quiz-proxy stage)

```python
# grpo.py  — RL with verifiable rewards; no separate reward model
from unsloth import FastLanguageModel
from trl import GRPOConfig, GRPOTrainer
from datasets import load_dataset
from rewards import render_validity_reward, quiz_proxy_reward, leakage_penalty, pedagogy_reward

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="feynman-dpo-lora", max_seq_length=4096, load_in_4bit=True,
    fast_inference=True, gpu_memory_utilization=0.6,   # vLLM for fast rollouts
)
model = FastLanguageModel.get_peft_model(model, r=32, lora_alpha=32, use_gradient_checkpointing="unsloth")

# prompts only: {concept, student_state, facts}; the model generates beats, rewards score them
prompts = load_dataset("json", data_files="rl_prompts.jsonl", split="train")

trainer = GRPOTrainer(
    model = model,
    reward_funcs = [render_validity_reward, pedagogy_reward, quiz_proxy_reward, leakage_penalty],
    args = GRPOConfig(
        per_device_train_batch_size = 4, gradient_accumulation_steps = 4,
        num_generations = 8, max_prompt_length = 1024, max_completion_length = 1536,
        learning_rate = 5e-6, optim = "adamw_8bit", lr_scheduler_type = "cosine",
        temperature = 0.9, num_train_epochs = 2, output_dir = "ckpt-grpo",
    ),
    train_dataset = prompts, tokenizer = tokenizer,
)
trainer.train(); model.save_pretrained("feynman-grpo-lora")
```

**Reward curriculum:** start RL with `render_validity_reward + pedagogy_reward` only (cheap, makes
output well-formed + well-structured). Add `quiz_proxy_reward + leakage_penalty` once >~95% of
generations render — that's when outcome optimization is meaningful and the expensive student
simulation isn't wasted on broken outputs.

### 7d. Distillation flywheel (cheap quality)

Generate many candidate teaching plans (high temperature), keep only those that pass render-validity
**and** score well on the quiz proxy (rejection sampling), then SFT the small model on those winners.
Optionally use a frontier model as a one-time "teacher" to produce ideal plans for hard concepts and
distill those in. This is your "rejection-sampling → distillation" thread, and it's far cheaper than
more RL.

---

## 8. Reward functions (stubs)

```python
# rewards.py
# TRL GRPO reward signature: f(prompts, completions, **kwargs) -> list[float]  (one score per completion)
import json
from typing import List

# ---- 1. Render-validity: free, automatic, attacks TEA's #1 failure mode -------------------------
def render_validity_reward(prompts, completions, **kwargs) -> List[float]:
    scores = []
    for c in completions:
        try:
            plan = json.loads(c)
            ok, n_err = validate_and_dryrun(plan)     # schema check + headless renderer dry-run
            scores.append(1.0 if ok else max(-1.0, -0.2 * n_err))
        except Exception:
            scores.append(-1.0)                        # didn't even parse
    return scores

def validate_and_dryrun(plan) -> tuple[bool, int]:
    """Validate against the DSL JSON schema; check every `at` cue exists in its beat's narration;
    check every directive `op` is known and targets resolve; run the deterministic renderer headlessly
    (e.g. node + jsdom/Playwright) and count thrown errors. Returns (ok, num_errors)."""
    ...

# ---- 2. Quiz proxy: the transferable teaching-effectiveness signal ------------------------------
def quiz_proxy_reward(prompts, completions, **kwargs) -> List[float]:
    scores = []
    for prompt, c in zip(prompts, completions):
        concept = extract_concept(prompt)
        plan = safe_load(c)
        if plan is None:
            scores.append(0.0); continue
        lesson_text = render_to_studyable_text(plan)   # narration + described visuals (what a student "sees")
        quiz = get_quiz_for(concept)                    # held-out questions; NOT shown to the teacher model
        student = simulate_student(lesson_text, quiz)   # a separate LLM that only saw the lesson
        scores.append(grade(student, quiz))             # fraction correct in [0,1]
    return scores

def simulate_student(lesson_text, quiz):
    """Fresh LLM context: 'You just watched this lesson: <lesson_text>. Answer:' + quiz. Use a model
    that has NOT been told the answers. Optionally model a 'novice' persona for difficulty calibration."""
    ...

# ---- 3. Leakage penalty: prevents teaching-to-the-test / answer parroting -----------------------
def leakage_penalty(prompts, completions, **kwargs) -> List[float]:
    pens = []
    for prompt, c in zip(prompts, completions):
        quiz = get_quiz_for(extract_concept(prompt))
        lesson = render_to_studyable_text(safe_load(c) or {})
        overlap = max_answer_overlap(lesson, quiz)      # n-gram + semantic match of answers in lesson
        pens.append(-1.0 * overlap)                     # in [-1, 0]
    return pens

# ---- 4. Pedagogy reward: rubric grader grounded in learning science -----------------------------
def pedagogy_reward(prompts, completions, **kwargs) -> List[float]:
    """LLM-as-judge (or a learned generative reward model) scoring, per the Mayer/CLT rubric:
       + move-appropriateness for the concept & misconception
       + temporal contiguity (cues present and sensible)
       + signaling (highlights the right thing)
       + segmenting (beat granularity)
       - extraneous load (redundant on-screen text, decorative noise)  [Mayer coherence/redundancy]
       - missing pre-training of terms before use
       Return a scalar in [0,1]. Anchor with a few hand-scored exemplars to reduce judge variance."""
    ...

# Composite weighting is handled by GRPO summing the reward_funcs; tune weights by scaling each fn's
# output range, e.g. render in [-1,1], pedagogy in [0,1], quiz in [0,1], leakage in [-1,0].
```

---

## 9. Cost & free-compute plan

### 9.1 Truly-free compute (2026)

| Platform               | Free GPU                                    | Quota                                                                                             | Notes                                                                                                                                |
| ---------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Kaggle Notebooks**   | **dual T4 (≈30 GB combined)** or P100 16 GB | **30 h/week**, 9–12 h sessions                                                                    | **Best free option.** Background execution; **73 GB persistent storage** survives sessions; commercial use of trained models allowed |
| Google Colab (free)    | T4 16 GB                                    | ~15–30 h/week (dynamic, not guaranteed)                                                           | 12 h cap, 90 min idle disconnect, no terminal/background on free; disposable VM                                                      |
| Lightning AI (Studios) | mixed                                       | ~22 GPU-h/month free                                                                              | Longer uninterrupted sessions                                                                                                        |
| Saturn Cloud           | T4-class                                    | ~30 h/month                                                                                       |                                                                                                                                      |
| SageMaker Studio Lab   | T4-class                                    | session-limited                                                                                   | No credit card                                                                                                                       |
| HF Spaces              | community T4 grants                         | grant-based                                                                                       | For _useful/educational_ open-source demos                                                                                           |
| GCP new-user credit    | T4/A100/V100                                | **$300**, 90-day expiry                                                                           | ~100 h T4 or ~30–40 h A100                                                                                                           |
| Student/startup        | varies                                      | GitHub Student Pack + Azure for Students ($100/yr); AWS Activate; Google for Startups ($2k–$200k) | Apply if eligible                                                                                                                    |

**Rotation strategy** (community-reported): Kaggle + Colab + Lightning + Paperspace ≈ **50+ free
GPU-h/week** — enough to do what would cost **$100–200** on commercial cloud. Always checkpoint to
Drive/Kaggle datasets.

### 9.2 Cheap rentals (when free isn't enough — mainly the RL stage)

| Provider    | GPU                                 | ~Price/hr                                                        |
| ----------- | ----------------------------------- | ---------------------------------------------------------------- |
| **Vast.ai** | RTX 3090 24 GB / **RTX 4090 24 GB** | **$0.07–0.20 / $0.33** (individual hosts — check reliability)    |
| **RunPod**  | spot / **A100** / **H100**          | from **$0.20** / **~$0.99** / **<$2.50** ($5–10 new-user credit) |
| Lambda Labs | A100 / H100                         | <$1 / <$2.50                                                     |
| Modal       | A100 / H100                         | ~$2.80 / ~$3.95, **per-second**, zero idle, <5 s cold start      |
| GMI Cloud   | H100 / H200                         | $2.10 / $2.50                                                    |

### 9.3 What each stage actually costs

- **Data extraction:** CPU + ASR (free Kaggle T4). Captioning: free if you run a local VLM
  (Qwen2.5-VL-7B on Kaggle); low-tens-of-$ if you use a frontier VLM API for higher-quality labels.
- **SFT (QLoRA 7–14B, ~few k examples, 1–3 epochs):** a few hours → **$0 on Kaggle**, or ~**$1–3** on
  a rented 4090/A100.
- **DPO/ORPO:** same order → **$0–5**.
- **GRPO/RLVR (the expensive one):** rollouts + the student-simulation pass dominate. Doable but slow
  on free tier; for a serious run rent an A100/H100 for ~1–2 days → **~$25–100**.
- **Distillation flywheel:** mostly cheap student SFT; main line item is optional teacher-API calls.

**Two concrete budgets**

- **$0 plan:** Kaggle-first rotation for SFT + DPO + small-batch GRPO; local VLM for extraction; accept
  slowness and checkpoint religiously. Entirely feasible for a working v1.
- **~$100 plan:** free tier for extraction/SFT/DPO; rent an A100/H100 spot for ~1–2 days for the RL
  stage; ~$10–30 of frontier-API for high-quality extraction labels and a teacher for distillation.

---

## 10. Serving the real-time agent (the part free tiers can't do)

⚠️ Free notebooks are for **training**, not **serving**. Their ToS forbids production real-time
inference, and they can't give you a persistent low-latency endpoint for the LiveKit loop. Options:

- **Self-host** the merged model with **vLLM** on a cheap rented GPU (4090/A100 spot). Best
  cost-control + lowest latency once stable.
- **Serverless inference APIs** (Together, Fireworks, Groq, DeepInfra, OpenRouter) — host your
  fine-tuned-or-base model; pay per token; fastest to stand up.

**The live loop (per beat, streamed):**

1. Planner produces a short storyboard + move sequence (can be the same model, a thinking pass, or a
   stronger model for hard topics).
2. Policy **streams DSL beats** one at a time.
3. Each beat's `narration` → TTS that returns **word/character timestamps** (e.g. ElevenLabs char
   timestamps, Azure word boundaries) — or force-align with WhisperX.
4. A **scheduler** fires each directive when TTS reaches its `[[cue:cN]]` word; the web renderer paints
   to SVG/Canvas/D3/KaTeX.
5. **Neo4j** supplies grounded facts so correctness comes from the graph, not from imitation.

Latency is tractable precisely because you ship **short JSON + audio**, never render video.

---

## 11. Build order (milestones)

1. **DSL v0 + renderer** for one domain (say single-variable calculus): ~15 primitives + a headless
   validator/dry-run. _Nothing else works without this._
2. **Data pipeline** on 5–10 of your own videos (source path if possible). Hand-correct the DSL +
   move labels. Eyeball quality.
3. **SFT** (QLoRA, Kaggle). Can it produce valid, sensible beats for held-out concepts? Render them.
4. **DPO/ORPO** on a few hundred good/bad pairs. Measure: fewer Mayer violations, better cue timing.
5. **Quiz proxy harness** + `render_validity` + `pedagogy` rewards. Then **GRPO**; add quiz-proxy once
   render-rate >95%.
6. **Distillation flywheel**: rejection-sample winners, re-SFT, repeat.
7. **Serve** with vLLM, wire into LiveKit + TTS-timestamp scheduler + Neo4j. Close the loop.
8. **Evaluate** on _unseen_ topics with real/simulated students — this is the only test that matters
   for "extraordinary teaching."

---

## 12. References

- Prasad & Mahapatra (2026), _Speech-Synchronized Whiteboard Generation via VLM-Driven Structured Drawing Representations_ — arXiv 2603.25870
- Ku et al. (2025), _TheoremExplainAgent_ — arXiv 2502.19400 (ACL 2025)
- Belouadi et al. (2023), _AutomaTikZ_ — arXiv 2310.00367
- Belouadi et al. (2024), _DeTikZify_ — arXiv 2405.15306
- Holmberg (2025), _AutoLectures (Narrated Lecture Videos from Slides)_ — arXiv 2505.02966
- Shen et al. (VIS 2023), _Data Player_; Wang et al., _WonderFlow_ (narration–animation interplay)
- Mayer, _Cambridge Handbook of Multimedia Learning_; Sweller, Cognitive Load Theory
- Tools: Manim (`3b1b/manim`, MIT) & `3b1b/videos` (CC BY-NC-SA) & `3b1b/captions`; Motion Canvas;
  Excalidraw; D3 / function-plot / JSXGraph; KaTeX; Three.js; Penrose
- Training: Unsloth (LoRA/QLoRA/DPO/GRPO/GSPO, vision FT); TRL; PEFT; WhisperX; PySceneDetect; MathPix/pix2tex
- Compute: Kaggle (30 h/wk dual-T4), Colab, Lightning AI; Vast.ai / RunPod / Lambda / Modal for rentals
