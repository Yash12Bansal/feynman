# Architecture Analysis: Precompute + Live Pipeline

## What Was Proposed (Yash's Architecture Diagram)

Two-phase architecture drawn in Excalidraw:

### Precompute Phase (left box)
```
Book --> Table of Contents --> Chapterwise split:
  |
  +--> Text Extracted ---+
  |                      |
  +--> Images Extracted --+--> Data Warehouse

Metadata to identify the book: Class, Subject, Board, Author, Edition

Text + Images feed into "Dig following script along with descriptions":
  |
  +--> Script --> Lecture Script ("now I will be drawing")
  |
  +--> JSON structure:
       {"lec": "photosynthesis is",
        "dig+description": [
          1. plant lifecycle,
          2. sunlight to energy conversion
        ]}

JSON --> Validator --> Design Agent --> Diagram codes (dict description vs image_code)

Data Ingestion pipeline at bottom
```

### Live Phase (right box)
```
Lecture2 (prepared lecture) --> Text to Speech --> LiveKit service
                                                    |
                                              +-----------+
                                              |           |
                                           doubt      no doubt
                                              |
                                           lookup (back to precompute assets)
```

---

## What's Strong About This Design

### 1. Book-first content pipeline
Starting from actual textbooks is smart. Schools care about curriculum alignment. This grounds the product in what teachers already use. When a school adopts Feynman, they can say "it teaches from YOUR textbook."

### 2. Separating script from diagram descriptions
The JSON structure with `lec` + `dig+description` shows thinking about the dual-stream problem (voice + visuals need to be generated together but delivered differently). This is the right instinct.

### 3. Precomputing diagram assets
Diagram generation is slow (2-10 seconds per diagram with current LLMs). Having them ready eliminates the biggest latency source during live teaching. The Design Agent + Diagram codes pipeline handles this.

### 4. Doubt -> lookup back to precomputed material
This shows thinking about how to handle interruptions without latency. If a student asks about something and the diagram is already precomputed, you can show it instantly. Smart.

### 5. Validator between generation and rendering
Having a validation step between the JSON structure and the Design Agent shows awareness that LLM output needs checking before being shown to students. This is critical for accuracy.

---

## What Concerns Me Deeply

### 1. This architecture produces a "smart recorded lecture," not an AI teacher

The entire lecture is precomputed — script, diagrams, everything. At runtime, you're essentially playing a recording through TTS, with a "doubt handler" bolted on. That's fundamentally different from what Feynman should be.

**The difference matters for investors and users:**
- A recorded lecture with Q&A = EdTech 1.0 (Khan Academy, Coursera)
- An AI that thinks, adapts, and creates in real-time = what we're building

If everything is precomputed, the natural follow-up question from any investor is: "so it's a video lecture with a chatbot?"

The magic we promised is: **the AI thinks, adapts, and creates in real-time.** It notices when a concept isn't landing and pivots. It responds to a student's weird analogy and runs with it. Precomputing the script kills that.

### 2. The Live Phase is dangerously underspecified

The right-side box has: TTS -> LiveKit -> doubt/no doubt. But where is:

- **The teaching state machine** (our core IP — the tree/graph session structure)?
- **The visual rendering** — what are students actually SEEING on the screen?
- **Voice-visual synchronization** — "now I will be drawing" is a stage direction, but how does the system coordinate saying words while a diagram animates?
- **Comprehension checks** — the AI should be ASKING students, not just waiting for doubts
- **Pacing adaptation** — most students never ask doubts. Silence does not equal understanding.

### 3. The "doubt" branch is too simple

Current: doubt -> lookup precomputed material. But:

- What if the doubt is about something NOT in the precomputed material?
- What if the doubt reveals a fundamental misconception that requires a completely different explanation?
- What about doubts that are GOOD — where a student is connecting ideas and the AI should go deeper?
- What about nested doubts (doubt about the doubt response)?

This needs the full branching state machine, not just a lookup table.

### 4. The frontend/screen is entirely absent

Half the product — what students see — isn't in this architecture at all. The diagram codes get precomputed but there's no path showing how they reach the screen, when they appear, how they animate, or how they sync with voice.

### 5. Book metadata extraction is hand-waved

"Book -> TOC -> Chapterwise -> Text + Images" is a massive engineering pipeline drawn as 4 bubbles. PDF/textbook parsing, image extraction, structure detection, equation recognition — each of these is a hard problem. For a prototype, this should be shortcut entirely.

---

## The Fundamental Problem: Optimized for the Wrong Thing

The architecture is optimized for "how do we process a textbook and deliver content." It should be optimized for "how do we make the live classroom experience feel magical."

### The Key Insight: Precompute the PLAN, Not the PERFORMANCE

A real teacher doesn't memorize a script. They prepare:
- What concepts to cover (lesson plan)
- What diagrams/visuals to have ready (asset library)
- What common misconceptions students have (knowledge base)
- What questions to ask to check understanding (comprehension checks)

Then they PERFORM live — adapting, improvising, reading the room.

Feynman should do the same.

---

## Proposed Restructuring

```
PRECOMPUTE PHASE (Curriculum Prep)
----------------------------------
Book --> Extract --> Structure into:
  1. Concept Graph (what depends on what)
  2. Lesson Plan (ordered checkpoints + learning objectives)
  3. Asset Library (pre-generated diagrams, equations, key visuals)
  4. Comprehension Checks (questions per concept)
  5. Common Misconceptions Bank (per concept)

This is the "sheet music" — NOT the recording.


LIVE PHASE (The Performance)
----------------------------
                    +---------------------------+
                    |   TEACHING BRAIN           |
                    |   (State Machine)          |
                    |                            |
  Lesson Plan ----> | - Knows where we are       |
  Asset Library --> | - Generates speech LIVE     |---> TTS --> LiveKit --> Audio
  Concept Graph --> | - Generates visuals LIVE    |---> Visual Instructions --> Screen
  Knowledge ------> | - Tracks comprehension     |
  Graph             | - Manages session tree     |
                    | - Adapts in real-time       |
                    +-------------+--------------+
                                  |
                    +-------------+--------------+
                    |  Student Input (via STT)    |
                    |  - Doubts --> branch         |
                    |  - Answers --> assess        |
                    |  - Silence --> check pulse   |
                    +-----------------------------+
```

The Teaching Brain has the lesson plan but **generates the actual words and visuals on the fly**, pulling from the asset library when a precomputed diagram fits, generating new ones when it needs to adapt.

### Weight Distribution
- **20% precompute**: Lesson plan, asset library, misconception bank
- **80% live intelligence**: Teaching Brain, voice-visual sync, real-time adaptation

---

## For the Prototype Demo Specifically

### Skip the book pipeline entirely for now
Hand-craft 2-3 lesson plans manually. The book extraction is infrastructure, not magic. You can fake it. Nobody in a demo will ask "but how did you parse the textbook?"

### Invest everything in the live Teaching Brain
This is what people will see and feel. The precompute pipeline is invisible to the demo audience.

### The 3 demo moments that matter (5-minute demo)

1. **"It teaches like a human"** — The AI is mid-explanation, draws a diagram in real-time while talking about it (voice-visual sync), then pauses and asks "does that make sense?" This is NOT a recording — it FEELS alive.

2. **"It handles the unexpected"** — A student asks a doubt. The AI doesn't just answer — it says "Great question. Let me show you why that's confusing..." and draws a NEW diagram on the spot, then seamlessly returns to where it was. The branching state machine in action.

3. **"It actually checks understanding"** — After a concept, the AI poses a question. Student answers wrong. The AI doesn't say "incorrect" — it says "Interesting, I think I see where the confusion is..." and re-teaches with a different analogy. THIS is the Feynman Technique.

---

## Decision Points for Yash

1. **When to build the book pipeline?** After the prototype proves the live teaching experience. Book parsing is a Phase 2/3 investment.

2. **How much precomputation for the prototype?** Hand-craft lesson plans + use our 41-component diagram engine for assets. Zero book parsing.

3. **Should the script be precomputed or live?** Live. The script is generated by the Teaching Brain in real-time. The lesson plan provides structure, not script.

4. **What about the Data Warehouse / Data Ingestion?** Defer. For the prototype, lesson plans and assets are stored in the database (PostgreSQL). A data warehouse comes when you have hundreds of textbooks to process.
