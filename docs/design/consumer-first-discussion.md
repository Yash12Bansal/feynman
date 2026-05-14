Good. I think you're right — but for sharper reasons than the one you gave. Let me push on the logic and then lay out what this
  actually means.

  "In our control" — the real version of that argument

  The reason "in our control" matters isn't really control. School sales has tons of leverage we'd lack as consumer (one district
  win = thousands of kids overnight; one viral TikTok backlash kills a consumer brand). Both markets have their own gatekeepers.

  The real argument for consumer-first is: consumer is the only market that will let you build a magical product. Schools tolerate
  mediocre software. Procurement, IT, district politics — none of that selects for delight. A kid who's bored opens TikTok instead.
  A parent who paid $30 last month and got nothing magical cancels. Consumer is the fire that forces you to actually be great. It's
  a quality-forcing function masquerading as a market choice.

  That's the case. And it lines up with everything in MEMORY.md about the bar we want to hold ourselves to. So yes — I'm with you on
   the pivot. But let's be honest about why, because that framing changes which decisions we make next.

  What this actually changes (less than you'd think)

  Most of what we've built and designed transfers directly. The pivot is more focusing than throwing away:

  Survives the pivot intact:
  - Teaching agent state machine, branching, doubts
  - Curriculum graph pipeline (per-student knowledge instead of shared classroom spine, but the graph structure is the same)
  - Visual engine — split-board, design_agent, anticipation engine, all of it
  - Voice + visual modality, real-time interaction
  - Per-student knowledge graph (was always per-student)
  - LiveKit pipeline

  Gets cut or simplified:
  - Multi-student perception, zone tracking, voice identification across speakers — all gone. One kid, one camera, one voice.
  Massive simplification.
  - Teacher dashboard
  - Hardware planning (Jetson, classroom cameras, etc.)
  - COPPA-class regulatory work simplifies to "standard parental consent"
  - Mode 1 vs Mode 2 distinction collapses to one mode
  - "Public doubts" classroom dynamic disappears (it's now a 1:1 conversation)
  - B2B/B2G sales scaffolding (we never built it; now we never have to)

  The classroom perception design from yesterday becomes much simpler too: one student, one camera, one set of signals, no zones.
  Gemini API in selective mode is now obviously the right v0.

  What becomes hard (the new game we're signing up for)

  This is where I want to be brutally honest. Consumer EdTech is one of the hardest categories in software. The graveyard is
  enormous. Here's what we're really committing to:

  1. The first 90 seconds matter more than everything else.
  A kid opens our app. If by 90 seconds they aren't delighted and curious, they're gone forever. Duolingo's first-session retention
  is a religion they obsess over. We need to be at that level on day one. Not after a polish phase. Day one of public launch.

  2. CAC is brutal.
  Paid acquisition for parents is $30–80 CPI. Organic is hard without a viral hook. Khan Academy spent a decade building brand
  before it had pull. We need either (a) a viral product mechanic, (b) influential endorsement (a famous educator? a viral parent
  demo?), or (c) very deep pockets. Best case is (a) — figure out the share moment.

  3. Retention is the metric, not signups.
  A kid using us 4x/week for 6 months is a real product. A kid who tries us once and bounces is noise. We need engagement loops that
   don't feel like manipulative gamification (Duolingo guilt-streaks) but also actually work. This is the hardest design problem in
  consumer EdTech and we don't have an answer yet.

  4. The competitive set is heating up fast.
  ChatGPT can already tutor for free. Synthesis ($200/mo, ex-Ad Astra) is in this space. MathAcademy. Brilliant. Khan Academy's
  Khanmigo. Photomath. ChatGPT for Schools. We need to be 10x better than free ChatGPT for a parent to pay us, not 2x better. The
  teaching state machine, the branching, the visual board — that's the thesis for why we're 10x. We need to show that on day one.

  5. The trust hill is steep.
  Parents are protective. "AI tutor for my kid" sets off alarm bells. We need to over-invest in transparency: parent dashboard
  showing exactly what was discussed, explicit content guardrails, clear pricing, no manipulative growth tactics. The stuff that
  consumer apps cut corners on, we can't.

  6. Pricing is uncertain.
  $10/mo says "I'm a worksheet app." $30/mo says "I'm a tutor." $200/mo (Synthesis) says "I'm a school replacement." Different
  prices imply different products. We need to pick a ceiling early because it shapes every design decision.

  What I think the next move is

  If we're committing to this — and we should commit, no half-measure — here's what I'd do this week:

  1. Write a consumer-product memo together. A short doc — 2–4 pages — that captures: target persona (a specific kid/parent
  archetype, not "K-12 STEM"), the pricing thesis, the magic-moment definition, the engagement loop, the competitive cut. Not a
  13-phase plan. A clear product north star. Save to docs/strategy/01-consumer-product-thesis.md.
  2. Define the demo. One specific 7–10 minute experience that, if a parent watched it, they'd open their wallet. Pick the subject
  (algebra? physics? fractions for younger kids?), the kid persona, the moment. Everything else gets prioritized against making that
   demo magical.
  3. Audit the existing roadmap against the new thesis. Some of what's in flight (split-board) is exactly right. Some (teacher
  dashboard scaffolding, classroom voice ID, multi-student perception) gets shelved or cut. The classroom-perception doc I just
  wrote needs a v0 rewrite as "single-student perception via Gemini" — much smaller scope.
  4. Decide on platforms. Web first? iOS? Tablet-only? This is a real call. My instinct: web on a laptop, with a good tablet
  experience as a stretch. Phone is bad for the visual board format.
  5. Park the school stuff cleanly, don't delete it. The classroom architecture isn't wrong, it's premature. We'll come back to it
  after consumer traction. Move the school-specific designs to docs/design/archive/ and add a one-line "deferred until consumer
  traction" note. We're not abandoning the long-term vision; we're sequencing.

  One thing I want to flag

  The reason consumer EdTech founders fail isn't usually that the product is bad. It's that they get distracted by everything except
   the one thing that matters: the magic moment.

  The trap with our existing momentum is: we have so much in flight (curriculum graph, split-board, visual engine, perception layer)
   that "polish toward consumer launch" can fan out into 50 sub-projects. If we let it, we'll spend six months doing breadth and
  never ship the magic moment.

  So my hard take: before any of the above five steps, define the demo. One scenario. A specific kid. A specific subject. A specific
   7-minute arc. Then everything else — what we cut, what we polish, what we defer — gets ranked by "does it make THAT demo
  magical." That's the only filter.

  Want me to draft the consumer-product memo as our starting artifact? I'd write it as a short, opinionated thesis doc — not a
  feature plan — and we iterate from there. Or do you want to talk through the persona and demo definition first, in conversation,
  before I commit anything to disk?
