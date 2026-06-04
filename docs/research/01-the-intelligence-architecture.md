# The Intelligence Architecture of Feynman

> *A research-to-engineering map for building a tutor that teaches like Feynman, models a student like a cognitive scientist, and earns attention like TikTok — without becoming TikTok.*

**Status:** Living research doc. Written 2026-06-03.
**Audience:** Us (founders). This is the "study from basics to hardcore engineering" map.
**One-line thesis:** The product is not an LLM with a good prompt. It is a **persistent model of a learner** + a **teaching policy conditioned on that model** + a **closed data loop that makes both compound over time**. The LLM is the actor. The model of the student is the brain. The data is the moat.

---

## Part 0 — Reframing the Question (read this first; everything follows from it)

The brief had four desires baked in: teach (like Feynman), adapt to pace, understand strengths/weaknesses, and out-compete Instagram/TikTok for the student's attention. These are **three distinct intelligences** that people constantly conflate. Keeping them separate is the single most clarifying move we can make.


| Intelligence                    | The question it answers                                                                                  | What it is, concretely                                                                                    | Where it lives today                                         |
| ------------------------------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| **Pedagogical** (the *policy*)  | *How* should I teach this, right now, to this kid?                                                       | Explanation strategy, Socratic questioning, worked examples, analogy selection, when to branch on a doubt | Mostly the LLM + curriculum + prompt                         |
| **Student model** (the *state*) | *Who* am I teaching — what do they know, where are the gaps, how fast, what misconceptions, what affect? | Knowledge tracing, mastery estimates, misconception catalog, pace, affect/flow state                      | **Does not exist yet in any durable form.** This is the gap. |
| **Engagement** (the *loop*)     | *Why* do they come back tomorrow at 8 PM instead of opening Instagram?                                   | Flow management, curiosity hooks, relatedness/persona, healthy habit formation                            | Implicit in the experience; not engineered                   |


The LLM gives us the *pedagogical* intelligence nearly for free (Part V). The reason this is a hard, defensible, multi-year product and not a weekend prompt is the other two. **The student model is the compounding IP. The engagement loop is the retention engine.** A competitor can copy our prompt in an afternoon; they cannot copy six months of a particular kid's learning trace and the model trained on millions of them.

### The TikTok reframe — steal the machine, not the objective

This is worth being precise about because it's where most people's intuition goes wrong.

TikTok is *spectacularly* good at one thing: building a real-time model of what will keep *you specifically* watching, and serving it within milliseconds. Its objective function is **engagement (watch-time, completion, re-watch, interaction)**. That objective is *valid for TikTok* — time-on-app *is* their goal.

If we copy that **objective**, we build a worse TikTok with a textbook skin. A kid who spends 3 hours mesmerized but confused is a catastrophe, not a win. So:

- **What we steal — the machinery.** Real-time per-user modeling, the two-stage retrieval architecture (candidate generation → ranking), embedding-based representation of users and content, online/streaming training so the model updates within a session, multi-armed bandits for exploration, and above all the **data flywheel** (every interaction improves the model that produces the next interaction). All of Part III.
- **What we reject — the objective.** We do **not** optimize time-on-app. We optimize **long-term learning** + **healthy intrinsic motivation**.

And here is the **unfair advantage that makes this whole thing work**:

> For TikTok, engagement and user well-being are in *tension* (more scrolling ≠ better life). For us, **engagement and learning are *aligned*** — because the psychological state that produces the deepest engagement, **flow**, is the *same* state that produces the most learning: the **challenge-skill balance** (Csikszentmihalyi) is operationally identical to teaching in the **Zone of Proximal Development** (Vygotsky). When we tune for the right kind of engagement, we are *automatically* tuning for learning. TikTok can never say that. **This alignment is our ethical moat and our product moat at once.** (Part IV makes this rigorous.)

### The LLM is the actor, not the brain

A tempting wrong turn: "GPT/Claude is smart, so a great prompt is the product." No. LLMs are:

- **Amnesiac** across sessions — no memory of *this* kid unless we build it.
- **Sycophantic** — they will tell a student they're right, give away answers, and inflate praise (the opposite of a good teacher) unless explicitly constrained. (The Kestin study's tutor had to be *forced* to reveal one step at a time.)
- **Stateless about mastery** — they have no calibrated belief about what the student knows; they pattern-match the conversation in the window.

So the LLM is a phenomenally capable **policy executor**. The durable intelligence is the **student model it is conditioned on** and the **teaching policy that decides what to do**. Build the brain; rent the actor.

---

## Part I — The Learning Science Foundation (what "good teaching" provably is)

You cannot build an intelligent teacher without a precise, evidence-based definition of teaching quality. This is the substrate the whole system optimizes toward. Decades of cognitive science have *already* told us what works; most edtech ignores it. We won't.

### The north star: Bloom's 2 Sigma

Bloom (1984) found that students tutored 1:1 with **mastery learning** performed **~2 standard deviations** above classroom students — i.e., the average tutored student beat ~98% of the classroom. That gap, at scale, is literally the business. **Caveat we must internalize:** later work (VanLehn 2011) couldn't replicate the full 2σ, and concluded much of Bloom's effect came from holding tutored students to a *higher mastery standard*. The honest read: **the magic isn't mystical "tutoring," it's (a) tight feedback loops and (b) refusing to let the student move on before mastery.** Both are things software can do *better* than a human (infinite patience, perfect memory of the gap).

### The efficacy ladder (VanLehn 2011, the number to remember)

Effect size over conventional classroom:

- **No tutoring:** 0
- **Answer-based ITS** (right/wrong only): **~0.31σ**
- **Step-based ITS** (feedback on each step of reasoning): **~0.76σ**
- **Human tutors:** **~0.79σ**

The lesson is sharp: **step-level feedback gets you ~96% of the way to a human tutor.** The intelligence is in reasoning *with* the student step by step, not in grading the final answer. Our agent must operate at the step loop, not the answer loop.

### VanLehn's two loops (the architecture of any tutor)

- **Outer loop:** *what task next?* (which problem, which concept). This is a sequencing/recommendation/RL problem → Part III.
- **Inner loop:** *what to do within a task?* (hints, feedback, sub-questions, when to branch). This is the dialogue/pedagogy problem → the LLM + policy.

Feynman's "doubt branches" are inner-loop excursions; the "main branch checkpoints" are the outer loop. Our existing tree/graph session model maps cleanly onto this — good.

### The pedagogical principles that must be *mechanized* (not just hoped for)

These are not vibes; each has decades of evidence and an effect size. The system should treat them as **constraints and levers**, encoded in the teaching policy.

1. **Mastery learning** — don't advance until the prerequisite is solid. Requires a mastery estimate (Part II).
2. **ZPD + scaffolding** (Vygotsky) — teach just beyond current ability, with support that fades. Requires knowing current ability. *This is the same as flow's challenge-skill balance — Part IV.*
3. **Cognitive Load Theory** (Sweller) — working memory is tiny (~4 chunks). Minimize **extraneous** load (bad UI, irrelevant detail), manage **intrinsic** load (sequence from simple to complex), maximize **germane** load (effort that builds schemas). *This is why the visual board matters — offloading to the visual channel frees working memory (dual-coding).*
4. **Retrieval practice / the testing effect** (Roediger & Karpicke) — recalling beats re-reading, by a lot, for retention. → the system must make the kid *produce*, not just nod. (Our "kid solves it" magic beat is this principle.)
5. **Spacing effect** (Ebbinghaus → modern) — distributed practice >> massed. Implies the system schedules *return visits* to concepts over days/weeks. → Part II spaced-repetition modeling.
6. **Desirable difficulties** (Bjork) — spacing, interleaving, retrieval, generation, and variation all *feel harder and slower in the moment* but produce far better long-term retention and transfer. **Profound product consequence:** the experience that *feels* most fluent and easy is often the one that teaches *least*. We must resist the temptation to make it feel effortless. We engineer *productive struggle*, not frictionlessness. (This directly tensions with naive "engagement.")
7. **Interleaving** — mixing problem types beats blocking, for discrimination and transfer.
8. **Worked examples + the expertise-reversal effect** (Sweller) — novices learn more from studying worked examples than solving; *experts* learn more from solving. So the example/practice ratio must **adapt to mastery** — another reason the student model is load-bearing.
9. **Self-explanation effect** (Chi) — students who explain *why* a step works learn more. The Feynman technique itself ("explain it simply") *is* the self-explanation effect operationalized — get the kid to teach it back.
10. **Productive confusion** (D'Mello & Graesser) — confusion, when *resolved*, is the single affective state that *predicts learning gains*. We should not eliminate confusion; we should *induce it deliberately and then resolve it* (the "question → payoff" rhythm already in our pipeline). Unresolved confusion → frustration → boredom is the failure cascade to detect and interrupt (Part II).

**Design consequence:** half of these (mastery, ZPD, worked-example ratio, spacing) are *impossible to do well without a student model*. The learning science *forces* us to build Part II. That's the proof the student model isn't optional polish — it's the spine.

---

## Part II — Modeling the Student (the "understands strengths & weaknesses" brain)

This is the heart of the defensible product. It has three layers: **what they know** (knowledge tracing), **how they feel** (affect), and **who they are over time** (pace, misconceptions, learning patterns). I'll go basics → hardcore for each, then give the honest engineering verdict.

### Layer 1 — Knowledge tracing: estimating mastery from a stream of interactions

The core problem: given a student's history of correct/incorrect responses on items tagged with skills (KCs — knowledge components), estimate **P(they know skill k)** and **P(they get the next item right)**.

**The lineage, basics → hardcore:**

1. **Item Response Theory (IRT)** — the psychometric foundation (the math behind every standardized test). Models P(correct) as a logistic function of *student ability θ* minus *item difficulty b*: `P(correct) = σ(θ − b)` (1PL/Rasch); 2PL adds a discrimination slope; 3PL adds a guessing floor. Strengths: principled, calibrated, interpretable, decades of validation. Weakness: assumes ability is *static* — no learning over time. Still the right tool for *placement* and *item calibration*.
2. **Bayesian Knowledge Tracing (BKT)** — Corbett & Anderson (1995). The classic. A 2-state Hidden Markov Model per skill: the hidden state is *known / not-known*, with four parameters — **p(L₀)** prior known, **p(T)** transition (learning) probability, **p(slip)** (knows it but errs), **p(guess)** (doesn't but lucky). After each response you Bayes-update P(known). Strengths: interpretable, cheap, you can literally *say* "she's at 0.82 on the chain rule." Weaknesses: one skill at a time (no transfer between related skills), binary state, fixed difficulty.
3. **Performance Factors Analysis (PFA) / AFM** — logistic models where P(correct) depends on counts of prior successes/failures per skill. More flexible than BKT for multi-skill items.
4. **Knowledge Space Theory (KST)** — Doignon & Falmagne; the engine behind **ALEKS**. Instead of independent skills, model the *partial order* of knowledge states (you can't know X before prerequisite Y). The "knowledge space" is the set of feasible states; assessment navigates it efficiently. Conceptually beautiful and a great match for a **prerequisite graph** — which we already have in embryonic form in the curriculum graph.
5. **Deep Knowledge Tracing (DKT)** — Piech et al. (2015, NeurIPS). An RNN/LSTM consumes the interaction sequence and predicts next-item correctness. Captures inter-skill dependencies and temporal patterns automatically; big AUC jump on benchmarks. Weaknesses: opaque (a black-box hidden state, not a per-skill mastery you can show a parent), can violate sanity (predict mastery goes *down* after a correct answer), data-hungry.
6. **Memory-augmented & attentive KT (the modern SOTA):**
  - **DKVMN** (2017) — Dynamic Key-Value Memory Networks; an explicit memory slot per concept, more interpretable than vanilla DKT.
  - **SAKT** (2019) — first self-attention (Transformer) KT; handles sparse data by attending to *relevant* past items.
  - **AKT** (2020) — Context-aware Attentive KT; couples attention with *psychometric* structure (Rasch-style difficulty embeddings + a monotonic attention decay modeling forgetting). One of the best-balanced models — deep power *with* measurement theory.
  - **SAINT / SAINT+** (2020, Riiid) — full Transformer encoder-decoder (exercises → encoder, responses → decoder); SOTA on the large EdNet benchmark; SAINT+ adds response time and lag time as features (a hint at the implicit-signal goldmine — Part VII).

**The honest engineering verdict (do not cargo-cult deep KT):**

- On raw next-item AUC, attentive Transformers (AKT/SAINT) win on big benchmarks. **But**: (a) the deep-vs-BKT gap is *much smaller* than papers imply once BKT is given fair extensions (BKT+, individualization) — there's a well-known reproducibility critique; (b) deep models need a *lot* of data we won't have at cold start; (c) **a teacher must be able to explain its belief** — "you're shaky on factoring, solid on substitution" — and a black-box hidden vector can't do that; (d) interpretable Bayesian/IRT variants remain SOTA for **calibration and fairness**, which matter enormously when a *parent* is paying and trusting us.
- **Therefore: a hybrid, and start interpretable.** An **IRT/BKT-style backbone** gives the explainable, per-skill mastery state that drives mastery decisions, the parent dashboard, and the teaching policy. Layer a **deep sequence model on top later** (once we have data) for next-step *prediction* and for catching cross-skill structure the backbone misses. The mastery state the *teacher reasons about* stays interpretable; the *predictor* can be deep. This is also the [[curriculum-graph-pipeline]] payoff — items tagged to a real KC graph make every one of these models work better.

### Layer 2 — Affect: modeling how the student *feels* (the engagement-detection brain)

This is where we go beyond any textbook tutor and toward the "make them comfortable / sense confusion" brief. D'Mello & Graesser's **affect dynamics** model is the canonical map:

> **Engagement/Flow** → hit an impasse → **Confusion** (cognitive disequilibrium) → *if resolved* → back to Flow (and **learning happens here**); *if unresolved* → **Frustration** → *if persistent* → **Boredom** → disengagement.

The empirically load-bearing facts:

- **Confusion is the only state that reliably predicts learning gains** — *when it gets resolved*. So our job is not a frictionless dopamine drip; it's **induce confusion, then guarantee resolution.** This is the opposite of TikTok.
- The dangerous transition is **confusion → frustration → boredom**. Detecting the slide early and intervening (re-scaffold, switch analogy, drop difficulty, inject a win) is a core real-time loop.

**How to sense affect (our signal advantage):** Tutoring-systems research senses affect from conversational/discourse cues, response timing, facial features, and body posture. **We have a richer stream than almost any prior system** because we're real-time voice + a visual board:

- **Voice prosody** — hesitation, pitch rises (uncertainty), latency-to-answer, filled pauses ("um"), trailing off. This is a near-direct readout of confidence/confusion.
- **Response latency** — long pause before answering = struggle or disengagement; instant correct = possibly too easy (under-challenged, flow-bored).
- **Lexical/dialogue cues** — "wait, what?", "I don't get it", re-asking, going quiet.
- **Interaction with the board** — do they engage when asked to, or stall?

Building a real-time **affect classifier** over these signals (start with simple rules + thresholds, graduate to a learned model) that outputs a flow/confusion/frustration/boredom estimate is one of the highest-leverage and most *novel* things we can build. It directly feeds the engagement loop (Part IV) and the inner-loop policy.

### Layer 3 — The longitudinal learner profile (pace, misconceptions, patterns)

Beyond moment-to-moment, the model accumulates *who this kid is*:

- **Pace** — how many exposures until mastery, per concept type. (Adapt outer-loop speed.)
- **Misconception catalog** — *specific wrong models*, not just "got it wrong." (E.g., "treats negative signs as optional under a square root.") Misconception-aware feedback is dramatically more effective than generic hints. This requires tagging errors to a **bug library** per topic — a real data asset to build.
- **Learning patterns** — responds to visual vs verbal? (⚠️ **myth alert:** the "learning styles" theory — matching teaching to a preferred modality — is **not supported by evidence**. Do *not* build "she's a visual learner" personalization; it's pseudoscience. What *is* real: some *content* is inherently better taught visually, and **dual-coding** (verbal + visual together) helps *everyone*. Personalize on *mastery, pace, misconceptions, and affect* — not on a learning-style label.)
- **Prerequisite gaps** — when a kid fails concept C, is it really a gap in prerequisite B? The curriculum graph + KST lets us *diagnose upstream*, which is the Feynman move: "revisit fundamentals."

**This whole part maps onto the repo's three-graph architecture:** the **curriculum graph** (shared spine, the KC/prerequisite structure), the **per-student knowledge graph** (Layers 1 & 3 above), and the **ephemeral session/board state** (Layer 2 lives partly here). The student model is the per-student graph, made *quantitative* with the tracing math above.

---

## Part III — What TikTok Actually Does (recommendation systems, honestly mapped)

Now the "understand the user like TikTok/Instagram" pillar — what's really under the hood, and exactly what transfers vs. what is a trap.

### The canonical architecture: two-stage retrieval (this is the pattern to learn cold)

Industrial recommenders (YouTube — Covington et al. 2016 — is the cleanest published example) almost universally use **two stages** because you can't rank millions of items in real time:

1. **Candidate generation (retrieval):** from a corpus of millions, cheaply select **hundreds** plausibly-relevant items. Done with **embeddings** — learn a vector for each user (from history) and each item; retrieval = approximate nearest-neighbor in that space. Optimized for *recall*, not precision.
2. **Ranking:** score those hundreds *precisely* with a heavier model using many features (item × user interactions, context, freshness), output a ranked list. Optimized for *precision*.

YouTube's models had ~1B parameters trained on ~hundreds of billions of examples. The *architecture*, though, is simple and copyable.

### The representation: embeddings and how users get "understood"

- **Matrix Factorization** (Koren et al., the Netflix-Prize era) — the foundational idea: represent each user and item as a vector; predicted affinity = dot product. Learns latent "taste" dimensions automatically.
- **Deep recommenders** — **Wide & Deep** (Google 2016, memorization + generalization), **DeepFM**, **DLRM** (Meta's open-source deep learning recommendation model) — neural nets over sparse categorical features + dense features.
- **Two-tower models** — a user tower and an item tower producing embeddings in a shared space; the standard for retrieval at scale.
- **Sequential / session-based models** — the key to "what should come *next*": **GRU4Rec** (RNN over the session), **SASRec** (self-attention), **BERT4Rec** (masked-LM-style). **Notice:** these are *the same family of models as Deep Knowledge Tracing.* Predicting "next video you'll like" and "next problem you're ready for" are *structurally the same problem* — a sequence model over user history. That's the deep connection between RecSys and student modeling, and it's why our team should learn both as one body of math.

### Real-time: the TikTok/Monolith twist

TikTok's edge (ByteDance's **Monolith**, arXiv:2209.07663) is **real-time online training**:

- **Collisionless embedding tables** (Cuckoo hashing) — most systems hash sparse IDs into fixed tables and tolerate collisions; Monolith avoids them so each user/video gets a clean embedding. With **expirable embeddings** + **frequency filtering** to bound memory.
- **Online training** — the model updates from your likes/watches **within seconds**, not in a nightly batch. Training and serving aren't separate stages; feedback flows back continuously. This is *why* TikTok "reads your mind" after a handful of videos — the model is literally fitting to you in real time.

**The transferable insight for us:** within a single 30-minute lesson, the system should be *updating its model of the student continuously* and adapting — not running a fixed pre-baked script. Our pre-compute pipeline gives us *prepared material* (low latency); the real-time layer must *select and adapt* it online from the live student model. Pre-compute for speed, online-adapt for fit.

### Exploration: bandits and RL (how it discovers what you like)

A recommender that only exploits what it already knows never *learns* your tastes. The exploration/exploitation tradeoff is handled with:

- **Multi-armed bandits** — **ε-greedy**, **UCB**, **Thompson sampling**. **Contextual bandits** condition the choice on features (the student's state). This is the *right-sized* tool for outer-loop sequencing: "which next activity, given uncertainty about what helps *this* kid?"
- **Full RL** (Q-learning, PPO, slate RL) — when actions have *long-horizon* consequences (today's choice affects next-week's mastery). More powerful, far harder (next section).

### The precise mapping to Feynman — and the precise divergence


| TikTok                                | Feynman                                                                                  |
| ------------------------------------- | ---------------------------------------------------------------------------------------- |
| Corpus = videos                       | Corpus = concepts, problems, explanations, analogies, **pre-generated diagrams**         |
| User embedding from watch history     | Student embedding from **knowledge trace + affect**                                      |
| Candidate generation → ranking        | "What concept/problem/representation next?" → outer-loop sequencing                      |
| Reward = watch-time, completion, like | Reward = **learning gain + flow + mastery** (Part VIII — and this is *hard*)             |
| Online training within session        | Online student-model update within lesson                                                |
| Bandits explore new content           | Bandits explore which *explanation/analogy/difficulty* works for this kid                |
| **Objective: maximize engagement**    | **Objective: maximize learning; engagement is a *constraint & a means*, never the goal** |


**The trap, stated plainly:** every signal TikTok optimizes (more time, more taps, more emotional spikes) is, copied naively, *actively harmful* in education. The whole skill is keeping the *machine* and swapping the *objective* — and the objective swap is not a config change, it's the hardest research problem in the system (next part of Part VIII). But the flow-alignment insight from Part 0 is what makes it *tractable*: optimizing for *flow-state engagement* is, uniquely for us, almost the same as optimizing for learning.

---

## Part IV — The Motivation Engine (beating Instagram, ethically and durably)

The brief's hardest ask: make a kid *choose* studying over TikTok. This is a **motivation-design** problem, and the science is clear and underused.

### Why TikTok wins the dopamine war (and why we shouldn't enter it)

TikTok exploits **variable-ratio reinforcement** (Skinner) — unpredictable rewards on each swipe — which is the most powerful schedule for compulsive behavior, plus near-zero effort and infinite supply. This produces **extrinsic, compulsive** engagement: you keep scrolling but feel *worse*. We **cannot and should not** out-compete on this axis — a slot machine will always out-slot-machine a teacher. If we try, we lose *and* we corrupt the product.

### The alternative engine: intrinsic motivation (Self-Determination Theory)

Deci & Ryan's **SDT** is the most validated theory of durable motivation. Intrinsic motivation — doing something because it's inherently satisfying — is fueled by three needs:

1. **Competence** — the feeling of *getting better*, meeting an optimal challenge. **This is the big one for us.** It is *manufactured by good teaching*: visible progress, mastery, "I just solved something I couldn't 10 minutes ago." Our product's core loop *is* a competence-generating machine — if the student model keeps difficulty in the ZPD.
2. **Autonomy** — acting from one's own volition. Give the kid *real choices* (what to explore next, "show me why", set their own goal), not a rail. Coercive "do this now" kills intrinsic motivation.
3. **Relatedness** — a caring, supportive relationship. **This is the Feynman persona.** A warm, patient teacher who *remembers you*, knows you struggled with this yesterday, celebrates your win, never judges. The voice modality + a persistent memory of the student makes relatedness *real* in a way a worksheet app never can. This is a massive, underrated moat.

**The strategic point:** SDT-driven (intrinsic) motivation produces *better learning, more persistence, more creativity, and healthier kids* than reward-driven (extrinsic) motivation. We're not choosing the "ethical but weaker" option — **intrinsic motivation is also the more durable retention engine** for a product used over months. Single sessions are noise; a kid choosing us 4×/week for 6 months is the business — and that only comes from competence + relatedness, not points.

### Flow — the master variable that unifies engagement and learning

Csikszentmihalyi's **flow**: total absorption, occurs when **challenge matches skill**. Too hard → anxiety; too easy → boredom; matched → flow. Recall from Part II that **this is operationally identical to D'Mello's engaged/flow state and to teaching in the ZPD.** So:

> **The single most important real-time control variable in the entire product is the challenge-skill balance.** Keep the student in flow and you simultaneously (a) maximize engagement, (b) maximize learning, (c) satisfy competence, and (d) avoid the boredom→churn and anxiety→churn failure modes. The student model (Part II) exists *precisely* to estimate skill so the policy can tune challenge to hold flow.

This is the technical heart of "engaging *and* effective." It's one knob, and we have the instrumentation (affect + mastery) to turn it in real time.

### Curiosity — the hook that doesn't rot

Loewenstein's **information-gap theory**: curiosity is the felt deprivation when you become aware of a gap between what you know and want to know. Berlyne's work on novelty/surprise/complexity as arousal drivers backs this. **Product moves:** open concepts with a *question* or a *surprising phenomenon*, not a definition (our pipeline's "hook → question → payoff" already encodes this). The "press-twice / reveal" mechanism is a *variable reward used for good* — the dopamine of *insight*, not the dopamine of a slot machine.

### The ethical landmine: gamification and the overjustification effect

The naive move — points, badges, streaks, leaderboards — is **dangerous**. The **overjustification effect** (Deci; Lepper) is robust: paying people (or kids) *extrinsic* rewards for something they'd do intrinsically can *destroy* the intrinsic motivation. Streaks can become anxiety; badges can make learning feel like a chore-for-points. Duolingo's streak works as a *habit trigger* but is widely criticized for optimizing engagement over learning — the exact trap. **Our stance:** rewards should *reflect genuine competence* (you unlocked this because you actually can do it), be *informational* not *controlling*, and never substitute for the intrinsic reward of understanding. When in doubt, make **mastery itself** the reward.

### The habit layer (used carefully)

Nir Eyal's **Hooked** model (trigger → action → variable reward → investment) describes how habits form. We use it *descriptively* to design a healthy return loop — an 8 PM trigger ("your physics is waiting"), a low-friction start, the variable reward of *insight/progress*, and *investment* (the kid's accumulating knowledge graph, their relationship with the teacher, their goals) that makes the product more valuable the more they use it. **But every element is pointed at competence/relatedness, not compulsion.** The test: *does the kid feel better and more capable after a session, or drained?* TikTok fails that test by design; we must pass it by design.

---

## Part V — The LLM Substrate (what changed in 2023–2026, honestly)

LLMs are why this product is buildable *now*. They give us, near-free, the thing that took ITS researchers decades to hand-author per-topic: **natural-language, step-by-step, adaptive Socratic dialogue across any subject.** But they are an *actor*, with specific, dangerous failure modes.

### The efficacy evidence is real and recent (this is not hype)

- **Kestin et al. (2025, *Scientific Reports*)** — Harvard physics RCT, N=194. Students with an AI tutor learned **>2× as much in less time** than an active-learning class, *and* felt **more engaged and motivated**. Crucially, the tutor was prompt-engineered with pedagogy: **give one step at a time, never the full solution, make them try first.** → Pedagogy-in-the-prompt is the difference between a tutor and a cheat-sheet. The "less time" is the headline feature: **efficiency, not time-on-app, is the win.**
- **LearnLM** (Google, 2024, arXiv:2412.16429) — Gemini fine-tuned for "pedagogical instruction following." Expert raters preferred it substantially over GPT-4o (+31%), Claude 3.5 (+11%), base Gemini (+13%). They solved the *data* problem by *manufacturing* tutoring data: human-tutor transcripts, LLM↔LLM synthetic sessions, and teacher-authored "golden conversations." → A blueprint for *our* training-data strategy (Part VII).
- The broader ITS meta-analyses (Part I) say step-based tutoring ≈ human tutoring. LLMs make step-based dialogue *general* instead of hand-built per problem.

### The failure modes we must engineer against

1. **Answer-giving / sycophancy** — the default LLM hands over the answer and praises everything. A *teacher* withholds, questions, and lets the student struggle productively. Requires explicit pedagogical constraints (LearnLM's whole thesis) — and is in tension with the model's RLHF "be helpful" training.
2. **Hallucination** — a confidently wrong physics explanation is worse than none. LearnLM reports **0.1% factual-error rate** *after* heavy tuning — i.e., this is solvable but not free. Grounding in our curriculum graph + pre-verified content is the mitigation.
3. **No persistent student model** — covered; the LLM forgets. We inject the student model into context; we don't expect the LLM to *be* it.
4. **No calibrated uncertainty** — it doesn't know what it doesn't know about the *student*. The Bayesian student model supplies that.

### How the LLM fits the architecture

The LLM is the **inner-loop policy executor**: given (this student's model + current concept + board state + lesson goal), it generates the next utterance, question, hint, or visual instruction. It is *conditioned on* the student model and *constrained by* the pedagogical policy. The **outer loop** (what next) is better served by the cheaper, controllable bandit/sequencing machinery, not the LLM's whims. **Pedagogical alignment** — RLHF/fine-tuning the model toward *teaching* behavior (withhold, scaffold, diagnose) using data like LearnLM's — is a medium-term moat once we have transcripts.

---

## Part VI — System Design & Hardcore Engineering

Now the build. The system is two loops bolted together: a **real-time teaching loop** (milliseconds, in-session) and an **offline learning loop** (the flywheel, across sessions). Mirrors a production recommender exactly.

### Reference architecture

```
                         ┌──────────────────────────────────────────────┐
   REAL-TIME LOOP        │  Student (voice + board interaction)          │
   (in-session, ms)      └───────────────┬──────────────────────────────┘
                                         │ audio, responses, latency, prosody
                                         ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │  PERCEPTION:  STT + prosody/affect features + response-timing          │
   └───────────────┬───────────────────────────────────────────────────────┘
                   ▼
   ┌───────────────────────────┐     ┌──────────────────────────────────────┐
   │  STUDENT MODEL (online)    │◄───►│  CURRICULUM GRAPH (KC + prereqs +     │
   │  knowledge trace + affect  │     │  pre-generated content & diagrams)    │
   │  + flow estimate           │     └──────────────────────────────────────┘
   └───────────────┬───────────┘
                   ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │  TEACHING POLICY                                                        │
   │   • OUTER LOOP: what next? (bandit/RL over curriculum, holds flow)      │
   │   • INNER LOOP: how? (LLM, conditioned on student model + constrained)  │
   └───────────────┬───────────────────────────────────────────────────────┘
                   ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │  REALIZATION:  TTS (voice) + visual instructions (board)               │
   └───────────────────────────────────────────────────────────────────────┘
                   │ every interaction logged as a structured event
                   ▼
   ════════════════════════════════════════════════════════════════════════
   OFFLINE LOOP    │  Event lake → feature store → train: student-model      │
   (the flywheel)  │  params, affect classifier, content embeddings,         │
                   │  sequencing policy, pedagogical fine-tunes               │
                   │  → eval (offline + RCT) → ship → improves real-time loop │
   ════════════════════════════════════════════════════════════════════════
```

### The latency budget (already in our DNA — keep it sacred)

Our standing rule: **<300ms mid-sentence, <800ms at sentence boundary.** That's the difference between "an extension of the teacher's voice" and "a laggy chatbot." Engineering consequences:

- **Pre-compute aggressively** (the existing `data_pre_compute_v2` pipeline) — diagrams, explanations, likely doubts generated *ahead* of time, served from cache. This is our analog of a recommender's pre-built candidate index. Pre-generated DiagramSpecs alone kill the 10–15s generation latency for ~70% of visuals.
- **Two-stage everything** — cheap retrieval from pre-built candidates first; expensive LLM generation only when nothing fits.
- **Streaming** — STT, LLM tokens, TTS all stream; never wait for completion. Progressive board rendering from partial output.
- **Speculative / anticipatory generation** — the lesson plan tells us what's *probably* next; pre-generate during the natural pauses of speech. *Anticipation > reaction* is already a stated principle.
- **Tiered models** — frontier model for the hard teaching turns, cheap/fast models (or pre-compute) for everything else. Already a stated convention.

### The data platform (the flywheel's plumbing)

- **Event streaming** — every interaction → an append-only event log (Kafka-style). This is the raw material of *everything* downstream.
- **Feature store** — consistent features for *online* serving (the live student model) and *offline* training, computed once, no train/serve skew. (Monolith's whole point: don't let these diverge.)
- **Online + offline training** — batch-train the heavy models offline; online-update the per-student state in session (the Monolith lesson).
- **Model serving** — low-latency inference for the student model + affect classifier; the LLM via streaming API.
- **Vector index** — ANN over content/concept embeddings for candidate generation (retrieval of the right explanation/diagram/problem).

### Cold start (the hardest practical problem)

A brand-new kid has no trace; a brand-new concept has no data. Mitigations:

- **Content cold start** — solved by the **curriculum graph + pre-compute**: prerequisite structure and pre-authored content mean we're never starting from zero on the *content* side.
- **Student cold start** — a short, *engaging* diagnostic (KST-style adaptive placement using IRT item difficulties) infers initial mastery fast; **population priors** (the average kid's path) fill the gap until the personal trace accumulates; the affect signals work from minute one.
- **The LearnLM move** — manufacture training data (synthetic + teacher-authored + early-user transcripts) so models aren't starved pre-scale.

### Safety & privacy — non-negotiable, because these are *children*

- **COPPA** (under-13) — verifiable parental consent, data minimization. Our persona Aanya is 13; many users will be younger. This is a legal *and* trust gate.
- **Content guardrails** — no hallucinated-as-fact errors, age-appropriate, no harmful content. Grounding + a safety layer on every LLM output.
- **Transparency** — the parent dashboard isn't a feature, it's a *trust instrument*. Parents are protective and paying; over-invest here (a memory note already flags this).
- **Data governance** — a child's complete learning trace is extraordinarily sensitive. Encryption, retention limits, the right to delete, no creepy data use. Privacy is a *product surface*, not just compliance.

---

## Part VII — Data Strategy (what to collect — the moat material)

If the student model is the brain and data is the moat, then **the event taxonomy we design on day one is the most important schema in the company.** Most of the value is in signals naive products throw away.

### The explicit signals (obvious, necessary, insufficient)

- Item responses: correct/incorrect, the *specific* answer (→ misconception tagging), attempt count.
- Self-reports: "did that make sense?", confidence ratings, goal selection.
- Navigation: what they chose to explore, what they skipped, replays.

### The implicit signals (the goldmine — this is where we beat everyone)

This is the direct analog of TikTok's watch-time/scroll-velocity/rewatch — but for **cognition and affect**, and we have a *richer* stream than any text app because we're **real-time voice + visual board**:

- **Response latency** — time-to-answer is a near-direct readout of difficulty/confidence. (SAINT+ showed even just *response time* meaningfully improves knowledge tracing.)
- **Voice prosody** — pitch, pace, hesitation, filled pauses, trailing off, the *sound* of uncertainty vs. confidence. Almost no tutor has had this. We do.
- **Hesitation & self-correction** — starting an answer, stopping, changing it.
- **Re-asks & "wait, what?"** — explicit confusion markers in the dialogue.
- **Pauses & disengagement** — going quiet, long gaps = the boredom slide.
- **Board interaction** — engagement with prompted tasks; where attention goes.
- **Session-level patterns** — time of day, session length, voluntary return, what they come back to.

**Design imperative:** instrument *all* of this as **structured, timestamped, KC-tagged events from day one**, even before we have models to consume them. You cannot retro-collect a signal you didn't log. Every event tagged to (student, concept/KC, timestamp, modality, signal-type, value). This stream trains the affect classifier, the knowledge tracer, the sequencing policy, and the content embeddings — *everything* downstream eats this.

### The ground-truth problem (the subtle hard part)

Implicit signals are *correlated* with learning, not *equal* to it. We need periodic **ground truth**:

- **Spaced retrieval tests** — delayed quizzes that measure *retention* (the thing that matters), not in-the-moment performance (which is inflated).
- **Transfer problems** — novel problems testing whether they can *apply*, not just recall (the Kestin study's outcome measure — "solve novel problems").
- **Pre/post normalized gain** — the standard learning-science measure.

These calibrate and validate everything else — and they're the reward signal the whole optimization needs (Part VIII).

### Manufacturing training data (the LearnLM lesson)

We won't have millions of traces at launch. So, like LearnLM: **synthesize** (LLM-simulated student↔tutor dialogues, seeded with realistic misconceptions), **author** ("golden" lessons with great teachers), and **harvest** early-user transcripts (with consent). A simulated-student model (even a rough one) also lets us *train and evaluate sequencing policies offline* before risking them on real kids — essential, because online experimentation on children is ethically constrained.

---

## Part VIII — Evaluation (how we know it's real, and the trap that kills edtech)

### The engagement-metric trap (memorize this)

TikTok measures time-on-app and it's *valid for them*. **If we optimize the same metric, we have failed**, because a kid can be highly "engaged" and learning nothing (or being harmed). This is the most common way edtech fools itself. **Our primary metrics must be learning, not engagement:**

- **Normalized learning gain** — (post − pre) / (max − pre). The standard.
- **Long-term retention** — performance on *spaced* delayed tests (days/weeks later). This is the real prize and what spacing/retrieval practice optimize.
- **Transfer** — performance on *novel* problems (Kestin's measure). Did they *understand*, or memorize?
- **Time-to-mastery** — Kestin's "*less* time" — efficiency is a feature; *less* time-on-app for the same learning is *good*.

**Engagement metrics are guardrails and *means*, not goals:**

- **Voluntary return / streak of genuine use** — proxy for healthy motivation (retention is the business — a memory note already says this).
- **Flow ratio** — fraction of session in estimated flow vs. boredom/frustration.
- **Raw time** — a *cost and a guardrail* (too long = inefficient or stuck), never a target.

### The credit-assignment / "Where's the Reward?" problem (the central research hardness)

This deserves its own flag because it's *the* reason RL-for-teaching is hard and why we can't just bolt on TikTok's playbook. There's literally a review paper titled **"Where's the Reward? A Review of Reinforcement Learning for Instructional Sequencing"** (Doroudi, Aleven, Brunskill). The problem:

- TikTok's reward (watch/like) is **immediate, abundant, cheap, unambiguous.** Our true reward (durable learning, transfer) is **delayed (days), sparse, expensive to measure, and confounded** (did *we* cause the learning, or school, or the kid's mood?).
- You cannot run TikTok-style real-time RL when the reward arrives a week later and costs a quiz to measure.

**The pragmatic answer (this is the architecture of the optimization):**

1. **Short-horizon proxy rewards** for the real-time/online loop: immediate correctness, *flow signals* (the affect model), productive-confusion-then-resolution, engagement. These are abundant and fast.
2. **Periodic ground-truth anchoring**: spaced retrieval + transfer tests *validate and re-weight* the proxies — confirm the proxies actually predict real learning, recalibrate when they drift. (Guards against optimizing a proxy that diverges from learning — exactly the trap.)
3. **Offline simulation**: train/test sequencing policies against simulated students (built from the knowledge-tracing models) *before* any live rollout — because RCTs on kids are slow and ethically gated.
4. **Constrained action space + conservative methods**: prefer **contextual bandits** over a *curated* set of pedagogically-sound actions to open-ended deep RL. Bandits are sample-efficient, safer, and interpretable. Earn the right to fancier RL with data and proven simulators.
5. **A/B + RCT for ground truth**: offline metrics *propose*; controlled online experiments (with the learning outcomes above) *decide*. Hold the line that the deciding metric is *learning*, never engagement.

---

## Part IX — Synthesis: Feynman's Intelligence Architecture & Build Sequence

Pulling it together into *what we actually build*, mapped to what exists in the repo.

**The system is:** a **persistent, interpretable student model** (knowledge trace + affect + misconceptions), feeding a **two-loop teaching policy** (bandit outer loop that holds the kid in *flow*, LLM inner loop that teaches step-by-step under pedagogical constraints), realized as **real-time voice + a living visual board**, all running on a **pre-compute index for latency** and a **streaming event flywheel** that makes the student model and policies compound — measured by **learning, not engagement**, with **flow as the control variable that aligns the two.**

**What already exists (assets to build on):**

- Curriculum graph pipeline → the **KC/prerequisite spine** (Part II/III need this).
- `data_pre_compute_v2` + pre-generated DiagramSpecs → the **candidate index / latency solution** (Part VI).
- Three-graph architecture (curriculum / board-state / per-student) → the **skeleton** the student model slots into.
- Real-time LiveKit voice + visual board → the **perception & realization** layers and our **implicit-signal advantage** (Part VII).
- Session tree/graph (main + doubt branches) → VanLehn's **two-loop** structure.

**What's missing (the priority gaps, in build order):**

1. **The event taxonomy + logging** (Part VII) — *do this first, before models exist*; you can't retro-collect signals. Highest-leverage, lowest-glamour.
2. **The interpretable student model** (Part II, Layer 1) — IRT/BKT backbone over the KC graph + a short adaptive diagnostic for cold start. This unlocks mastery decisions, the parent dashboard, and policy conditioning.
3. **The real-time affect/flow estimator** (Part II, Layer 2) — start with rules over latency + prosody + dialogue cues; this is novel and directly powers the engagement loop.
4. **Pedagogical constraints on the LLM** (Part V) — the "withhold, scaffold, diagnose, make-them-try" policy (the Kestin/LearnLM lesson). Cheap, huge quality delta.
5. **The flow-holding outer loop** (Part III/IV) — start with a contextual bandit over difficulty/representation that uses the student model to keep challenge ≈ skill.
6. **Ground-truth measurement** (Part VIII) — spaced retrieval + transfer tests, so we can *prove* learning and *anchor* the proxies. Without this we're flying blind and optimizing vibes.
7. *(Later, with data)* deep knowledge tracing, learned sequencing policy, pedagogical fine-tunes, the full flywheel.

The sequencing principle: **build the brain (2,3) and the measurement (6) before the fancy optimization (7).** Most edtech does it backwards — flashy adaptive-RL claims on top of no real student model and no learning measurement. The student model + honest evaluation *is* the product; the rest is amplification.

---

## Part X — The Reading List (basics → hardcore, by pillar)

Prioritized. ★ = start here.

**Learning science (the pedagogy):**

- ★ Bloom (1984), *The 2 Sigma Problem* — the founding motivation.
- ★ VanLehn (2011), *Relative Effectiveness of Human Tutoring, ITS, and Other Tutoring Systems* — the efficacy numbers + inner/outer loop.
- Bjork & Bjork (2011), *Making Things Hard on Yourself, But in a Good Way: Desirable Difficulties.*
- Roediger & Karpicke (2006), *Test-Enhanced Learning* (retrieval practice).
- Sweller — Cognitive Load Theory (any survey).
- Chi et al. — self-explanation effect.
- D'Mello & Graesser (2012), *Dynamics of Affective States During Complex Learning* — the confusion/flow/boredom model.
- *(Myth to inoculate against)* Pashler et al. (2008), *Learning Styles: Concepts and Evidence* — why learning-styles personalization is pseudoscience.

**Intelligent tutoring systems (the lineage):**

- VanLehn (2006), *The Behavior of Tutoring Systems* — inner/outer loop framework.
- Anderson et al. — Cognitive Tutors / ACT-R (model tracing).
- Graesser — AutoTutor (dialogue-based tutoring).
- Kulik & Fletcher; Ma et al.; Steenbergen-Hu & Cooper — the ITS meta-analyses.

**Student modeling / knowledge tracing (the math):**

- ★ Corbett & Anderson (1995), *Knowledge Tracing* (BKT) — the classic.
- Item Response Theory — any psychometrics text (Rasch / 2PL / 3PL).
- ★ Piech et al. (2015), *Deep Knowledge Tracing* (NeurIPS).
- Zhang et al. (2017), DKVMN. Pandey & Karypis (2019), SAKT. Ghosh et al. (2020), *Context-Aware Attentive KT (AKT)*. Choi et al. (2020), *SAINT / SAINT+*.
- Khajah, Lindsey, Mozer (2016), *How Deep is Knowledge Tracing?* — the essential BKT-vs-deep reproducibility critique.
- Doignon & Falmagne — Knowledge Space Theory (ALEKS).
- Settles & Meeder (2016), *A Trainable Spaced Repetition Model* (Half-Life Regression, Duolingo).

**Recommendation systems (the TikTok machine):**

- ★ Covington, Adams, Sargin (2016), *Deep Neural Networks for YouTube Recommendations* — the two-stage pattern.
- Koren, Bell, Volinsky (2009), *Matrix Factorization Techniques for Recommender Systems.*
- Cheng et al. (2016), *Wide & Deep.* Naumov et al. (2019), *DLRM.*
- Kang & McAuley (2018), *SASRec*; Sun et al. (2019), *BERT4Rec* — sequential (= the KT connection).
- ★ Liu et al. (2022), *Monolith* (arXiv:2209.07663) — TikTok's real-time training.
- Li et al. (2010), contextual bandits; Thompson sampling — exploration.

**RL for instructional sequencing (the hard optimization):**

- ★ Doroudi, Aleven, Brunskill, *Where's the Reward? A Review of RL for Instructional Sequencing* — read this *before* attempting RL-for-teaching.
- Reviews of MAB/deep-RL in education (Springer IJAIED 2025 survey).

**Motivation & engagement (the loop):**

- ★ Deci & Ryan — Self-Determination Theory (autonomy/competence/relatedness).
- ★ Csikszentmihalyi — *Flow.*
- Loewenstein (1994), *The Psychology of Curiosity* (information-gap theory).
- Lepper, Greene, Nisbett — the overjustification effect (why naive gamification backfires).
- Eyal, *Hooked* — habit mechanics (read *critically*, repurpose for healthy habits).

**LLMs as tutors (the substrate, 2024–2026):**

- ★ LearnLM team (2024), *LearnLM: Improving Gemini for Learning* (arXiv:2412.16429).
- ★ Kestin et al. (2025), *AI Tutoring Outperforms Active Learning: an RCT* (*Scientific Reports*).
- Tutor CoPilot (2024) — human-AI tutoring at scale.

**Affective computing:**

- Picard (1997), *Affective Computing* — the founding text.
- D'Mello & Graesser — affect-sensitive AutoTutor.

---

### The one-paragraph version (if we forget everything else)

Build a **persistent, interpretable model of each student** — what they know (knowledge tracing over a real curriculum graph), how they feel (a real-time affect/flow estimator off voice + timing), and who they are over time (pace, misconceptions). Condition a **two-loop teaching policy** on it: a bandit outer loop that keeps challenge matched to skill (**flow = ZPD = the one knob that makes the product engaging *and* effective at once**), and an LLM inner loop that teaches step-by-step under hard pedagogical constraints (withhold, scaffold, make-them-try). Steal TikTok's **machine** — real-time per-user modeling, two-stage retrieval, embeddings, the data flywheel — but **never its objective**: optimize **learning**, measured by spaced retention and transfer, with engagement as a *means and a guardrail*. Instrument **every implicit signal from day one** (latency, prosody, hesitation) because that's the moat and you can't retro-collect it. The LLM is the brilliant **actor**; the **student model is the brain**; the **data loop is the moat**. And the whole thing is held together by the one beautiful fact TikTok will never have: **the state that engages a learner most is the state that teaches them most.**