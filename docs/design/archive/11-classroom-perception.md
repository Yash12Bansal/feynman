> **ARCHIVED — 2026-05-10**
>
> This document is preserved for future reference but is **not active**.
>
> **Why archived**: We pivoted to consumer-first / single-student / India IB/IGCSE on 2026-05-10. Multi-student classroom perception is not in v0 scope.
>
> **Status**: Parked. May be revived when/if we return to schools post-consumer-traction.
>
> **Current direction**: see `docs/strategy/01-consumer-product-thesis.md` and `docs/design/12-aanya-demo-v0.md`.
>
> Content below is preserved verbatim from the May 10 design. Do not act on it without first revisiting the strategic context above.

---

# 11 — Classroom Perception (V-JEPA 2)

> A passive vision system that watches the classroom and emits structured perception events (confusion, disengagement, hand-raise intent, class energy) the teaching agent can react to. Solves the "wait for verbal interaction" gap in Mode 1 (screen-only).

**Status**: Design
**Date**: 2026-05-10
**Depends on**: Per-student knowledge graph (exists), agent state machine (exists)
**Privacy posture**: On-prem inference only. Raw video never leaves the classroom. Events only.

---

## 1. Why This Matters

Today, Feynman in Mode 1 (screen-only, no tablets) reads the room only through verbal interaction. A real teacher reads faces, posture, half-raised hands, the kid who is *about* to ask but hasn't quite committed. That signal is the difference between a generic lecture and a teacher who feels present.

We have repeatedly stated the goal: *"sense confusion and proactively adapt, not just wait for questions"*. Without a perception layer, the agent is blind between utterances. With it, the agent can branch into a re-explanation before a single hand goes up.

VL-JEPA (Chen et al., Dec 2025) demonstrates that a 1.6B-param model built on V-JEPA 2 can stream continuous semantic understanding of video at very low latency, only "decoding" to text when something semantically meaningful changes. That is exactly the shape of the classroom perception problem.

This doc specifies how to integrate **V-JEPA 2 (frozen, 304M)** as the perception backbone, with thin task heads on top, running on classroom-local hardware. The teaching agent receives only structured events.

### What this is *not*

- **Not facial recognition.** No identity inference from faces. Per-student tracking uses zone/seat assignments, never biometric identity.
- **Not video upload.** Frames never leave the device. Only structured events do.
- **Not a generation model.** This does perception. It does not draw diagrams, write LaTeX, or generate visuals. (Solved separately by curriculum-graph + design_agent.)
- **Not a cure for diagram latency.** Diagram latency is a generation problem. Perception is orthogonal.

---

## 2. The Three Signals (v1 scope)

Resist scope creep. These three first; everything else after they work.

| Signal | Per-student or class | Trigger | Agent reaction |
|---|---|---|---|
| **Confusion detected** | Per-student | Furrowed brow, head tilt, gaze unfocused, sustained ≥3s | If high-confidence and not mid-critical-step: push doubt branch on current concept |
| **Disengagement detected** | Per-student | Gaze drift away from board, slumped posture, ≥5s | Updates per-student knowledge graph; if N≥3 students simultaneously: agent slows pacing, queues check-in |
| **Hand-raise intent** | Per-student | Partial hand lift, leaning forward, sustained ≥1s | High confidence: yield floor and acknowledge by zone |

Two derived class-level signals computed from the above:

- **Class energy** — smoothed engaged-fraction over rolling 30s window
- **Comprehension momentum** — share of class with engaged-positive signals on current concept

---

## 3. System Architecture

A new perception worker process, peer to the LiveKit agent worker. Runs on classroom-local hardware. Sends events (only) over WSS to the backend.

```
┌─────────────────────────────────────────────────────────────┐
│  Classroom hardware (on-prem; no internet upload of video)   │
│                                                             │
│  [Camera] ──► [Frame Capture] ──► [V-JEPA 2 Encoder]        │
│                                          │                  │
│                              continuous embedding stream    │
│                                          ▼                  │
│                              [Probe Heads + Selective       │
│                               Decoder + Aggregator]         │
│                                          │                  │
│                              perception events (JSON)       │
│                                          ▼                  │
│                              [Local event publisher]        │
└──────────────────────────────────────────┼──────────────────┘
                                           │
                              WSS (events only, no video)
                                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend (cloud or on-prem)                                 │
│                                                             │
│  [WS ingest] ──► [Redis pub/sub: perception.events]         │
│                                          │                  │
│       ┌──────────────────────────────────┼─────────┐        │
│       ▼                                  ▼         ▼        │
│  [Teaching agent      [Knowledge graph     [Teacher        │
│   state machine]       per-student writer]  dashboard]     │
└─────────────────────────────────────────────────────────────┘
```

The architectural commitments that flow from this:

1. **Two-process split.** Perception worker is its own Python process, started independently. Same convention as the LiveKit agent worker. Crashes do not take down the FastAPI server.
2. **Events-only over the wire.** No frames, no embeddings, no biometrics — only `PerceptionEvent` and `ClassPerceptionState` JSON.
3. **Selective decoding.** The encoder runs continuously; the *decoder* (probe heads + event emission) only fires when the embedding meaningfully changes. This is the JEPA-style efficiency win.
4. **Agent decides.** Perception emits raw signals. The agent's policy layer decides whether to act, stash, or ignore. Perception never commands the agent.

---

## 4. The Model: V-JEPA 2

| Property | Value |
|---|---|
| Backbone | V-JEPA 2 ViT-L (Assran et al., 2025) |
| Parameters | ~304M (frozen) |
| Source | Meta FAIR — `facebookresearch/jepa` GitHub, `facebook/v-jepa2` Hugging Face |
| Input | 256² resolution, 16 frames per window |
| Window | 2 seconds @ 8 fps sliding |
| Output | Sequence of visual tokens; we average-pool to ~1024-dim per window |
| Inference (RTX 4090) | 30+ windows/sec, single camera |
| Inference (Jetson Orin AGX 64GB) | 5–10 windows/sec, single camera |

**Decision: V-JEPA 2 is frozen.** No fine-tuning the encoder. Task heads on top only. This keeps the system small, debuggable, and avoids weeks of fine-tuning research. Re-evaluate only if linear + 2-layer probes plateau below 70% accuracy on real classroom data.

---

## 5. Hardware

| Phase | Hardware | Cost | Use |
|---|---|---|---|
| Dev (single-person) | Apple M2/M3 Mac OR PC w/ RTX 3060+ | $0 (existing) | Build pipeline, single-person test |
| Pilot (1 classroom) | NVIDIA Jetson Orin AGX 64GB + 4K wide-angle USB camera | ~$2.5k | Real classroom, 20–30 students |
| Production | Same Jetson Orin per classroom (or small GPU PC) | ~$2k/room | School deployment |

Camera: any 4K USB webcam with wide-angle (Logitech Brio, Insta360 Link, similar). Mounted above the screen, pointing at students. ~$200.

Buy one Jetson Orin AGX *before* Phase 4 so edge deployment friction surfaces early.

---

## 6. Privacy Architecture (non-negotiable)

Children's video data. COPPA, FERPA, GDPR-K. If we get this wrong we lose every school.

Concrete commitments, enforced in code:

1. **Raw video never persists, never leaves the device.** Frames flow camera → ring buffer → encoder → discarded. The buffer holds at most 16 frames (2 seconds). No disk writes of frames in any environment.
2. **Only events leave the box.** Events contain: timestamp, kind, confidence, zone identifier, intensity. No facial features, no embeddings, no biometric data.
3. **No facial recognition.** Person tracking by pose + position only. Mode 1 (no tablets) means students are tracked as `student_zone_3`, never `Riya`. Mode 2 (with tablets) binds identity via tablet auth, never via face.
4. **Consent gating before activation.** School-admin enable toggle plus parental opt-in per student. If a student is not opted in, their zone is excluded from per-student events (still counted in aggregate class signals).
5. **Audit log of every event sent.** Stored locally and replicated to the backend. Schools can audit what data left the room.
6. **Hard kill switch.** Physical shutter on the camera + visible status LED + software disable.

These belong in `backend/src/feynman/perception/privacy.py` and `docs/legal/perception-privacy.md`. The privacy layer is enforced as middleware that wraps the publisher — no event ever reaches the WS without passing through it.

---

## 7. Module Structure

New module: `backend/src/feynman/perception/`. Mirrors `agent/` and `livekit/` conventions.

```
backend/src/feynman/perception/
├── __init__.py
├── CLAUDE.md                      # module docs (write once stable)
├── config.py                      # perception-specific Pydantic settings
├── models.py                      # event schemas (PerceptionEvent, ClassPerceptionState)
├── encoder/
│   ├── __init__.py
│   ├── vjepa2.py                  # V-JEPA 2 model loader + forward pass
│   ├── frame_buffer.py            # rolling 16-frame buffer at 8 fps
│   └── camera.py                  # camera capture (OpenCV / GStreamer)
├── probes/
│   ├── __init__.py
│   ├── base.py                    # LinearProbe abstract class
│   ├── confusion.py               # confusion classifier
│   ├── engagement.py              # engagement/attention classifier
│   ├── hand_raise.py              # hand-raise intent detector
│   └── trained/                   # trained probe weights (.pt)
├── tracker/
│   ├── __init__.py
│   ├── person.py                  # ByteTrack or simple IoU tracking → student_zone_id
│   └── zones.py                   # spatial zones (front-left, back-right, etc.)
├── selective_decoder.py           # "should we emit an event?" — JEPA-style trigger
├── aggregator.py                  # smoothing, debouncing, class-level aggregates
├── publisher.py                   # WebSocket client → backend
├── privacy.py                     # consent enforcement + audit log
├── worker.py                      # entrypoint (the perception process)
└── tests/
    ├── test_encoder.py
    ├── test_probes.py
    ├── test_selective_decoder.py
    ├── test_aggregator.py
    └── fixtures/
        ├── sample_videos/         # short clips with known labels
        └── sample_embeddings.pt   # cached embeddings for fast tests
```

Backend additions outside the new module:

```
backend/src/feynman/api/routers/perception.py     # WS endpoint to receive events
backend/src/feynman/agent/perception_handler.py   # agent state machine integration
backend/src/feynman/knowledge/perception_writer.py # graph updates from events
contracts/perception.schema.json                  # shared event schema
```

---

## 8. Event Contract (the most important interface)

```python
# backend/src/feynman/perception/models.py
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime

class PerceptionEvent(BaseModel):
    event_id: str
    session_id: str
    timestamp: datetime
    kind: Literal[
        "confusion_detected",
        "disengagement_detected",
        "hand_raise_intent",
        "class_energy_drop",
        "class_energy_rise",
        "comprehension_positive",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    student_zone: str | None = None       # e.g. "zone_3"; None for class-level
    duration_s: float | None = None        # how long the state has held
    intensity: float = Field(ge=0.0, le=1.0)
    metadata: dict = {}                    # signal-specific extras

class ClassPerceptionState(BaseModel):
    """Aggregated rolling state, computed every 2s."""
    session_id: str
    timestamp: datetime
    engaged_fraction: float
    confused_fraction: float
    pending_questions: int                 # raised hands count
    energy_score: float                    # smoothed 0-1
```

Two streams: discrete `PerceptionEvent` (deltas) and periodic `ClassPerceptionState` snapshots every 2s.

---

## 9. The Encoder Pipeline (concrete shape)

```python
# backend/src/feynman/perception/worker.py — sketch, not final
async def main():
    cam = Camera(device=settings.camera_device, fps=8)
    buffer = FrameBuffer(window_size=16)        # 16 frames = 2s @ 8fps
    encoder = VJEPA2Encoder.load(settings.model_path)
    tracker = PersonTracker()
    probes = {
        "confusion":  LinearProbe.load("probes/trained/confusion.pt"),
        "engagement": LinearProbe.load("probes/trained/engagement.pt"),
        "hand_raise": LinearProbe.load("probes/trained/hand_raise.pt"),
    }
    decoder = SelectiveDecoder(threshold=0.15)  # cosine distance trigger
    aggregator = SignalAggregator(window_s=5.0)
    publisher = EventPublisher(settings.backend_ws_url)

    async for frame in cam.stream():
        buffer.push(frame)
        if not buffer.full:
            continue

        # 1. Encode the 2s window
        with torch.no_grad():
            window_embedding = encoder.encode(buffer.tensor())

        # 2. Per-zone crops + per-student embeddings
        zones = tracker.detect_zones(frame)
        zone_embeddings = encoder.encode_crops(buffer.tensor(), zones)

        # 3. Apply probe heads → raw signals
        raw_signals = {
            zone_id: {name: probe(emb) for name, probe in probes.items()}
            for zone_id, emb in zone_embeddings.items()
        }

        # 4. Aggregator: smooth, debounce, threshold
        aggregator.ingest(raw_signals, t=frame.timestamp)

        # 5. Selective decoding: emit only if meaningful change
        events = decoder.maybe_emit(aggregator.state, window_embedding)
        for event in events:
            await publisher.send(event)

        # 6. Periodic class state snapshot
        if aggregator.should_snapshot():
            await publisher.send(aggregator.class_state())
```

The `SelectiveDecoder` is the JEPA-style trick: maintain a rolling-mean embedding of the recent window, only emit when the current embedding's cosine distance to the mean exceeds a threshold. Tuning this threshold is half the work — start at 0.15 and calibrate empirically against ground truth from the friends test.

---

## 10. Training the Probes (the "make it actually work" step)

V-JEPA 2 raw embeddings don't ship as signals. Probes map embeddings to our specific signals.

**Data collection (Phase 3, week 1):**
- Record 30s clips of you + 4–5 friends/family acting each signal: "look confused at the screen", "look engaged taking notes", "raise your hand", "look bored", "neutral".
- Target: 50 clips per class × 5 classes = 250 clips, ~2 hours of footage.
- Labels: `(clip_path, signal, intensity)`.
- Encode all clips with V-JEPA 2 once, cache embeddings to `tests/fixtures/sample_embeddings.pt`.

**Probe training (Phase 3, day 4):**
- Per-signal binary linear probe: `nn.Linear(1024, 1)` with BCE loss.
- Trains on cached embeddings. Runs in minutes on CPU.
- Hold out 20% for eval. Target ≥75% accuracy on each binary task.

**Per-signal binary probes** (preferred over one big classifier):
- Each gives a calibrated probability per zone per window.
- Aggregator turns probability streams into events via thresholds + duration gating.

**Escalation path if linear probes plateau:**
1. 2-layer MLP head (`Linear → ReLU → Linear`).
2. Fine-tune the V-JEPA 2 Predictor's last 2 layers on classroom-domain data.
3. Do *not* fine-tune the X-encoder unless we have thousands of real classroom clips.

---

## 11. Teaching Agent Integration

Perception events arrive on Redis pub/sub channel `perception.events`. The agent state machine subscribes through a **policy layer** that decides whether to interrupt the lesson or just update graph state.

```python
# backend/src/feynman/agent/perception_handler.py — sketch
class PerceptionPolicy:
    """Decides when perception events should affect agent behavior."""

    async def handle(self, event: PerceptionEvent, agent: TeachingAgent):
        # Always: update knowledge graph
        await self.knowledge_writer.record(event)

        # Conditional: affect lesson flow
        if event.kind == "hand_raise_intent" and event.confidence > 0.85:
            await agent.acknowledge_question(zone=event.student_zone)

        elif event.kind == "confusion_detected" and event.confidence > 0.75:
            if agent.in_critical_explanation():
                # Don't interrupt mid-sentence; stash for end of beat
                agent.stash_signal(event)
            else:
                await agent.push_branch(
                    reason="inferred_confusion",
                    target_concept=agent.current_concept,
                    student_zone=event.student_zone,
                )

        elif event.kind == "class_energy_drop":
            agent.pacing_modifier *= 0.85
            agent.queue_check_in()

        # Other events: log only, no immediate behavior change
```

Key principle: **perception events are inputs, not commands.** The agent decides how to act. Perception layer stays pure; pedagogical logic stays centralized in the agent.

For the per-student knowledge graph: every event becomes a graph update. Student `zone_3` with N confusion events on Concept C → graph state "shaky on C". The graph naturally accumulates a confusion fingerprint without a single utterance from the student.

---

## 12. Testing Strategy

Five layers, each cheap or free:

**Layer 1 — Unit tests with mock encoder.** Replace `VJEPA2Encoder` with a stub that returns canned embeddings. Test `SelectiveDecoder`, `SignalAggregator`, event emission, policy decisions. Pure Python, fast. ~80% of bugs caught here.

**Layer 2 — Recorded video integration tests.** Record 5–10 short clips with known content ("here I'm pretending to be confused for 10s"). Pipeline must produce expected events at expected timestamps. Run on every CI build via stored fixtures.

**Layer 3 — Live single-user test.** Start the perception worker on dev machine. Connect to local Feynman. Sit in front of webcam, act out scenarios, watch events flow. Print incoming events with timestamps for ground-truth comparison.

**Layer 4 — Friends-as-students (3–5 people, 30 min).** Real teaching session. One person silently logs ground truth ("Riya looked confused at 14:23"). Compute precision/recall per signal type. **This test tells us whether it's actually any good.** Acceptance: ≥70% precision and recall on each of the three core signals.

**Layer 5 — Pilot classroom.** When friends test passes, run with real students under consent. *Don't* connect events to the agent at first — log them only and have the human teacher annotate true/false post-session. Tune thresholds. Only after a passing pilot do we wire the agent's policy layer.

---

## 13. Phasing

| Phase | Duration | Outcome |
|---|---|---|
| **0. Spike** | 4 days | V-JEPA 2 loaded locally, encoder runs on webcam, embeddings printed. Verify model behavior is real on commodity hardware. |
| **1. Pipeline scaffolding** | 1 week | Module structure, frame buffer, camera capture, mock encoder, end-to-end fake events flowing to a test consumer. |
| **2. Real encoder + selective decoder** | 1 week | V-JEPA 2 encoder integrated, selective decoding firing on real scene changes (gross motion). Still no probes. |
| **3. Probe training** | 1 week | 250 clips collected, 3 binary probes trained and evaluated, weights checked in. ≥75% per-signal accuracy on held-out. |
| **4. Person tracking + zones** | 1 week | Per-zone embeddings, IoU-based tracker, zone IDs stable across frames. |
| **5. Backend integration** | 1 week | WS ingest, Redis pub/sub, `perception_handler` in agent (logging-only first), knowledge graph writes. |
| **6. Privacy + audit** | 3 days | Consent gates, audit log, kill switch. |
| **7. Friends test + tuning** | 1 week | 5-person session, precision/recall measured, thresholds tuned. **Gate:** ≥70% precision/recall before Phase 8. |
| **8. Edge deployment** | 1 week | Port to Jetson Orin, verify real-time perf, full re-test. |

**~7 weeks of focused work to a pilot-ready prototype.** This is real engineering, not a 2-week spike.

---

## 14. Risks & Open Decisions

1. **No labeled classroom video.** All training is from acted/simulated data. Real-classroom domain gap is the single biggest risk. Plan: collect real classroom video (with consent) by Phase 7 to retrain probes.
2. **Identity binding in Mode 1.** Without facial recognition, we use zone-based tracking. Students who move chairs break zones. Practical mitigation: pilot uses fixed assigned seats. Long-term: pose-based re-identification within a session.
3. **Probe accuracy floor.** If linear probes max at 60% on confusion, the agent gets noisy signals and feels weird. Mitigation: hard "don't act below confidence X" threshold + no-action mode for first pilot session.
4. **Latency budget.** Encoder + selective decoding + WS round-trip + agent reaction → can we hit "agent responds to inferred confusion within 2s"? Probably yes on Jetson, must verify.
5. **Multi-camera.** A single front-camera misses the back row. Pilot may need 2 cameras. Architecture supports it; adds tracking-fusion complexity.
6. **Probe drift across age groups.** A 9-year-old's "confused" face differs from a 16-year-old's. Probes likely need per-age-band training data eventually. Out of scope for v1; flag for Phase 8 retest.

---

## 15. Out of Scope (for this doc)

- Audio-based perception (already partially covered by LiveKit STT + agent listening).
- Generation of any visual content. (See `docs/design/08-curriculum-graph-pipeline.md` and `docs/design/10-split-board.md`.)
- Cross-classroom federation, multi-room observation, teacher-side dashboards beyond minimal event display.
- Production deployment to schools. (Pilot only; a separate doc covers GA rollout.)

---

## 16. Definition of Done (v1)

- All 9 phases complete.
- Friends test passes ≥70% precision/recall per signal.
- One pilot classroom session completed under consent, with the human teacher confirming events match observed reality at ≥70%.
- The agent's policy layer is connected and triggers a documented branch in at least one real session.
- `backend/src/feynman/perception/CLAUDE.md` written.
- `docs/legal/perception-privacy.md` written and reviewed.

When DoD met: this becomes the canonical perception layer; doc is moved from "Design" to "Shipped" and a v2 doc is opened for next-tier signals (gesture recognition, group dynamics, peer attention).
