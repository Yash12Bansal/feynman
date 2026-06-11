# Design Doc 20 — Student-as-Teacher ("Your Turn"): Creativity, Pride & the Protégé Effect

**Status:** Idea proposed + researched. Not yet sequenced. Awaiting Yash's go/no-go on prototyping as an Aanya-demo coda.
**Authors:** Yash (the question — "what can let students show creativity and feel proud/empowered on the platform?"). Claude (research + synthesis + recommendation).
**Date opened:** 2026-06-08
**Branch:** TBD (prototype likely off the Aanya-demo line).
**Related:** `12-aanya-demo-v0.md` (the "kid-solves-it" magic beat this evolves), `15-doubt-orchestrator.md` / `16-diagram-awareness-rearchitecture.md` (the doubt-tree + gap-detection engine this inverts), `19-feynman-standard-lecture-pipeline.md` (the teaching bar this is measured against).

---

## 0 · The one idea everything else serves

The most powerful, most on-brand, most pride-generating feature we can add is **not a new feature** — it's the **inversion** of the product we already built:

> **Let the student become the teacher. The student picks up the chalk; Feynman becomes the curious, slightly-behind learner.**

Our product is named after the man whose entire thesis was *"if you can't explain it simply, you don't understand it."* We've built an AI that teaches with real-time voice, a live visual board, and a doubt-branching engine. Flipping it — the student teaches, Feynman learns, asks "why?", gets confused, has aha moments — is the purest possible expression of the brand, AND the most robustly validated idea in this entire field, AND almost nobody has built it well for consumers.

The mark of the greatest teacher isn't that they explain well. It's that **their students can teach it back.** This feature is the *proof the mission is working.*

---

## 1 · Why this is not a hunch — the evidence

This is the single most-validated idea in the learning-by-teaching literature.

- **The protégé effect is real and measured.** In the canonical Stanford/Vanderbilt studies, kids who *taught* a teachable agent spent more time learning and learned more than kids studying the identical material for themselves — and the effect was **largest for lower-achieving students**, exactly the "I don't get it" kid we're built for. ([Stanford AAA Lab](https://aaalab.stanford.edu/assets/papers/2009/Protege_Effect_Teachable_Agents.pdf), [Springer — Chase & Chin](https://link.springer.com/article/10.1007/s10956-009-9180-4))
- **It's a 20-year research program, not a hunch.** Vanderbilt's *Betty's Brain* has students teach an agent named Betty, then watch Betty take a quiz on what she was taught. Kids treat the agent *socially* — they feel responsible for her, get visibly upset when she fails, and learn from that. But Betty's Brain is clunky concept-maps. **We have voice + a beautiful live board.** We can build the version they could only dream of. ([Vanderbilt LIVE](https://lab.vanderbilt.edu/live/2024/06/20/bettys-brain/), [Wikipedia](https://en.wikipedia.org/wiki/Betty's_Brain))
- **It now works with LLMs.** Recent studies show teaching an LLM agent measurably improves the human's knowledge gains and self-regulation — *with one critical design catch* (see §4, step 2). ([Wiley/BJET](https://bera-journals.onlinelibrary.wiley.com/doi/abs/10.1111/bjet.70001), [arXiv 2412.15226](https://arxiv.org/html/2412.15226v1))
- **It satisfies all three drivers of intrinsic motivation at once.** Self-Determination Theory says motivation *and creativity* flourish when autonomy + competence + relatedness are met. Teaching hits all three: *autonomy* (how she explains is hers), *competence* (she's the expert), *relatedness* (she's helping someone). ([SDT.org](https://selfdeterminationtheory.org/theory/))
- **It's the constructionism payoff.** Papert/Resnick (Scratch) showed motivation spikes when learners make a **shareable artifact for an authentic audience**. A lesson she taught *is* that artifact. ([FabLearn/Stanford](https://fablearn.stanford.edu/fellows/blog/constructionism-learning-theory-and-model-maker-education))

---

## 2 · Why it's perfect for *Feynman* specifically

1. **It reuses our entire architecture, inverted.** Doubt branches → now Feynman asks the doubts. Board rendering tools → now in her hands. Gap-detection intelligence → now pointed at *her explanation*. We're not building a new engine; we're flipping the polarity of the one we have.
2. **Creativity is intrinsic to teaching, not bolted on.** Choosing the analogy, the example, what to draw, the framing — there are infinite right answers. That's the creative surface, and it's *load-bearing* for the learning, not a distraction app sitting next to it.
3. **"I taught it" is the most empowering sentence in education.** Far more than "I got 18/20."
4. **It's the best assessment we could build.** When a kid teaches, we see *exactly* where understanding is solid vs. hollow — richer signal than any quiz. It feeds the per-student knowledge graph with the highest-quality data we'll ever get.
5. **In India, it's a relief valve.** 35–37% of Indian secondary students report high academic stress and exam anxiety ([study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4129138/)). This mode is the *one place* where there's no wrong answer and the kid is the confident expert. For a terrified 14-year-old, that emotional reversal is rare and precious — and it's positioning **no exam-prep competitor can copy** without contradicting themselves.

---

## 3 · Mission / moat / retention fit

- **Mission ("better than any human teacher"):** The greatest teachers don't just explain — they make you *capable of explaining*. This is the most teacher-complete thing we could build.
- **Moat:** ChatGPT answers questions. A structured, voice + visual-board, gap-detecting, artifact-producing "teach it back to a curious AI and build your body of work" loop is a *product*, not a prompt. Defensible and deeply differentiated.
- **Retention (THE metric):** Creativity + pride + a growing portfolio + parent-share = the strongest re-engagement loop we can build. A kid comes back to teach, to add to their museum, to make a parent proud. That's the 3–4×/week behavior that defines a real product vs. noise.

---

## 4 · The hero feature: "Your Turn" (the student teaches)

The craft is everything here. The student does **not** teach the master Feynman (intimidating). She teaches **a younger, curious learner who looks up to her** — a junior persona/tutee. Betty's Brain's whole power was the kid feeling *responsible for* the tutee. For an Indian teen, being the knowledgeable elder is a high-status, pride-rich role.

(Alternative framing kept in reserve: Feynman himself plays humble — "teach me, I'm rusty on this." Teaching "down" to a struggling junior is more empowering and triggers the responsibility/protégé effect harder than teaching "up" to a master, so the junior-tutee is the default.)

**The flow:**

1. After Aanya learns trigonometry (or anytime she chooses), the board flips. She has the pen. The little learner says: *"I have a test on this and I really don't get it. Can you teach me?"*
2. **The AI plays dumb — convincingly.** This is the make-or-break design constraint the LLM research surfaced: an LLM's vast knowledge *discourages* the human from teaching, so we must **deliberately restrain its knowledge and make it ask genuine "why/how" questions** (the TeachYou / AlgoBo finding, [arXiv 2412.15226](https://arxiv.org/html/2412.15226v1)). It never lectures. It asks *"why can you square both sides?"* It makes a believable mistake to see if she catches it.
3. **She uses our board** — draws the triangle, writes the ratio, points — the same gorgeous tools, now hers.
4. **The Analogy Forge moment.** When she invents her own analogy, the AI *celebrates the originality*: *"Oh — I've never pictured it as a [cricket field] before. That actually makes it click."* Rewarding invention is the creativity payoff.
5. **The consequence (the Betty's Brain mechanic — this is the magic).** The little learner then tries a *fresh* problem using **only what she taught it.** Teach it well → it succeeds and is thrilled. Left a gap → it gets stuck *in exactly that spot*. The gap shows up on the lovable tutee, not as a red X on her — so it feels *protective* ("let me fix that for you") instead of like failure. And it's a sneaky-perfect diagnostic of *her* understanding.
6. **It produces an artifact:** *"Aanya teaches the Pythagorean Theorem (with a pizza analogy)"* — saved, replayable, shareable.

**The latency surprise:** this mode is *easier* than live teaching, not harder. When she's teaching, the AI is *listening*; turn-taking is forgiving; "hmm, let me think…" is *in character* and buys time; the board is in her hands so we're not racing to render. The hard part is purely the AI staying believably restrained and detecting her gaps accurately — and gap-detection is the one thing we've already built.

---

## 5 · The system around it (ranked — most are facets of the hero, not separate builds)

1. **The portfolio — "My Lessons" / an Aha Museum.** A beautiful gallery of everything she's made: lessons taught, original analogies, problems invented, breakthroughs. This is the constructionism authentic-audience loop *and* portfolio-as-assessment (which research shows lowers anxiety and raises agency — [Edutopia](https://www.edutopia.org/article/standards-based-portfolio-assessment/)). **Build this with the hero — it's the pride container.**
2. **The parent-share loop.** A parent gets: *"Aanya taught a full lesson on trigonometry today. Watch it."* **This is what actually justifies ₹4,000/mo** — visible, emotional proof of confidence and growth, not "she did 20 problems." It directly attacks the parent trust-hill the strategy memo calls the steepest. **Build with the hero.**
3. **Problem Author / "Stump Feynman."** She invents her own word problems framed in *her* world (her game, cricket, K-pop); the AI checks they're well-formed and tries to solve them; she can challenge friends. Different creative flavor (generative, not explanatory) + a social hook. **Strong — build right after the hero.**
4. **Community remix library** (share analogies/problems others can use and upvote). Powerful — it's Scratch's remix culture + the *relatedness* need + the peer-status dynamics that matter intensely for Indian teens. But it needs a user base and moderation. **Phase 2–3, post-traction.**

---

## 6 · What we will NOT do (brutal honesty)

- **Don't chase the "student-creators make short-form videos" trend** (Khan/Zenius are leaning in). The research itself flags that virality undermines conceptual depth ([Kadence](https://kadence.com/en-us/knowledge/edtech-platforms-embrace-student-creators-to-drive-growth/)), and it's a *marketing* motion, not a learning product. A taught lesson *can* become shareable — but TikTok-ification is not the goal.
- **Don't build a generic "creative sandbox" disconnected from learning.** Creativity without the learning spine is just another distraction app. The whole point is creativity *as the vehicle for understanding.*
- **Don't gamify with badges/points as the primary reward.** SDT is explicit: extrinsic trinkets can *crowd out* intrinsic motivation. The reward must be the artifact + the AI's authentic reaction + the parent's pride. Don't cheapen it.

---

## 7 · Three-factor scorecard (per `feedback-three-factor-evaluation`)

| Factor | Verdict |
|---|---|
| **Precision / accuracy** | The risk: the AI breaks character, shows off, or over-corrects. Mitigated by the research-backed *restrained-knowledge* prompt pipeline (§4 step 2). Gap-detection reuses our doubt engine. **Hard but tractable.** |
| **Latency (real-time)** | *Easier* than live teaching — AI listens more, talks less, "thinking" is in-character, board is in the student's hands. **Latency-friendly mode.** |
| **Cost (per-hr session)** | Comparable to or *cheaper* than a teaching session (student talks more = fewer AI tokens + less TTS). Artifact storage is trivial. **Within budget.** |

---

## 8 · Recommendation + first step

Build **"Your Turn"** as the hero, with the **portfolio + parent-share** as its container. It's the most on-brand, most evidence-backed, most defensible, and most *emotionally* powerful thing we can add — and it strengthens the core mission rather than diverting from it.

**Smallest first step (fits what we're already building):** the Aanya demo's third magic beat is currently "the kid solves it." The more powerful version of that exact beat is **"the kid teaches it."** Prototype "Your Turn" as a ~90-second coda to the trig lesson — Aanya teaches the little learner the ladder-against-the-wall idea — and see if internal viewers say "whoa." If teaching trig back is the moment that makes a parent tear up, we've found something far bigger than a feature.

**The one research risk to de-risk early (the whole ballgame):** *can we make the AI play a believably dumb, restrained student that asks good questions and stays in character?* Worth a ~1-hour prompt spike before committing — the restrained-knowledge pipeline (TeachYou/AlgoBo) is the technique to validate.

---

## 9 · Sources

- [Stanford AAA Lab — Teachable Agents and the Protégé Effect](https://aaalab.stanford.edu/assets/papers/2009/Protege_Effect_Teachable_Agents.pdf)
- [Springer — Chase & Chin, Teachable Agents and the Protégé Effect](https://link.springer.com/article/10.1007/s10956-009-9180-4)
- [Vanderbilt LIVE — Betty's Brain](https://lab.vanderbilt.edu/live/2024/06/20/bettys-brain/)
- [Wikipedia — Betty's Brain](https://en.wikipedia.org/wiki/Betty's_Brain)
- [Wiley / British Journal of Educational Technology — Learning by teaching with ChatGPT](https://bera-journals.onlinelibrary.wiley.com/doi/abs/10.1111/bjet.70001)
- [arXiv 2412.15226 — teachable ChatGPT agent (restrained-knowledge / why-how questioning, TeachYou & AlgoBo)](https://arxiv.org/html/2412.15226v1)
- [Self-Determination Theory (Deci & Ryan)](https://selfdeterminationtheory.org/theory/)
- [FabLearn/Stanford — Constructionism & maker education](https://fablearn.stanford.edu/fellows/blog/constructionism-learning-theory-and-model-maker-education)
- [Edutopia — portfolio-based assessment](https://www.edutopia.org/article/standards-based-portfolio-assessment/)
- [Kadence — edtech platforms & student creators (and the depth-vs-virality caveat)](https://kadence.com/en-us/knowledge/edtech-platforms-embrace-student-creators-to-drive-growth/)
- [NCBI — test anxiety among Indian board-exam students](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4129138/)
