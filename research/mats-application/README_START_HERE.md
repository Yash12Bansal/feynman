# MATS Application Starter Kit — "Do You Know This Entity?"
### Probing the LLM's dynamic model of what the user knows

This folder is a complete, ordered path from zero to a submitted application.
Work through it top to bottom. Every step says WHY it exists.

**The project in one sentence:** LLMs build internal models of their users
(Chen et al. showed demographics). We test whether they build *dynamic* models
of what the user KNOWS — whether that internal estimate updates rationally on
in-conversation evidence, whether it causally drives behavior, and whether the
model's *stated* assessment diverges from its *internal* one when the user is
confidently wrong (the sycophancy/honesty gap).

**Deadline:** confirm on matsprogram.org/apply — announced as Sep 4, 2026 11:59pm PT.
**Time budget (Nanda's rules):** 20 hours of project work + 2 extra hours for the
executive summary. General learning & generic tech setup BEFORE choosing the
project do NOT count. Track time with Toggl and screenshot it.

---

## PHASE A — Setup (pre-clock, doesn't count toward 20h)

### A1. Accounts (~30 min)
- [ ] runpod.io account + billing (GPU rental). Purpose: real GPU for a 9–27B model;
      Nanda's doc now recommends AGAINST Colab.
- [ ] openrouter.ai account + API key. Purpose: one API for the dialogue-generator
      and judge models (which must be a DIFFERENT model family than the subject model).
- [ ] Claude Code with the best plan you can afford for the period — Nanda: rate
      limits matter for agentic research; agentic-tool users were accepted at ~3x rate.
- [ ] MATS application form — open it NOW, read the questions, note the
      "1–3 pieces of evidence you can do research" question (this is where Feynman goes).

### A2. GPU pod (~45 min, lean on your LLM for tech support)
- [ ] Rent 1x A100 80GB (or H100). 80GB covers 27B-class inference in bf16
      (9B ≈ 18GB weights, 27B ≈ 54GB). Cost ≈ $1.5–2.5/hr; expect $40–80 total.
- [ ] Template: any PyTorch 2.x CUDA image. Add persistent volume ≥ 100GB
      (model weights + activation caches survive pod restarts).
- [ ] `pip install torch transformers accelerate scikit-learn matplotlib pandas requests tqdm`
- [ ] Clone this folder onto the pod. Set env vars: `OPENROUTER_API_KEY`.
- [ ] Start JupyterLab on the pod; connect Claude Code to it via jupyter-mcp-server
      (Nanda's doc: "give the agent a live Jupyter kernel via MCP" — models load once,
      state persists between agent calls). Fallback: `ipython` inside `tmux`, agent
      talks to it with tmux send-keys / capture-pane.
- [ ] Copy `CLAUDE.md` from this folder to the repo root the agent works in.

### A3. Minimum concepts (2–3 evenings; you only need FIVE things)
Learn each because a specific step depends on it:
1. **Residual stream** — each layer reads/writes a running vector per token;
   it's the model's working memory. It is WHAT WE PROBE. (Nanda's "what is a
   transformer" video; 3Blue1Brown transformer videos.)
2. **Linear representation hypothesis** — concepts tend to be directions in that
   vector space. WHY a linear probe / steering vector is the right first tool.
3. **What a probe is** — the model is FROZEN; we fit logistic regression on stored
   activations. We measure the model, we don't train it.
4. **Chat templates & token positions** — conversations are serialized with role/
   turn tokens; info about the user must be aggregated by the time the model
   replies → we extract at end-of-user-turn positions.
5. **output_hidden_states / hooks** — how activations come out (scripts show it).
Do ARENA chapter 1.2, first 3 sections only (Nanda's exact advice for the
time-constrained). Timebox ruthlessly.

### A4. Skim these before starting the clock (they define your delta)
- Chen, Viégas & Wattenberg — user-model probes (age/gender/education/SES) + steering.
- LessWrong: "Do LLMs Change Their Minds About Their Users… and Know It?" (demographics
  dynamics + introspection gap — your project starts where this stops).
- Eliciting Secret Knowledge (Cywiński et al.) — the User-Gender organism section.
- Nanda's MATS doc sections: "How are applications evaluated", "Sanity-check your
  agent", "Suggested Research Problems → User models".
YOUR DELTA, memorize it: prior work = WHO the user is (static demographics).
You = WHAT the model thinks you KNOW, how that belief UPDATES on evidence, and
whether the model is HONEST about it.

### A5. Rehearsal (half a day; Nanda explicitly recommends this)
- [ ] With your agent + kernel, load the subject model, generate text, pull
      hidden states, fit one throwaway probe on anything (e.g., sentiment).
      Purpose: your 20 clocked hours must not be your first 20 hours of
      agentic research. Debug the plumbing for free, now.

### A6. Pick the subject model
Default: newest **Qwen dense ~9B instruct** (Nanda's doc names Qwen 3.5/3.6
dense 4B/9B/27B as good defaults). Set it in `config.py` (`MODEL_ID`). Escalate
to 27B only if 9B signals are weak — escalation is evidence, not failure.
Do NOT use small/old models (his doc mocks "theory of mind in GPT-2").

---

## PHASE B — The clocked 20 hours

Start Toggl. Fill the prediction table in `logbook.md` BEFORE any experiment (Hour 0–1).

| Hours | Step | Script | Gate |
|---|---|---|---|
| 0–1 | Pre-register hypotheses + predictions | `logbook.md` | table complete |
| 1–4 | Generate datasets + QC | `01_generate_dialogues.py`, `02_qc_dialogues.py` | judge agreement 85–95%; YOU read 30 dialogues |
| 4–6 | Extract activations + E1 probe | `03_extract_activations.py`, `04_probe_e1.py` | **GO/NO-GO** (below) |
| 6–10 | E2 update dynamics | `05_dynamics_e2.py` | curves + 3 metrics |
| 10–14 | E3 honesty gap | `06_honesty_e3.py` | 2×2 matrices |
| 14–17 | E4 steering + baselines (CUT FIRST if behind) | `07_steering_e4.py` | dose–response + random-vector control |
| 17–20 | Verification pass + main write-up | — | headline numbers recomputed; 30 transcripts read |
| +2 | Executive summary (YOUR voice, ≤600 words/1 page ideal) | — | graphs included |

**Hour-6 GO/NO-GO:** does the E1 probe beat chance on HELD-OUT TOPICS with clean
controls (shuffled labels ≈ chance; topic probe high)?
- Weak → escalate to 27B.
- Absent on 27B → the project PIVOTS to a controlled negative: "modern chat models
  do not linearly represent user competence (though they represent topic and
  demographics)" — spend remaining hours characterizing why (does black-box asking
  do better? then it's represented non-linearly/elsewhere). Nanda: "negative or
  inconclusive results that are well-analysed are much better than a poorly
  supported positive result." A full restart also legally resets the 20h clock.

**Every experiment:** write the prediction in `logbook.md` first, run, record outcome.
**Every agent result:** treat "it worked" as a hypothesis. Read the raw data. Recompute
one headline number yourself. Document what you verified (this is scored).

---

## PHASE C — Write-up rules (from Nanda's doc, non-negotiable)
- Google Doc, link-shareable ("anyone with link"). Exec summary first: ~1 page ideal,
  hard max 3 pages / 600 words, WITH graphs. Sections: What problem & why → high-level
  takeaways → one paragraph + one graph per key experiment.
- Immediately after the exec summary: 5 RANDOMLY SELECTED (not cherry-picked)
  qualitative examples of your generated dialogues + judged responses.
- Claims-first structure, never chronological. Name the models, the key experiment,
  the surprising number. State limitations before he finds them.
- NEVER submit raw LLM prose for the form answers or exec summary — he calls
  LLM-sounding text "a significant negative signal". Use LLMs for code, graphs,
  drafting, and criticism (anti-sycophancy prompt), then write it yourself.
- Application form summary questions are read FIRST and used as a filter — spend
  real time on them.
- Include the prediction-vs-outcome table and the Toggl screenshot in an appendix.

## FRAMING RULE (repeat until internalized)
This is a SAFETY / model-biology project: user models → sycophancy → manipulation.
Never frame it as an AI-tutor or education project (his doc's "pet interest" warning).
Feynman appears ONLY in the form's "evidence you can do research" answer, as
engineering/agency evidence.

## File map
| File | What it does |
|---|---|
| `config.py` | model ids, topics, levels, paths — edit this first |
| `01_generate_dialogues.py` | all 5 datasets via OpenRouter |
| `02_qc_dialogues.py` | human-read sampler + blind LLM judge agreement |
| `03_extract_activations.py` | per-turn residual-stream caching (all layers) |
| `04_probe_e1.py` | layer sweep, topic-held-out eval, controls, figures |
| `05_dynamics_e2.py` | frozen-probe update curves, asymmetry, anchoring |
| `06_honesty_e3.py` | truth probe + behavior judge + 2×2 matrices |
| `07_steering_e4.py` | diff-of-means steering, random-vector control, baselines |
| `judge_rubrics.md` | every LLM-judge prompt, with rationale |
| `logbook.md` | prediction table + daily log + verification checklist |
| `CLAUDE.md` | instructions for your research agent on the pod |
