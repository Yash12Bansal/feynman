# Voice-Visual Synchronization: The Teaching Beats Approach

## The Core Problem

The AI is speaking (via TTS through LiveKit) and simultaneously needs to show visuals (diagrams, equations) on the screen that are synchronized with what it's saying.

This is the single hardest problem in making Feynman feel like a real teacher.

---

## The Core Insight

**Stop thinking of it as "syncing two streams." It's ONE stream of teaching that has voice and visual components.**

A real teacher doesn't have separate brain processes for "speak" and "draw" that need synchronizing. They think in **teaching beats** — one atomic unit of explanation that naturally includes words AND gestures/drawing. Our AI should work the same way.

---

## The "Teaching Beat" Concept

The LLM doesn't generate a script and separately generate visuals. It generates a single interleaved sequence:

```
Beat 1: [SAY] "Let's understand how plants make their food."

Beat 2: [SAY] "This is what happens inside a leaf."
        [DRAW] plant cell diagram (animation: 3s)
        [TIMING] visual starts 0.5s BEFORE speech

Beat 3: [SAY] "See this green part? That's the chloroplast."
        [HIGHLIGHT] chloroplast in existing diagram
        [TIMING] highlight fires on word "green"

Beat 4: [SAY] "The equation looks like this..."
        [EQUATION] 6CO2 + 6H2O -> C6H12O6 + 6O2
        [REVEAL] term-by-term, synced to narration fragments:
          "six carbon dioxide" -> reveal 6CO2
          "plus six water" -> reveal + 6H2O
          "gives us glucose" -> reveal -> C6H12O6
          "and oxygen" -> reveal + 6O2

Beat 5: [PAUSE] 2s  (let it sink in)

Beat 6: [ASK] "Can anyone tell me what the plant needs from outside?"
```

Each beat is self-contained. The Orchestrator plays them sequentially. **You don't need millisecond-level sync — you need beat-level sync.**

---

## The Timing Trick: Teaching Rhythm IS Your Latency Budget

Most people miss this. A real teacher's natural rhythm has HUGE gaps where visuals can load:

```
Teacher says: "Let me show you something..."     <- 1.5s of speech
Teacher turns to board                            <- 0.5s pause
Teacher starts drawing                            <- 2-4s of drawing
Teacher says: "See this?"                         <- points at drawing
Teacher explains the drawing                      <- talks about visible thing
```

That's **4-6 seconds** between "I'm going to show you" and "let me explain what you're seeing." That's an enormous latency budget. We're not fighting latency — **the natural rhythm of teaching ABSORBS it.**

The live-drawing idea (diagram drawing itself over 2-3 seconds) isn't a compromise — it's MORE engaging than instant appearance. It's a feature AND a latency cover.

---

## The Three Sync Patterns

### Pattern 1: "Draw, then talk about it" (easiest, most common — 90% of teaching)

```
Visual: Start diagram animation (duration: 3s)
Speech: "Let me show you..." (during drawing)
[wait for drawing to finish]
Speech: "See how the chloroplast captures light..."
Visual: Highlight chloroplast
```

Visual leads, speech follows. Dead simple — just sequence the actions.

### Pattern 2: "Equation term-by-term" (medium difficulty, highest wow-factor)

```
Speech: "Six CO two"        -> Reveal: 6CO2
Speech: "plus six water"    -> Reveal: + 6H2O
Speech: "produces glucose"  -> Reveal: -> C6H12O6
Speech: "and oxygen"        -> Reveal: + 6O2
```

The trick: **you don't need real-time sync. You can pre-schedule it.**

Flow:
1. LLM generates the full equation beat with term-narration pairs
2. Send the speech text to TTS — TTS returns audio WITH word timing metadata (LiveKit TTS plugins provide this via TimedString)
3. BEFORE playing the audio, calculate exactly when each term narration starts
4. Schedule visual reveals at those timestamps
5. Play audio + fire scheduled visual events simultaneously

It's like a karaoke system — pre-timed, not real-time sync. But it LOOKS perfectly synchronized.

In our current implementation, the SyncManager on the frontend already handles this — it matches spoken words against `trigger_words` in TermSyncHints using fuzzy matching. This works even if the LLM paraphrases.

### Pattern 3: "Highlight while talking" (advanced, adds polish)

```
Speech: "The ->sunlight<- enters through the leaf surface"
Visual: Highlight sunlight arrow on diagram when word "sunlight" is spoken
```

Same technique as Pattern 2 — use TTS word-boundary events to trigger highlights. The LLM embeds cue markers in the speech text, the orchestrator strips them and maps them to visual events.

Our HighlightWalk instruction already does this — it maps sub_element_ids to trigger_words and the SyncManager handles the matching.

---

## The Orchestrator Architecture

```
+------------------------------------------------------+
|                   TEACHING BRAIN (LLM)               |
|  Generates stream of TeachingBeats (structured JSON)  |
+------------------+-----------------------------------+
                   | streaming beats
                   v
+------------------------------------------------------+
|                    ORCHESTRATOR                       |
|                                                      |
|  Beat Queue: [beat5] [beat4] [beat3] > [beat2]       |
|                                        playing       |
|                                                      |
|  For each beat:                                      |
|  +---------------------------------------------+    |
|  | 1. Send visual instruction -> WebSocket      |    |
|  |    (visual starts first -- teacher "draws")  |    |
|  | 2. Wait visual_delay (e.g., 500ms)           |    |
|  | 3. Send speech text -> TTS -> LiveKit audio   |    |
|  | 4. Wait for speech to finish                 |    |
|  | 5. Next beat                                 |    |
|  +---------------------------------------------+    |
|                                                      |
|  Buffer: LLM is always 2-3 beats AHEAD of playback  |
|  This means the next visual is ready before needed   |
+------------------+-------------------+---------------+
                   |                   |
             +-----v-----+      +-----v------+
             | TTS/Audio  |      | Visual WS  |
             | (LiveKit)  |      | (Frontend) |
             +-----------+      +------------+
```

**The key: the LLM generates beats faster than they play.** A beat that takes 5 seconds to play (3s drawing + 2s speech) might take 1-2s to generate. So the buffer naturally stays full. You're always 2-3 beats ahead.

---

## The LLM Output Format

The LLM generates structured JSON chunks (streaming):

```json
{"beat": 1, "type": "narrate",
 "speech": "Let's understand how photosynthesis works."}

{"beat": 2, "type": "narrate_with_visual",
 "speech": "Here's what happens inside a leaf.",
 "visual": {"action": "draw_diagram", "spec": "photosynthesis_cell",
            "animate": true, "duration_ms": 3000},
 "timing": "visual_first", "delay_ms": 500}

{"beat": 3, "type": "narrate_with_visual",
 "speech": "See this green structure? That's the chloroplast.",
 "visual": {"action": "highlight", "target": "chloroplast", "style": "glow"},
 "timing": "visual_on_word", "cue_word": "green"}

{"beat": 4, "type": "equation_reveal",
 "terms": [
   {"latex": "6CO_2", "narration": "Six molecules of carbon dioxide"},
   {"latex": "+", "narration": "combine with"},
   {"latex": "6H_2O", "narration": "six molecules of water"},
   {"latex": "\\rightarrow", "narration": "to produce"},
   {"latex": "C_6H_{12}O_6", "narration": "one molecule of glucose"},
   {"latex": "+", "narration": "and"},
   {"latex": "6O_2", "narration": "six molecules of oxygen"}
 ],
 "intro_speech": "Here's the chemical equation."}

{"beat": 5, "type": "pause", "duration_ms": 2000}

{"beat": 6, "type": "ask",
 "speech": "Can someone tell me -- what does the plant take in from outside?",
 "expect": "comprehension_check"}
```

---

## Implementation Approach: What to Build in Order

### Week 1: Pattern 1 only — already impressive
Build the beat model and orchestrator. LLM generates beats, orchestrator plays them sequentially. Visuals appear, then speech explains them. No fancy timing — just sequential. Even this alone will feel magical in a demo.

### Week 2: Equation term-by-term reveal (Pattern 2)
Add the pre-scheduled timing mechanism using SyncManager + TermSyncHints. This is the "jaw drop" moment — the equation appearing in sync with the voice.

### Week 3: Polish — highlights and transitions (Pattern 3)
Add word-level cue points via HighlightWalk. "See THIS part" while an element glows. Add transitions between beats. Add the "Let me think about that differently..." doubt-handling flow.

---

## Why This Will Work

1. **It matches how teaching actually works** — not two parallel streams fighting for sync, but one unified teaching flow.

2. **Latency is hidden by design** — the teacher's rhythm absorbs it, drawing animations consume it, buffering prevents stalls.

3. **It degrades gracefully** — if a visual is slow, the speech just runs slightly ahead. In teaching, that's fine. "Let me show you... *pause*... there it is." Perfectly natural.

4. **Streaming diagram generation fits perfectly** — the diagram "draws itself" over seconds, matching the teacher's narration pace. No instant rendering needed.

5. **Each pattern can be built independently** — start with sequential beats (trivial), add equation sync (medium), add word-level cues (polish). Each level is impressive on its own.

---

## Decision Points for Yash

1. **Beat generation: pre-generated or real-time?** Pre-generate per concept for reliability. Real-time generation for doubts/improvisation.

2. **How tightly to couple speech and visuals?** Beat-level sync (easy, reliable) vs word-level sync (impressive, harder). Start with beat-level, add word-level for equations and highlights.

3. **What TTS to use?** Cartesia Sonic-2 (current primary) supports word timing via aligned transcripts. Already enabled with `use_tts_aligned_transcript=True`.

4. **Buffer size?** 2-3 beats ahead is the sweet spot. Enough to hide latency, not so much that adaptation is delayed.
