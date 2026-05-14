# 01 — Consumer Product Thesis: Feynman for Cambridge IGCSE in India

> A personalized AI teacher for IGCSE Year 9–10 students, sold direct to Indian parents at ₹4000/month per subject. v0 is one persona, one subject, one country. Everything else waits.

**Status**: Strategic thesis (locked)
**Date**: 2026-05-10
**Locked**: persona, market, pricing target, v0 subject, v0 geography
**Living**: distribution mechanics, demo specifics, expansion sequencing

---

## The Bet (one paragraph)

We are building Feynman as a personalized AI teacher for Cambridge IGCSE students in India, sold direct to parents. v0 is **one subject** (IGCSE Mathematics 0580), **one age band** (Year 9–10, ages 13–15), **one geography** (Indian metro IB/IGCSE families). The product replaces or supplements the ₹2000–3000/hour math tutor who comes 2–4 hours a week with a tutor that lives on the kid's laptop, knows the Cambridge syllabus and marking scheme cold, and is available the moment the kid is stuck. Pricing: ₹4000/month per subject. That's the whole bet. Everything in the product roadmap, every architectural decision, every dollar spent, every hour worked passes through one filter: *does this make Aanya's experience better?*

---

## Aanya (the persona)

Aanya is 13. Year 9 at an IGCSE school in Bangalore (or Mumbai, or Delhi NCR — the city doesn't matter, the family pattern does). Her parents pay ₹6 lakh/year for school plus ₹8000/week for a math tutor who comes Tuesday and Saturday afternoons. They are upper-middle-class professionals — partner at a law firm, founder of a fintech, doctor, senior banker — and they take their daughter's education extremely seriously. Aanya is sharp. She gets most things on the first explanation. But IGCSE math has gotten harder this year — the abstraction in algebra, proof-style questions in geometry, worded contexts in past papers — and her tutor isn't enough. Some nights she's stuck on a problem at 8 PM and the tutor isn't coming for three days. Her parents could help with elementary stuff but not Year 9 IGCSE. She's too proud to ask anyway. So she opens YouTube, finds a 17-minute video by an Indian uncle in a basement that's *almost* the right thing. She gets the answer eventually. **She does not understand why.**

That last sentence is the gap. We are filling it.

Designing for Aanya means: she is sharp (no condescension), proud (she'd rather struggle than ask), comfortable in English, comfortable on a laptop, time-pressed (homework due tomorrow), and parents-watch-engagement (the buyer is over her shoulder). Every UX decision passes through "what would Aanya think of this at 8 PM on a Wednesday."

---

## Market

| Segment | Approximate India size | Notes |
|---|---|---|
| Cambridge IGCSE schools, India | ~600 schools | Year-on-year growth ~10–15%, urban metros + tier-1 cities |
| IB schools, India | ~200 schools | More premium, more concentrated |
| Year 9–10 students (IGCSE + IB MYP combined) | ~70K–90K | Our v0 age band |
| Avg household ed spend per child | ₹8–15 lakh/year | School + tutoring + materials |
| Avg math tutor cost | ₹40K–80K/month per subject | 2–4 hrs/week at ₹1500–3000/hr |

Globally, IGCSE candidates worldwide are ~1.5M annually (UAE, Singapore, Malaysia, UK, US international, etc.). India is ~5% by volume but the highest-paying market relative to local incomes. Same product expands internationally to identical curricula in v2.

### Competitive landscape

| Competitor | What they offer | Why we beat them |
|---|---|---|
| **Save My Exams** (~£10/mo) | Study guides, practice questions | No personalized teaching, no voice, no visual board |
| **Revision Village** (~£15/mo, IB-focused) | Video tutorials, practice | Same. Static content, not interactive teaching |
| **Human tutors** (₹1500–3000/hr) | Genuine personalized teaching | Available 4 hrs/week max, expensive, inconsistent quality |
| **Khan Academy / YouTube** (free) | Massive content library | Generic, not IGCSE-specific, no personalization, no marking scheme |
| **ChatGPT / Gemini consumer** (free–$20/mo) | Conversational AI | Text-only, no curriculum specificity, no visual board, no continuity |
| **Byju's, Vedantu, etc.** | Indian EdTech | Largely targeting CBSE/JEE, weak on IB/IGCSE, brand reputation damaged |

**There is no personalized AI tutor with voice and visual board that knows IGCSE specifically. Anywhere in the world.** This is not "an underserved market." This is a market that does not have the product yet.

---

## The product wedge

Three irreducible features no competitor has, and we already have most of them in code:

1. **Real-time voice-and-visual teaching with branching.** Aanya asks "wait, why does that ratio thing work?" mid-explanation. The AI branches mid-sentence, redraws the diagram with the new framing, returns to the main thread. No chatbot does this. No video does this. Most human tutors do — but only when they're physically in the room.

2. **Cambridge IGCSE specificity.** The agent knows syllabus 0580 by heart. It refers to topic codes ("this is 5.3 — geometrical terms"). It explains the marking scheme ("they want method marks for the ratio statement, an answer mark for the value, units explicit"). It pulls real past paper questions. This is teaching *to the test* in the way premium tutors do. Generic AI teaching cannot do this without major scaffolding work — work the giants will not bother doing for one curriculum.

3. **Continuity across sessions via per-student knowledge graph.** Aanya's graph remembers what she struggled with two weeks ago. Tonight's lesson on right-triangle trigonometry connects back to her shaky moment on ratios in October. The AI calls back to her own prior reasoning. This compounds — month two is meaningfully better than month one. It is also why the kid does not switch to a competitor after month one.

These three together are why a parent pays ₹4000/month for us instead of giving the kid ChatGPT for free.

---

## Pricing

**₹4000/month per subject.** ₹6000–8000/month all-subjects (Math + Physics + Chem + Bio when those ship). 30% discount on annual.

Why this price:
- Below the ₹5000/mo threshold where the line item gets questioned
- Roughly 1/3 the cost of one human tutor session per week — clear value substitution narrative
- Premium enough that the brand reads "serious," not "EdTech app"
- Leaves room for higher tiers later (1:1 human mentor add-on, mock exam grading, EE/IA support for IB)

We will A/B ₹3000 vs ₹4000 vs ₹5000 in the beta, but ₹4000 is the working hypothesis.

---

## Why now

- **Cambridge IGCSE adoption in India is accelerating.** Schools are switching from ICSE/CBSE because IGCSE travels — kids who plan undergrad abroad need it.
- **Post-Byju's trust vacuum.** Premium Indian families are deeply skeptical of EdTech right now. The brands that survive will be the ones that demonstrably *work*, not the ones with loudest marketing. We win on quality.
- **AI teaching is now actually possible.** Two years ago this product was sci-fi. Today the model layer (Gemini, Claude, GPT) plus our state machine plus our visual engine make it real.
- **Parents already accept laptop-based learning.** Post-COVID, no friction on "kid uses laptop for an hour at home for school stuff." That cultural battle is won.

---

## Why us

- **Founder fit.** Technical/product founder, consumer market — right shape. School sales is grueling and not what we're built for.
- **Most of the engine exists.** Teaching state machine ✅. Visual board (split-board) ✅. Curriculum graph designed ✅. We need to focus and finish, not start over.
- **India network.** Founder is in India, has access to IB/IGCSE families and tutors, can validate face-to-face within days.
- **Calibrated quality bar.** The internal philosophy ("every detail must feel like somebody really cared A LOT") matches exactly what premium parents pay for. We don't have to learn this; we already believe it.

---

## What this thesis commits us to

- **One subject for v0**: IGCSE Math 0580. No spreading.
- **One age band**: Year 9–10. Not below, not above.
- **One geography for first 100 paying users**: Indian metro IB/IGCSE families.
- **Magic moment > breadth.** We obsess over Aanya's 7-minute lesson before we build a fifth topic.
- **Direct-to-parent only**, until we have 10K+ paying consumer users. No school sales, no district contracts, no enterprise complexity.

---

## What we are cutting / parking

| Area | Status |
|---|---|
| Classroom-mode features (multi-student perception, voice ID, zone tracking) | Parked |
| Teacher dashboard | Parked |
| Hardware planning (Jetson, classroom cameras) | Cut |
| FERPA / school regulatory work | Cut for v0 (parental consent simpler) |
| Public-school / B2G go-to-market | Parked indefinitely |
| Subjects beyond IGCSE Math 0580 | Parked until v1 |
| Curriculum graph pipeline at full scope | Re-scoped to IGCSE 0580 corpus only |
| Camera-based perception layer | Parked — voice signal sufficient for 1:1 |

Existing in-flight work that survives intact: split-board, design_agent, agent state machine, knowledge graph, curriculum graph pipeline (scope reduced).

---

## Sequencing (post-v0)

If v0 lands and unit economics work:
1. **v1**: IGCSE Math 0580 across full syllabus + onboarding/auth/payments + 50–500 paying users in India
2. **v2**: IGCSE Physics 0625 + Chemistry 0620 + cross-subject graph
3. **v3**: IB MYP / IB DP support + UAE, Singapore, Malaysia expansion
4. **v4**: IGCSE Biology, IGCSE Add Math, English Language, etc.
5. **v5+**: Possibly back to schools, but only as B2B layer on top of proven consumer product

This sequencing is **not committed** — it is a plausible path. The only thing committed is v0.

---

## What kills this thesis

We abandon or re-think if any of these become true within 6 months:

1. **The Aanya demo doesn't land.** ≤1 of 5 IB/IGCSE moms has an unprompted "whoa" reaction in the validation test. Means our magic moment is wrong, not just the marketing.
2. **Pricing breaks.** We cannot sustain ≥30% trial-to-paid conversion at ₹4000/mo from beta users. May reposition lower (mass IGCSE, ICSE) or upmarket (1:1 hybrid).
3. **Retention crashes.** Kids stop using us by week 4. The engagement loop is broken even if first session is magical.
4. **A giant ships exactly this.** OpenAI / Google / Anthropic launch a curriculum-specific personalized AI tutor for IGCSE. Unlikely (specificity is below their level of focus) but watched.

---

## Decision log

| Date | Decision |
|---|---|
| 2026-05-10 | Committed: consumer-first, India-first, Cambridge IGCSE Math 0580, Year 9–10, Aanya persona, ₹4000/mo single-subject pricing |
| 2026-05-10 | Cut: classroom-mode work, B2G/B2B sales scaffolding, classroom-perception layer for v0 |
| 2026-05-10 | Re-scoped: curriculum graph pipeline → IGCSE 0580 corpus only |

---

## Next artifacts (this week)

1. `docs/design/12-aanya-demo-v0.md` — beat-by-beat 7-minute demo specification
2. Demo-blocker hit list — what in current code prevents shipping the Aanya demo today

After those: 2–3 weeks of build, then validation test with 5–10 IB/IGCSE moms. If that gates pass, Phase 1 product surface (auth/payments/onboarding/5–10 topics).
