# 13 — Aanya Demo v0 Build List

> File-level changes to ship the Aanya demo in 5–7 days. This is the engineering companion to `12-aanya-demo-v0.md`. An engineer should be able to start work from this doc without asking design questions.

**Status**: Build list (locked after audit)
**Date**: 2026-05-10
**Depends on**: `docs/design/12-aanya-demo-v0.md`, `docs/design/10-split-board.md`
**Defines**: file-level changes for the v0 demo build sprint.

---

## 1. Executive Summary

Five build items, **6–8 days realistic** (revised after the doubt-real-not-scripted decision added 1 day on Item 2). One mandatory 30-minute spike before committing the longest item.

| # | Item | Verified estimate | Risk |
|---|---|---|---|
| 1 | In-memory `LessonPlan` loader + demo-mode flag | 0.5 day | Low |
| 2 | Pre-cached DiagramSpec library (7 diagrams: 3 main + 4 anticipated doubts) | 3–4 days | **Critical path** — visual iteration on a larger library |
| 3 | Verbatim script binding (main beats only — beat 4 doubt is live) | 0.5 day | Low — model may paraphrase bound beats, mitigate with temp=0 |
| 4 | Frontend `/dev/aanya-demo` route | 0.25 day | Low |
| 5 | `wait_for_user_speech` primitive | 0.5–1 day | **Spike first** — LiveKit SDK STT control unknown |

**Critical path**: Item 2's visual iteration on the expanded 7-diagram library. Front-load the main diagram (beat 1) on day 2; once visual language is calibrated, the other 6 (2 main + 4 doubt) should converge faster. Schedule a half-day buffer for re-runs.

**Mandatory spike**: 30 minutes on day 1 to read LiveKit Agents SDK source for `AgentSession` STT exposure (item 5). The spike outcome dictates whether item 5 is a half-day (clean SDK API) or a full day (forced fallback to polled-listen).

**Total realistic budget**: 6 days of focused engineering + 1–2 days of visual/script iteration = 6–8 day sprint.

---

## 2. Item 1 — In-memory `LessonPlan` loader (0.5 day)

### What

Add a sibling to `lesson_plan_from_curriculum` that builds a `LessonPlan` from in-memory `ConceptNode` objects. Bypasses Neo4j entirely. Demo lessons are hand-authored Python data, not curriculum-derived.

### Files

| File | Change |
|---|---|
| `backend/src/feynman/agent/lesson_plan.py` | Add `lesson_plan_in_memory(concepts: list[ConceptNode], lesson_title: str = "") -> LessonPlan`. Sibling to `lesson_plan_from_curriculum` (lines 238–317). 10–20 lines total. |
| `backend/src/feynman/livekit/worker.py:118–127` | Add demo-mode branch in `FeynmanAgent.on_enter()`. If `settings.demo_mode == "aanya_v0"`: skip `load_curriculum()`, call `lesson_plan_in_memory(get_aanya_concepts(), "Trigonometry — Ladder Problem — IGCSE 0580")` instead. Else current path. |
| `backend/src/feynman/config.py` | Add `demo_mode: str = ""` Pydantic Setting. Env: `FEYNMAN_DEMO_MODE`. |
| `backend/src/feynman/agent/aanya_demo_concepts.py` (NEW) | Hand-authored ConceptNode data for the demo lesson. ~50 lines. Three concepts: `frame_right_triangle_and_sides`, `apply_trig_ratios`, `confirm_with_practice`. Each with title, description, key_points, visual_suggestions, estimated_minutes. |

### `ConceptNode` minimum fields (verified, lesson_plan.py:28–44)

```python
ConceptNode(
    title="Right Triangle — Naming the Sides",
    description="Establish the three named sides of a right triangle (opposite, adjacent, hypotenuse) relative to a given non-right angle.",
    key_points=[
        "Opposite — across from the angle",
        "Adjacent — next to the angle (not the hypotenuse)",
        "Hypotenuse — opposite the right angle (always the longest)",
    ],
    visual_suggestions=["ladder_problem_main"],
    estimated_minutes=1.5,
)
```

### Test

```python
# backend/tests/agent/test_lesson_plan.py
def test_lesson_plan_in_memory_builds_valid_plan():
    concepts = get_aanya_concepts()
    plan = lesson_plan_in_memory(concepts, "Trigonometry — Ladder Problem")
    assert len(plan.concepts) == 3
    assert plan.concepts[0].title == "Right Triangle — Naming the Sides"
    assert all(c.key_points for c in plan.concepts)
```

### Risk

None notable. The data model is intentionally flat; no graph traversal needed. The injection point at `worker.py:118–127` is clean.

---

## 3. Item 2 — Pre-cached DiagramSpec library (3–4 days, critical path)

### What

Pre-generate **7** `DiagramSpec` JSON files into a likely-doubts library:

**Main lesson (3):**
- `ladder_problem_main.json` — beat 1 ladder against wall
- `trig_ratio_invariance.json` — fallback for the canonical doubt
- `flagpole_confirmation.json` — beat 8 confirmation problem

**Anticipated doubts (4) — for the real-time doubt branch:**
- `doubt_why_sin_opp_hyp.json` — three same-shape, different-size right triangles with opp/hyp computed (~0.866 each)
- `doubt_which_side_is_opposite.json` — labeled-sides reference: opp/adj/hyp clearly marked relative to the angle
- `doubt_sin_vs_cos.json` — side-comparison view: which sides each ratio uses
- `doubt_why_ratios.json` — scale-invariance demonstration: same-angle triangles, ratio is constant

Add disk-load capability to `AnticipationEngine`. Wire into session start so cache is hot before lesson begins. The runtime LLM picks which doubt diagram to render via `anticipation.match()` Jaccard similarity against the asked question. **Cache-hit on the main 3 is non-negotiable** (a 5–15s loader during the planned beats kills the magic). Cache-hit on the doubt 4 is the *target* but graceful degradation is acceptable for unanticipated doubts (DraftingLoader + bridging voice + live gen).

### Sub-items

#### 2a — Generation script (0.5 day)

| File | Change |
|---|---|
| `scripts/generate_aanya_demo_diagrams.py` (NEW) | Standalone Python script. Loads **7** prompts from `aanya_demo_prompts.py` (3 main + 4 doubt library). Calls `DiagramAgent.generate_sync(prompt)` (`design_agent/backend/agent.py:82–86`) or `await design_bridge.generate_design_diagram(prompt, model="sonnet")` (`design_bridge.py:244`). Saves output to `data/aanya_demo/diagrams/{slug}.json`. ~120 lines. |
| `data/aanya_demo/diagrams/` (NEW DIR) | Houses generated specs: `ladder_problem_main.json`, `trig_ratio_invariance.json`, `flagpole_confirmation.json`, `doubt_why_sin_opp_hyp.json`, `doubt_which_side_is_opposite.json`, `doubt_sin_vs_cos.json`, `doubt_why_ratios.json`. |
| `backend/src/feynman/agent/aanya_demo_prompts.py` (NEW) | Hand-authored design prompts for the 7 diagrams (see demo spec §3 beats 1, 4, 8 for the main 3; §4 for the doubt library 4). Each prompt is paired with its `(concept_index, suggestion_index)` slot for `prompt_to_concept` mapping. Single source for both generation script and runtime cache-key mapping. |

Pattern: `design_agent/test_agent.py` is an existing standalone CLI entry. Use that as the template.

#### 2b — `AnticipationEngine.load_from_disk()` (1 day)

| File | Change |
|---|---|
| `backend/src/feynman/agent/anticipation.py` | New method `load_from_disk(diagram_dir: Path, prompt_to_concept: dict[str, tuple[int, int]]) -> int`. Reads each JSON file, populates `_cache: dict[tuple[int, int], dict]` and `_prompts: dict[(concept_idx, suggestion_idx), str]` matching internal structure (anticipation.py:192). Returns count loaded. ~80–100 lines. |
| Same file | Optionally add `_loaded_from_disk: bool` flag so `match()` can short-circuit Jaccard search if disk cache is authoritative. |

The `prompt_to_concept` mapping is hand-authored: which prompt corresponds to which `(concept_index, suggestion_index)` slot in the `LessonPlan`. Matches the in-memory ConceptNodes' `visual_suggestions` order.

#### 2c — Hook into session start (2 hours)

| File | Change |
|---|---|
| `backend/src/feynman/agent/teaching_context.py:44–45` | In `__post_init__()`: if `settings.demo_mode == "aanya_v0"`, after `AnticipationEngine` is instantiated, call `self.anticipation.load_from_disk(settings.demo_diagram_dir, get_aanya_prompt_mapping())`. Log how many entries loaded. |
| `backend/src/feynman/livekit/worker.py:154–160` | Verify load happens *before* the `warm()` call. Demo mode skips `warm()` entirely (we don't need to generate anything live; cache is fully pre-populated). |
| `backend/src/feynman/config.py` | Add `demo_diagram_dir: Path = Path("data/aanya_demo/diagrams")` setting. |

#### 2d — Visual quality iteration (1.5–2 days, the unknown)

Process:
1. Generate diagram 1 (ladder problem main view) via script.
2. Open `#/dev/aanya-demo` (item 4 must be done first), run session, watch the diagram render with stroke-reveal.
3. Refine prompt (color, layout, label clarity, scale). Regenerate.
4. Repeat 1–3× until landed.
5. Apply learned prompt patterns (color tokens, structural hints) to the other 2 main diagrams (trig ratio invariance, flagpole). Faster convergence expected.
6. Apply same patterns to the 4 doubt-library diagrams. Each should require minimal iteration (≤1 round) since the visual language is already calibrated.
7. Generate, view, refine each. Run the demo end-to-end with several different ad-hoc doubt questions to verify the matching layer picks reasonable diagrams for each.

Front-load diagram 1 — 60% of the iteration cost concentrates there. Diagrams 2–7 should each converge in ≤1 round once the visual language is calibrated. The doubt-library diagrams are simpler structurally (often just 1–2 reference triangles with annotations) so they should be cheaper.

### Test

```python
# backend/tests/agent/test_anticipation_disk_load.py
async def test_load_from_disk_populates_cache(tmp_path):
    spec_path = tmp_path / "test_diagram.json"
    spec_path.write_text(json.dumps({"elements": [...]}))
    engine = AnticipationEngine(...)
    count = engine.load_from_disk(tmp_path, {"test prompt": (0, 0)})
    assert count == 1
    match = await engine.match("test prompt", concept_index=0)
    assert match is not None
    assert "_generated_at" in match  # or whatever cache marker
```

Visual test: manual review at `#/dev/aanya-demo` once item 4 lands. Watch full lesson, confirm all 3 diagrams cache-hit (no `slide_pending` logs).

### Risk

**Visual iteration may exceed 2-3 prompt rounds per diagram.** Mitigation: schedule a 0.5-day buffer in days 6–7 for re-runs. If after 2 days a single diagram remains unsatisfying: fall back to a hand-authored `DiagramSpec` JSON written by hand using the schema reference (`design_agent/backend/schema.py:219–230`). The cache loader doesn't care whether the JSON came from an LLM or a human — it loads either.

---

## 4. Item 3 — Verbatim script binding (0.5 day)

### What

Make the LLM say the script from demo spec §3 verbatim **for the AI-led main lesson beats only** (beats 1, 2, 3, 5, 6, 7). Beat 4 (doubt) is real-time live LLM output — only its bridging acknowledgment ("Beautiful question — let me show you.") and its return cue ("OK — back to your ladder. Let's use what we just wrote down.") are bound. Beat 8 (kid solves) is listen-mode, no voice script.

Add a `target_voice_script` field to `TeachingBeat`, surface it in the prompt, instruct the LLM to follow it word-for-word *when set*; otherwise improvise per the beat's behavioral guidance.

### Files

| File | Change |
|---|---|
| `backend/src/feynman/agent/concept_planner.py:70–96` | Add field to `TeachingBeat`: `target_voice_script: str = Field(default="", description="If set, exact words the agent must say verbatim. Empty = improvise.")`. |
| `backend/src/feynman/agent/concept_planner.py:646–720` | Modify `format_plan_for_prompt()`: when a beat has non-empty `target_voice_script`, surface it inline with strong language. Example: `"BEAT 4 — Doubt Branch (verbatim): \"Great question — actually that's the most important thing...\""`. When empty, fall back to `speech_guidance`. |
| `backend/src/feynman/agent/prompts.py:16–37` | Add demo-mode addendum to `TEACHING_SYSTEM_PROMPT`: `"When a beat has target_voice_script set, follow it word-for-word. The phrasing and pacing are load-bearing."`. Conditional on `demo_mode == "aanya_v0"` if we want to keep production prompt clean. |
| `backend/src/feynman/agent/aanya_demo_concepts.py` | Hand-author the bound beat scripts from demo spec §3 — populated as `target_voice_script` on beats 1, 2, 3, 5, 6, 7. Beat 4 has only the two short bound lines (bridging + return); the long doubt explanation has empty `target_voice_script` and behavioral-guidance only. Beat 8 has empty `target_voice_script`. |

### Test

```python
# backend/tests/agent/test_verbatim_script.py
def test_format_plan_surfaces_verbatim_script():
    beat = TeachingBeat(
        beat_type="explain",
        speech_guidance="explain SOH CAH TOA",
        target_voice_script="Sine is opposite over hypotenuse — SOH. Cosine is adjacent over hypotenuse — CAH. Tangent is opposite over adjacent — TOA.",
        ...
    )
    plan = ConceptTeachingPlan(beats=[beat], ...)
    prompt = format_plan_for_prompt(plan)
    assert "Sine is opposite over hypotenuse — SOH." in prompt
    assert "verbatim" in prompt.lower()
```

Manual: run a session, verify TTS speaks scripted words (use cheap acoustic match — does the kid hear *exactly* what's in §3 of demo spec?). Set `temperature=0` for the demo agent's LLM config.

### Risk

LLM may still paraphrase. Mitigations in priority order:
1. Set LLM temperature to 0.
2. Make the prompt *very* directive: "Do not paraphrase, do not rewrite, say exactly the words in target_voice_script."
3. If still drifting, swap to a deterministic Sonnet config or use beam search.
4. Worst case: bypass the LLM for verbatim beats — call TTS directly with the scripted text. (Not recommended; preserves the agent's cognitive model.)

---

## 5. Item 4 — Frontend `/dev/aanya-demo` route (0.25 day, ~1.5 hours)

### What

A dev-only route that loads the demo lesson with one click. Hardcoded textarea pre-filled with the past paper question, submit button initiates a session.

### Files

| File | Change |
|---|---|
| `frontend/src/App.tsx:22–28` | Add hash route check: `if (hash === "#/dev/aanya-demo") return <AanyaDemoRoute />;`. Pattern matches existing `#/dev/split-board`. |
| `frontend/src/screens/AanyaDemoRoute.tsx` (NEW) | ~80 LOC. Pre-filled `<textarea>` with question text from demo spec §2. Submit button. On submit: calls `useSession()` (`hooks/useSession.ts`) with `{topic: "Trigonometry - Ladder Problem - IGCSE 0580 Paper 4", subject: "math", grade_level: "IGCSE Year 9"}`. On success: wraps `ClassroomScreen` in `RoomProvider` (reuse `MainApp` pattern from App.tsx:36–41). On loading: spinner. On error: retry button. |

The backend already accepts `topic/subject/grade_level` in the `createSession()` API (`lib/api.ts:26–36`); no backend wiring needed beyond reading `demo_mode` from settings (item 1).

### Test

```typescript
// frontend/src/screens/AanyaDemoRoute.test.tsx
it("renders question textarea pre-filled", () => {
    render(<AanyaDemoRoute />);
    const textarea = screen.getByRole("textbox");
    expect(textarea).toHaveValue(expect.stringContaining("ladder of length 10 m"));
});

it("initiates session on submit", async () => {
    render(<AanyaDemoRoute />);
    fireEvent.click(screen.getByRole("button", { name: /start/i }));
    await waitFor(() => expect(mockCreateSession).toHaveBeenCalled());
});
```

Manual: open `http://localhost:5173/#/dev/aanya-demo` locally, click submit, verify session starts and lesson begins.

### Risk

None notable. Pattern is well-established (split-board precedent).

---

## 6. Item 5 — `wait_for_user_speech` primitive (0.5–1 day; spike first)

### What

Beat 8 of the demo (kid solves it) requires the agent to enter "listen mode": pause TTS, wait for the kid to speak (with timeout), resume on speech or timeout. Today there's `wait_for_playout()` for TTS pacing, but no timed-listen primitive.

### MANDATORY 30-MIN SPIKE (do first, before any code)

Read LiveKit Agents SDK source for `AgentSession`. Look for:
- Public hook to access STT stream / next utterance event.
- Existing primitives like `session.aread()`, `session.next_user_input()`, etc.
- Whether the SDK exposes `_asr_manager` or equivalent publicly or if it's internal.

**Spike outcomes:**
- **Clean SDK exposure** → 0.5-day implementation. Wrap the SDK primitive in a tool.
- **No clean exposure** → 1-day implementation via fallback (see below).

Document spike outcome in this doc's decision log before coding.

### Files (assuming clean SDK exposure)

| File | Change |
|---|---|
| `backend/src/feynman/agent/tools.py` | New tool `listen_for_user_input(timeout_s: int = 8) -> dict`. Body: `await ctx.wait_for_playout()` (existing, tools.py:223), publish `set_listen_mode(active=True)` visual instruction, await STT primitive with `asyncio.wait_for(... , timeout=timeout_s)`, publish `set_listen_mode(active=False)`. Return `{"status": "speech"|"no_speech", "transcript": str}`. |
| `backend/src/feynman/visuals/schemas.py` | Add `SetListenModeInstruction` Pydantic model. Panel: meta-overlay (not slide or notebook). Fields: `active: bool`. |
| `backend/src/feynman/livekit/worker.py:270–350` | If SDK requires it: expose STT event stream to `TeachingContext` so the tool can await it. If SDK provides via `ctx`: pass-through, no changes needed. |
| `frontend/src/engine/whiteboard/listen-mode/ListenIndicator.tsx` (NEW) | Small mic icon overlay with subtle pulse. Shown when `set_listen_mode(active=True)` instruction received. Position: bottom-center of board, low-key. ~40 LOC. |
| `frontend/src/engine/whiteboard/...store.ts` | Wire `SetListenModeInstruction` into the store; ListenIndicator subscribes to state. |

### Fallback (if SDK does not expose STT cleanly)

Polled approach: agent runs short LLM turns every 2s checking for non-empty user transcript. Less elegant, still works. Same tool signature, different implementation.

### Test

```python
# backend/tests/agent/test_listen_tool.py
async def test_listen_returns_speech_on_input(mock_stt):
    mock_stt.simulate_utterance("the flagpole is 4 metres", delay=0.5)
    result = await listen_for_user_input(timeout_s=2.0)
    assert result["status"] == "speech"
    assert "4" in result["transcript"]

async def test_listen_returns_no_speech_on_timeout(mock_stt):
    # No utterance simulated
    result = await listen_for_user_input(timeout_s=1.0)
    assert result["status"] == "no_speech"
    assert result["transcript"] == ""
```

Manual: dev session, agent reaches beat 8, listen indicator appears, speak "the flagpole is 4 metres", agent receives transcript and continues.

### Risk

**SDK exposure is the unknown.** Spike de-risks before commit. Worst case: polled fallback adds a half-day. Add to buffer.

---

## 7. Build sequencing (recommended day-by-day)

| Day | Tasks | Outcome |
|---|---|---|
| **1** | Item 1 (lesson plan, 0.5d). Item 4 (frontend route, 0.25d). Item 5 SPIKE (30 min). | Demo route loads in browser; `lesson_plan_in_memory` works; spike outcome documented. |
| **2** | Item 3 (script binding, 0.5d). Item 2a (generation script for 7 prompts, 0.5d). | Demo lesson runs end-to-end with placeholder diagrams; bound voice scripts visible in TTS output for main beats; beat 4 prompt logic in place (calls real `start_doubt_branch`). |
| **3** | Item 2b (anticipation `load_from_disk`, 1d). | Cache loads from disk; one diagram passes integration test. |
| **4** | Item 2c (session-start hook, 2h). Item 2d start: visual iteration on main diagram 1 (ladder). | Ladder diagram lands cleanly. |
| **5** | Item 2d continue: main diagrams 2 + 3 (trig ratio invariance, flagpole) visual iteration. Item 5 implementation per spike outcome. | All 3 main diagrams cache-hit. Listen mode wired. |
| **6** | Item 2d: 4 doubt-library diagrams generated and refined (≤1 iteration round each — visual language already calibrated). | All 7 diagrams cache-hit. Real doubt handling test: 3+ ad-hoc questions branch correctly. |
| **7** | Acceptance test pass-through. Latency tuning. Script timing iteration. | Full demo runs in <8 min wall-clock, three magic beats land. |
| **8** | Buffer day. Re-run iteration. Pre-validation: 2–3 internal viewers say "whoa" unprompted. | Demo ready for moms validation. |

**Total: 8-day sprint with 1-day buffer.** If days 1–6 finish on schedule, days 7–8 are safety buffer plus polish. The doubt-real-not-scripted decision added day 6 (the doubt library diagrams).

---

## 8. Acceptance criteria (gate to moms validation)

From demo spec §8, restated for build:

1. All 5 items implemented and tested (unit + integration).
2. End-to-end demo runs at `#/dev/aanya-demo` in **<8 minutes wall-clock**.
3. **All three magic beats land**:
   - **Beat A**: each of the 3 main diagrams visible within 800ms of voice cue (cache-hit verified in logs).
   - **Beat B (real doubt handling)**: 3+ different testers each ask a different ad-hoc question during the doubt window. All branch correctly. All produce meaningful, non-generic responses tied to the actual question. Cache-hit rate ≥3/4 across the 4 most-likely doubts. Cache-miss path (DraftingLoader + live gen) gracefully degrades within 8s. Return-to-parent is clean every time. **Theater test passed: no scripted student utterances.**
   - **Beat C**: kid solves the confirmation problem; AI does not deliver the answer.
4. **No latency stalls >2s** where voice is silent waiting on visual on the cache-hit path; ≤8s on cache-miss with bridging voice covering.
5. **3+ of 5 internal viewers** say "whoa" unprompted at one of the magic beats.
6. Viewer can predict the next answer ("if the wire was on a 45° angle instead of 30°, how would you find the flagpole height?") without AI's help → "still sine, h = 8 × sin(45°)".

If any criterion fails: stop, fix, re-test. Do not proceed to mom validation.

---

## 9. Risks consolidated

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Visual iteration on diagrams 2+3 takes >1 round each | Medium | +1 day | Day 7 buffer; hand-authored fallback if any diagram still failing |
| LiveKit SDK doesn't expose STT cleanly | Medium | +0.5 day | Day 1 spike; polled-listen fallback |
| LLM paraphrases verbatim script | Low–Medium | Demo doesn't read magical | Temperature=0; prompt directive language; bypass to direct TTS as last resort |
| Demo session not re-runnable cleanly across moms | Low | Slows validation | Add `/api/sessions/{id}/reset` if missing; document reset flow for moms test |
| Cache pre-load doesn't actually fire before first diagram call | Low | Demo dies on beat 1 | Integration test verifies cache-hit on first `match()`; log assertions |

---

## 10. Out of scope (for v0 demo build)

- Auth, payments, onboarding, parent dashboard
- Multi-question support, subject switcher
- Mobile / tablet experience
- Production session management, billing, analytics
- Indian English TTS voice configuration (defer to post-acceptance, before moms test)
- Camera-based perception (parked permanently per consumer pivot)
- Curriculum graph pipeline beyond the 1 demo lesson

---

## 11. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-05-10 | Total estimate revised from 5 → 5–7 days | Audit confirmed item 2 visual iteration is the unknown; need buffer |
| 2026-05-10 | **Doubt branch is real, not scripted.** Pre-cache library expanded to 7 diagrams (3 main + 4 anticipated doubts); LLM matches via Jaccard similarity at runtime; 25–35s explanation is live LLM output. Sprint extended 5–7 → 6–8 days. | The whole pitch is "AI handles whatever your kid asks." Scripted doubt undermines that — moms catch on. Anticipation pre-caching is real (rehearsed answers for common questions), not theater. |
| 2026-05-10 | Item 5 spike is mandatory before commit | LiveKit SDK STT exposure unknown; outcome forks the implementation by 0.5 day |
| 2026-05-10 | Demo concepts hand-authored, not curriculum-derived | Bypass Neo4j entirely for v0; cleanest fastest path |
| 2026-05-10 | Three pre-cached DiagramSpecs is non-negotiable | Cache-hit is the only way to hit <800ms latency for the magic-beat A |
| 2026-05-10 | Hand-authored DiagramSpec JSON is acceptable fallback | Cache loader doesn't care about source; if LLM iteration fails, hand-write |
| 2026-05-10 | Visual iteration front-loads on diagram 1 | Calibration of visual language transfers to diagrams 2+3 |
| 2026-05-10 | LLM temperature=0 for demo | Reduce paraphrase risk on verbatim script |
| 2026-05-10 (TODO) | Item 5 spike outcome | (Filled in after spike runs day 1) |

---

## 12. Next artifacts

After this build list is approved and the sprint runs:

1. **Day 1 spike report**: outcome of LiveKit SDK STT investigation, item 5 path commitment.
2. **Day 4 visual iteration log**: which diagram prompts converged in what number of rounds, learned visual language patterns. Useful for v1 when we generate dozens more.
3. **Day 7 acceptance test report**: pass/fail per criterion, internal viewer reactions, gate decision (proceed to moms test or iterate).
4. **Mom validation test plan**: separate doc, post-acceptance. Recruitment, session protocol, scoring rubric.
