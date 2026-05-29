# 12 — "Ask Feynman" Real-Time Doubt Pipeline: End-to-End Control Flow

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28 (every cited line read in full this pass)

> Companion to `11-precompute-playback-flow.md` (the lecture this sits on top of) and `09-end-to-end-trace.md` (high-level). This doc traces the *lecture-mode* doubt pipeline — the only "Ask Feynman" path in the active product. It is **distinct from** the parked interactive-mode doubt system (`start_doubt_branch`/`doubt_orchestrator`/`plan_doubt`); see §9 and `13-redundant-code-audit.md`.

## TL;DR

While a precomputed lecture plays (doc 11), the LiveKit worker sits **silent** in the room (`worker.py:_run_lecture_mode`). When the student taps **Ask Feynman**:

1. Frontend `pause()`s playback and publishes a `doubt_intent` (with the current `board_snapshot`) over the `doubt_signal` data-channel topic.
2. Worker captures the spoken doubt via Deepgram STT (one utterance), then runs **classify → plan → match**:
   - `DoubtClassifier` (Sonnet) → `local_clarification` / `interconnected` / `new_angle`.
   - `ResolutionPlanner` (Sonnet, structured output) → 1–6 `ResolutionBeat`s. **This is where `board_snapshot` is consumed** — it's formatted into the prompt so the LLM scopes the answer to what's actually on screen.
   - `DiagramFitMatcher` (TF-IDF stage 1 + Haiku stage 2) → fills each beat's `target_diagram_id`.
3. Worker delivers each beat: publish `doubt_beat_start` (frontend swaps diagram + applies annotations) → 150 ms grace → speak narration via Cartesia TTS on a dedicated outbound track.
4. Worker publishes a `satisfaction_prompt`. Student picks one of four options → `crystal_clear` resumes the lecture; the others re-capture / re-resolve.

The state machine, the ~40 teaching tools, the board manager, anticipation — **none of it runs here.** The lecture-mode worker uses only `agent/doubt_resolution/*`, `livekit/doubt_delivery.py`, and the STT/TTS pipeline.

```
Frontend (LectureViewer)                  Worker (_run_lecture_mode)
   │  tap Ask Feynman                         │  (silent participant)
   │  pause(); rewind audio                   │
   │  ── doubt_intent {board_snapshot} ──────▶│  _on_data_received → _handle_doubt_intent
   │ ◀──────────────────── (thinking) ────────│  capture_student_doubt (Deepgram STT)
   │ ◀── doubt_captured {text} ───────────────│
   │                                          │  LectureDoubtSession.resolve():
   │                                          │    classify_doubt        (Sonnet)
   │                                          │    plan_resolution       (Sonnet) ← board_snapshot
   │                                          │    match_diagrams_for_plan(TF-IDF + Haiku)
   │ ◀── resolution_ready {beats,ids} ────────│
   │                                          │  DoubtDelivery.deliver_resolution():
   │ ◀── doubt_beat_start {anns} ─────────────│    for each beat:
   │  applyDoubtBeat() swaps slide + anns      │      publish beat → sleep 150ms → speak (TTS track)
   │ ◀════ audio frames (feynman-voice) ══════│
   │ ◀── satisfaction_prompt {options} ───────│
   │  SatisfactionPrompt modal                │
   │  ── satisfaction_choice {option} ───────▶│  _handle_satisfaction_choice
   │ ◀── lecture_resume ──────────────────────│    crystal_clear → resume
   │  play() resumes from rewound cursor       │
```

---

## 1. Trigger — `onAskFeynman`

`frontend/src/screens/LectureViewer.tsx:258-295`:

```ts
const onAskFeynman = useCallback(() => {
  if (doubtState !== "idle") return;
  if (!room?.localParticipant) { /* warn + bail */ return; }
  pause();                                            // halts playback, rewinds audio
  setDoubtState("listening");
  armStuckTimeout(12_000, "I didn't hear anything…");  // 12s listening guard
  const intent: DoubtIntentPayload = {
    type: "doubt_intent",
    chapter_id: chapterId,
    cursor,
    topic_id: currentTopicId,
    board_snapshot: currentSnapshot,                   // last-closed-page board state
  };
  room.localParticipant.publishData(
    new TextEncoder().encode(JSON.stringify(intent)),
    { reliable: true, topic: DOUBT_TOPIC },            // DOUBT_TOPIC = "doubt_signal"
  ).catch(/* revert to idle */);
}, [...]);
```

`pause()` (doc 11 §3): aborts the playback loop, cancels in-flight audio, snapshots the slide for later restore, and rewinds the audio cursor by one so resume re-plays the interrupted fragment. `board_snapshot` is `currentSnapshot` from `useExtractionPlayback` — the last *closed* page's board state (the page-staleness from doc 11 Known Issue #3 matters here).

The button itself is `components/AskFeynmanButton.tsx` — a state machine (`idle`/`listening`/`thinking`/`error`) driven entirely by the `doubtState` prop the viewer manages.

---

## 2. Message vocabulary — both sides (verified, no mismatches)

The entire dialogue runs over one LiveKit data-channel topic: `"doubt_signal"` (frontend `LectureViewer.tsx:35`, worker `worker.py:532`). Worker publishes via `_publish_doubt` (`worker.py:803-809`); frontend receives via `useDataChannel(DOUBT_TOPIC, onDoubtMessage)` (`LectureViewer.tsx:256`).

### Worker → Frontend

| `type` | Emitted at | Payload | Frontend handler (`LectureViewer.tsx`) |
|---|---|---|---|
| `doubt_captured` | `worker.py:673` | `{text, duration_ms}` | `:171` → set `thinking`, arm 75s timeout |
| `doubt_capture_failed` | `worker.py:671` | `{reason}` | `:178` → set `idle` |
| `doubt_resolution_failed` | `worker.py:601,615` | `{reason}` | `:179` → set `idle` |
| `resolution_ready` | `worker.py:626` | `{beats:int, matched_diagram_ids}` | `:183` → re-arm 75s timeout (**content ignored**) |
| `doubt_beat_start` | `doubt_delivery.py:168` | `{beat_index, target_diagram_id, annotation_actions}` | `:192` → `applyDoubtBeat()` |
| `satisfaction_prompt` | `worker.py:655` | `{options:[{key,label,description}]}` | `:203` → show modal |
| `lecture_resume` | `worker.py:712,734` | `{}` | `:206` → clear anns, `play()` |
| `doubt_capture_ready` | `worker.py:720,727` | `{}` | `:212` → set `listening`, arm 12s |

### Frontend → Worker

| `type` | Emitted at | Payload | Worker handler (`worker.py`) |
|---|---|---|---|
| `doubt_intent` | `LectureViewer.tsx:270` | `{chapter_id, cursor, topic_id, board_snapshot}` | `:761` → `_handle_doubt_intent` |
| `satisfaction_choice` | `LectureViewer.tsx:238` | `{option}` | `:763` → `_handle_satisfaction_choice` |

**All 8 worker messages are handled; both frontend messages are handled. No type mismatches, no field renames, no orphaned cases.** This is the one part of the system where the two-sided contract is fully aligned (unlike the page-stale snapshot semantics, which are a data-currency gap, not a vocabulary gap).

The TypeScript `DoubtServerPayload` union (`LectureViewer.tsx:91-99`) is exhaustive over the 8 worker types, so the `switch` is compiler-checked.

---

## 3. STT capture — real, not a stub

`worker.py:664-689` `_capture_then_resolve`:

```python
if stt_instance is None:
    stt_instance = create_stt()                    # lazy: only pay Deepgram setup on first doubt
captured = await capture_student_doubt(ctx, stt=stt_instance)
if captured is None:
    await _publish_doubt(ctx, {"type": "doubt_capture_failed", "reason": "no_transcript"})
    return
await _publish_doubt(ctx, {"type": "doubt_captured", "text": captured.text, "duration_ms": captured.duration_ms})
snap = intent.get("board_snapshot")
await _resolve_and_deliver(doubt_text=captured.text, topic_id=intent.get("topic_id"),
                           cursor=intent.get("cursor"), different_angle=False,
                           prior_resolution_summary="",
                           board_snapshot=snap if isinstance(snap, dict) else None)
```

`capture_student_doubt` (`agent/doubt_resolution/doubt_capture.py:46-107`) is fully implemented:
- Waits up to 5 s for a remote audio track (`_wait_for_student_audio_track`, `:110-121`).
- Pumps audio frames into a Deepgram STT stream (`:64-73`).
- Returns the **first `FINAL_TRANSCRIPT`** (Deepgram endpointing fires on the student's pause, so no "submit" press needed) (`:79-86`).
- 60 s max-utterance safety timeout (`_MAX_UTTERANCE_S`, `:39`); returns `None` on timeout or no track.

The "Phase 3 scope" docstring is stale framing — the function is complete (Known Issue #8).

---

## 4. Resolution pipeline — `LectureDoubtSession.resolve`

`agent/doubt_resolution/lecture_session.py:44-134`. One `LectureDoubtSession` lives per lecture session, holding the loaded `ChapterContext`, session doubt history, and `shown_diagram_ids` (recency penalty).

```python
classification = await classify_doubt(doubt_text=..., chapter_context=...)        # Sonnet
plan = await plan_resolution(doubt_text=..., classification=...,
                             chapter_context=..., board_snapshot=board_snapshot)   # Sonnet
skip_stage2 = classification.type == DoubtType.LOCAL_CLARIFICATION
await match_diagrams_for_plan(plan=plan, ..., skip_stage2=skip_stage2)             # TF-IDF (+Haiku)
# append to prior_doubts_in_session; shown_diagram_ids.update(matched_ids)
```

### 4.1 Classifier — `doubt_classifier.py`

- Model: Claude Sonnet (`:32`), forced tool `emit_classification`, 2 attempts, fallback `local_clarification` (`:108-111`).
- Three types (`DoubtType`, `:39-44`): **`local_clarification`** (small in-place clarification), **`interconnected`** (touches related concepts), **`new_angle`** (needs a fresh framing). The `related_concept_ids` feed the matcher's topic-overlap score.
- Prompt includes the doubt, current topic snippet, chapter topic list, and prior doubts (`:163-211`).

### 4.2 Planner — `resolution_planner.py` (the sync core)

- Model: Sonnet (`:28`), forced tool `emit_resolution_plan` (input schema = `ResolutionPlan.model_json_schema()`), 2 attempts; a `ValidationError` on attempt 1 is fed back into the attempt-2 prompt (`:253-258`) so the LLM self-corrects (e.g. when it trips the banned-opener validator).
- **The planner does NOT pick a diagram** — every beat's `target_diagram_id` stays `None`; the matcher fills it (`:1-6`, `:363`).
- Output: `ResolutionPlan{ beats: 1–6 × ResolutionBeat }`. Each `ResolutionBeat` (`models.py:100-127`) = `narration_text` + `visual_intent_description` (free-text) + `annotation_actions: list[AnnotationAction]`. `narration_text` is validated against banned openers (kernel `BANNED_OPENERS` + doubt-specific `_DOUBT_EXTRA_BANNED`, `models.py:28-51`).

**`board_snapshot` consumption (confirmed, not dropped):** `_build_user_message` (`:239-371`) calls `_format_board_snapshot(board_snapshot)` (`:183-236`) and appends the result. That block renders:

```
CURRENTLY ON BOARD (what the student is staring at):
  page_index: 2
  active diagram: diagram_F_ma_intro
  visible diagram elements:
    - force-arrow (force_vector) — the applied force, F
    ...
  notebook blocks already written:
    - eq-1 (EQUATION)
  Scope the resolution to these visible elements. … do NOT invent elements…
```

Plus `_active_diagram_from_snapshot` (`:149-155`) → `_format_visual_terms` (`:158-180`) appends per-element role/semantic for the active diagram. So the snapshot directly shapes what the LLM is allowed to reference. Returns `""` when no snapshot (chapter pre-feature, or first page not yet closed) — then the planner falls back to chapter context only.

The prompt also injects: current topic (`:269-277`), adjacent topics ±1 (`:289-295`), the **prereq chain** from `walk_prereqs` (`:297-310`), available diagrams with their element roles (`:312-332`), prior doubts (`:334-338`), and — on `different_angle` — a "do not repeat" block with the prior summary (`:340-346`).

`walk_prereqs` (`prereq_walker.py:35-73`) is a pure BFS over `TopicMeta.prereq_topic_ids` (max depth 3, cycle-safe) so a student stuck on a missed prerequisite gets anchored at the real dependency, not just "the previous section."

### 4.3 Matcher — `diagram_fit_matcher.py`

Two stages, mutates `plan.beats[*].target_diagram_id` in place (`match_diagrams_for_plan`, `:268-338`), all beats matched concurrently (`asyncio.gather`, `:338`).

- **Stage 1 (deterministic, no LLM, `:155-189`):** score every chapter diagram as `0.55·text_sim + 0.35·topic_overlap − 0.10·recency_penalty` (`_STAGE1_WEIGHTS`, `:41`). `text_sim` is TF-IDF cosine between the doubt+visual-intent and the diagram's description+role/semantic surface; `topic_overlap` against `current_topic_id + related_concept_ids` (capped at 3); `recency_penalty` = 1 if already shown this session. Returns top-K=3.
- **Stage 2 (Haiku verifier, `:195-262`):** for each top-3 candidate, one Claude Haiku (`claude-haiku-4-5-20251001`, `:35`) `emit_fit_verdict` call. First candidate with `fits && confidence ≥ 0.7` (`_FIT_CONFIDENCE_THRESHOLD`, `:39`) wins.
- **`skip_stage2` escape hatch (`:305-311`):** for `local_clarification` doubts (the common case), skip Haiku and accept the top stage-1 candidate if its score `≥ 0.15`. Saves ~1–2 s of latency.
- **No match → `target_diagram_id` stays `None`** (`:333-336`): Feynman narrates without showing a new diagram. No forced reuse.

---

## 5. How board / planning / explanation / frontend stay in sync

This is the question the doc exists to answer. The sync surfaces:

1. **Board → planner:** the frontend's authoritative `currentSnapshot` (unified board state, doc 11 §6) is shipped in `doubt_intent` and formatted into the planner prompt (§4.2). The planner is *told* exactly what's on screen and instructed not to invent elements. **This works — the snapshot is consumed, not dropped.**
2. **Planner → matcher → frontend:** beats reference elements by `target_element_id`/`target_role` in `annotation_actions`; the matcher attaches a `target_diagram_id`. The frontend `applyDoubtBeat` swaps to that diagram and applies the annotations against the *same* `SlideState` the lecture uses (one source of truth, `useExtractionPlayback.ts:893-959`).
3. **Visual ↔ voice:** `DoubtDelivery.deliver_resolution` (`doubt_delivery.py:145-166`) orders it: publish `doubt_beat_start` → `sleep(150 ms)` (`_BEAT_VISUAL_GRACE_MS`, `:36`) so the frontend swaps the diagram first → then `speak(narration)`. Same fragment-boundary discipline as lecture playback, but driven by the worker per beat instead of by a manifest.
4. **Resume:** `lecture_resume` → frontend `clearDoubtAnnotations()` + `play()`, which restores the pre-doubt slide snapshot (`useExtractionPlayback.ts:806-809`) and re-plays the rewound audio fragment. Clean — no doubt state leaks into the resumed lecture.

### Where it's actually out of sync

| Gap | Evidence | Why it matters |
|---|---|---|
| **Snapshot is page-stale** | `currentSnapshot` updates only on page close (doc 11 §6) | The planner's "CURRENTLY ON BOARD" block reflects the last *closed* page, not the live page. A doubt asked mid-page, or before the first page closes (`currentSnapshot === null`), gives the LLM stale/empty board context. It still answers (chapter context remains), but loses the "scope to what they're staring at" precision the feature was built for. |
| **Follow-up doubts drop the snapshot entirely** | `worker.py:721` (`counter_doubt`), `:728` (`somewhat_cleared`) call `_capture_then_resolve({"topic_id": …})` with no `board_snapshot`; `:740-746` (`start_over`) calls `_resolve_and_deliver(...)` with no `board_snapshot=` | Only the **initial** doubt carries board context. Every re-resolution runs with `board_snapshot=None`, so the planner reverts to chapter-context-only. The student is looking at the same board, but the worker no longer knows it. |

Both are data-currency gaps, not contract gaps. Fixing the first needs a live snapshot at intent time (the frontend has the data; it would need to compute a current-page snapshot rather than reuse the last-closed one). Fixing the second is a small worker change: thread the original `board_snapshot` through the satisfaction handlers (or have the frontend re-send it on `doubt_capture_ready`).

---

## 6. Delivery + annotation parity

`doubt_beat_start` payload (`doubt_delivery.py:168-179`):

```python
{ "type": "doubt_beat_start", "beat_index": index,
  "target_diagram_id": beat.target_diagram_id,
  "annotation_actions": [json.loads(a.model_dump_json()) for a in beat.annotation_actions] }
```

The four `AnnotationAction` subtypes (`models.py:56-94`) map **exactly** onto the frontend `DoubtBeatAnnotation` union (`useExtractionPlayback.ts:1005-1028`) and are all handled in `applyDoubtBeat` (`:932-955`):

| Backend (`models.py`) | Fields | Frontend `applyDoubtBeat` |
|---|---|---|
| `FocusAction` | `target_element_id?`, `target_role?`, `text?` | `:934` → `setFocusedTarget` |
| `PointAtAction` | `element_id`, `from_side` | `:941` → `appendPointer` |
| `TraceAction` | `element_id`, `duration_ms` | `:944` → `appendTrace` |
| `MarkPointAction` | `x`, `y`, `kind`, `label` | `:947` → `appendMarkPoint` |

These are the **same setters the lecture playback uses** for `focus`/`point_at`/`trace`/`mark_point` events (doc 11 §4), so a doubt annotation renders identically to a precomputed one. The `applyDoubtBeat` switch has no `default` case — unknown future action types would be silently dropped (Known Issue #3), but all current types are covered.

---

## 7. Satisfaction loop (all four wired)

After the last beat, the worker publishes `satisfaction_prompt` with `_SATISFACTION_OPTIONS` (`worker.py:779-800`). Frontend shows `components/SatisfactionPrompt.tsx`; the button passes `option.key` back as `satisfaction_choice` (`LectureViewer.tsx:238`). Worker `_handle_satisfaction_choice` (`worker.py:704-749`):

| Option key | Worker behavior |
|---|---|
| `crystal_clear` | Speak "Picking up where we left off." → publish `lecture_resume` (`:708-717`). |
| `counter_doubt` | Publish `doubt_capture_ready` → `_capture_then_resolve` for a follow-up (`:719-722`). *(no board_snapshot — §5)* |
| `somewhat_cleared` | Speak a clarifying nudge → `doubt_capture_ready` → re-capture (`:724-729`). *(no board_snapshot)* |
| `start_over` | Pop the just-rejected doubt from history, re-resolve the **same** doubt with `different_angle=True` + `prior_resolution_summary` (`:731-747`). *(no board_snapshot)* |

`start_over` guards the empty-history case (`:732-735`) so the `.pop()` (`:739`) never throws. Frontend holds the button at `thinking` after a choice until the worker drives the next state (`LectureViewer.tsx:251`).

---

## 8. Resume path

`lecture_resume` handler (`LectureViewer.tsx:206-211`):

```ts
case "lecture_resume":
  setSatisfactionOptions(null);
  clearDoubtAnnotations();     // resetSlideFocus → clears focus + traces/markPoints/pointers/marginNotes
  setDoubtState("idle");
  void play();                  // restores pre-pause slide snapshot, re-plays rewound audio fragment
  return;
```

`play()` (doc 11 §3, `useExtractionPlayback.ts:806-809`) restores `slideSnapshotRef` (captured at `pause()`), so the doubt's diagram + annotations vanish and the lecture's own slide returns. The audio cursor was rewound one fragment at pause, so narration resumes from the start of the interrupted sentence — intentional "let me back up a beat" behavior. No doubt state leaks.

---

## 9. Relationship to the parked interactive doubt system

There are **two** doubt mechanisms in the repo; only the one above is live:

| | Lecture-mode "Ask Feynman" (this doc) | Interactive-mode doubt branching (parked) |
|---|---|---|
| Entry | `worker.py:_run_lecture_mode` (lecture playback session) | `worker.py` interactive entrypoint + `FeynmanAgent` |
| Trigger | Student taps button → `doubt_intent` | LLM calls `start_doubt_branch` tool mid-teaching |
| Planning | `agent/doubt_resolution/resolution_planner.plan_resolution` | `feynman_teaching_kernel.plan_doubt` |
| State | `LectureDoubtSession` (in-memory, no stack) | `TeachingStateMachine.push_branch` + `DoubtOrchestrator` + `ReturnAnchor` + checklist |
| Delivery | `DoubtDelivery` (TTS-only track) | Full `AgentSession` STT→LLM→TTS loop + ~40 tools |
| Status | **Active** | **Parked** (see `13-redundant-code-audit.md` Group 2) |

If you go looking for "the doubt code," `doubt_orchestrator.py` / `plan_doubt` / `start_doubt_branch` are the *wrong* files for the current product — they belong to the interactive path. The active doubt pipeline is entirely under `agent/doubt_resolution/` + `livekit/doubt_delivery.py`.

---

## 10. Known issues / gaps (verified against full reads)

| # | Issue | Evidence | Severity |
|---|---|---|---|
| 1 | **Follow-up doubts drop `board_snapshot`** | `worker.py:721,728` pass `{"topic_id":…}` (no snapshot); `:740-746` omits `board_snapshot=` | **MEDIUM** — re-resolutions lose the "what's on screen" context the feature provides on the first doubt. |
| 2 | **`board_snapshot` is page-stale** | `currentSnapshot` updates only on page close (doc 11 §6); `null` before first page close | **MEDIUM** — even the first doubt's board context lags the live page. |
| 3 | **`applyDoubtBeat` has no `default` case** | `useExtractionPlayback.ts:932-955` | **LOW** — unknown future `AnnotationAction` types silently dropped; all 4 current types handled. |
| 4 | **`skip_stage2` floor `0.15` is permissive** | `diagram_fit_matcher.py:305-311` | **LOW** — for `local_clarification`, a weakly-related diagram (stage-1 ≥ 0.15) can be shown without Haiku verification. Needs empirical tuning. |
| 5 | **No-match narrate-without-diagram is undocumented behavior** | `diagram_fit_matcher.py:333-336` → `target_diagram_id=None`; `applyDoubtBeat` only swaps if truthy | **LOW** — correct by design, but silent; a beat may reference an element on a diagram that isn't shown if the planner named one the matcher rejected. |
| 6 | **Listening-timeout vs capture-timeout mismatch** | frontend 12 s (`LectureViewer.tsx:266`) vs STT 60 s utterance / 5 s track-wait (`doubt_capture.py:39-43`) | **LOW** — silent student: frontend shows "error" at 12 s while the worker keeps capturing; a late `doubt_captured` pulls the UI back to `thinking` (recovers, but a brief wrong state). |
| 7 | **`cursor` is vestigial for scoping** | sent in `doubt_intent`, passed to `resolve` (`lecture_session.py:49`) but only logged (`:77,90`) | **INFO** — board_snapshot does the scoping; `cursor` only drives the frontend's pause-rewind. |
| 8 | **`resolution_ready` content ignored** | worker sends `{beats, matched_diagram_ids}` (`worker.py:626`); frontend only re-arms timeout (`:183-191`) | **INFO** — not a bug; unused signal richness. |
| 9 | **Stale "Phase 3 stub" docstrings** | `doubt_capture.py:10-13`, `doubt_classifier.py:1-12`, `worker.py:540-546` | **INFO** — code is fully Phase 4/5; docstrings rot only. |

**What's solid:** the message vocabulary is fully aligned both ways; `board_snapshot` is genuinely consumed by the planner; all four `AnnotationAction` types render identically to lecture annotations; the satisfaction loop is complete; resume cleanly restores pre-doubt state. The real weaknesses are *board-context currency* (issues 1–2), not contract or wiring bugs.

---

## 11. Reading order for a new engineer

1. This doc, then `12`'s sibling `11-precompute-playback-flow.md` (the lecture this rides on).
2. `worker.py:_run_lecture_mode` (`:535-776`) — the silent-worker loop + handlers.
3. `agent/doubt_resolution/lecture_session.py` — the resolve orchestration.
4. `resolution_planner.py:_format_board_snapshot` (`:183-236`) — how board state enters the prompt.
5. `diagram_fit_matcher.py` — the two-stage retrieval.
6. `livekit/doubt_delivery.py` — beat delivery + TTS track.
7. `LectureViewer.tsx:onDoubtMessage` + `useExtractionPlayback.ts:applyDoubtBeat` — the frontend side.
8. For the parked alternative, contrast with `03-teaching-state-machine.md` §10.
