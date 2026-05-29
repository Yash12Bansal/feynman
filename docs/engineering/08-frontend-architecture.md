# 08 — Frontend Architecture (`frontend/`)

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

## TL;DR

The frontend is a **React 19 + TypeScript + Vite** app rendered on the classroom display. It has two production modes:

1. **Live agent mode** — student joins a LiveKit room, the worker drives audio + visuals in real time. UI: `ClassroomScreen` → `WhiteboardScene` or `SplitBoard`.
2. **Lecture playback mode** — student picks a precomputed chapter, the frontend walks the manifest and plays back audio + diagrams + notebook. UI: `LectureHomeScreen` → `LectureViewer`. The agent stays silent in the room until the student taps "Ask Feynman."

The product front door at `/` (no hash) is the lecture picker. The legacy live-teacher path is gated behind `#/dev/live-teacher`. Routing is hash-based; no React Router.

```
                ┌─────────────────────────────────────────────────┐
                │  /  → LectureHomeScreen (picks chapter)         │
                │       ?lecture=<chapter_id>                      │
                │            ↓                                     │
                │       MainApp creates session → LectureViewer    │
                │                                                  │
                │  #/dev/live-teacher → MainApp (live agent mode)  │
                │  #/dev → DevHarness                             │
                │  #/dev/split-board → SplitBoardPrototype        │
                │  #/diagram_generation_test → diagram lab        │
                │  #/lecture-preview → LecturePreviewScreen       │
                └─────────────────────────────────────────────────┘
                                       │
                                       ▼
                ┌─────────────────────────────────────────────────┐
                │  MainApp:                                        │
                │  - useSession() → POST /api/sessions             │
                │  - RoomProvider (connects to LiveKit)            │
                │  - ClassroomScreen (live) | LectureViewer        │
                └─────────────────────────────────────────────────┘
```

---

## 1. Entry points

### `index.html`

```html
<div id="root"></div>
<script type="module" src="/src/main.tsx"></script>
```

Single mount point. Vite handles HMR.

### `src/main.tsx`

10 lines:

```typescript
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>
);
```

### `src/App.tsx` (~173 lines)

Hash-based dev routing + the product front door.

```tsx
function App() {
    const route = useHashRoute();   // listens to window.location.hash

    if (route === "/dev")                    return <DevHarness />;
    if (route === "/dev/split-board")         return <SplitBoardPrototype />;
    if (route === "/diagram_generation_test") return <DiagramGenerationTestScreen />;
    if (route === "/lecture-preview")         return <LecturePreviewScreen />;
    if (route === "/dev/live-teacher")        return <MainApp legacyLiveMode />;

    return <MainEntry />;
}

function MainEntry() {
    const lectureChapterId = useLectureChapterParam();   // reads ?lecture= from URL
    if (lectureChapterId) {
        // Auto-start a session pointed at the precomputed chapter
        return <MainApp lectureChapterId={lectureChapterId} />;
    }
    return <LectureHomeScreen />;
}
```

### `MainApp` (in App.tsx, lines 83–172)

The session-bearing wrapper.

```tsx
function MainApp({ lectureChapterId, legacyLiveMode }) {
    const { status, sessionId, token, livekitUrl, lectureChapterId: lectureId, startSession } = useSession();

    useEffect(() => {
        if (lectureChapterId) startSession({ lecture_chapter_id: lectureChapterId });
    }, [lectureChapterId, startSession]);

    if (status === "idle" && !lectureChapterId) {
        return <WaitingScreen onStart={params => startSession(params)} />;
    }
    if (status === "connecting") return <ConnectingSpinner />;
    if (status === "error")      return <ErrorPanel />;

    return (
        <RoomProvider token={token} serverUrl={livekitUrl}>
            <ClassroomScreen lectureChapterId={lectureId} />
        </RoomProvider>
    );
}
```

---

## 2. Screens

### `LectureHomeScreen.tsx` (~80 lines) — chapter picker

The product front door for the consumer product.

```tsx
function LectureHomeScreen() {
    const [chapters, setChapters] = useState<ChapterListEntry[]>([]);

    useEffect(() => {
        fetch("/lecture-api/chapters")     // → proxied to preview_server :8080
            .then(r => r.json())
            .then(setChapters);
    }, []);

    return (
        <div className="lecture-home">
            {chapters.filter(c => c.has_manifest).map(c => (
                <button key={c.id} onClick={() => {
                    window.location.search = `?lecture=${encodeURIComponent(c.id)}`;
                }}>
                    <h3>{c.title}</h3>
                </button>
            ))}
        </div>
    );
}
```

A `ChapterListEntry` has `{id, title, idx, has_manifest}`. The chapter list is served by `data_pre_compute_v2/tools/preview_server.py` (port 8080), proxied by Vite from `/lecture-api/` (see `vite.config.ts`).

### `LectureViewer.tsx` (~300 lines) — precomputed playback + doubt resolution

The main screen for lecture-playback mode.

```tsx
function LectureViewer({ chapterId }: { chapterId: string }) {
    const [chapter, setChapter] = useState<ChapterPayload | null>(null);

    useEffect(() => {
        fetch(`/lecture-api/chapter/${encodeURIComponent(chapterId)}`)
            .then(r => r.json())
            .then(setChapter);
    }, [chapterId]);

    const {
        slide,            // SlideState (active spec, focusedElementId, traces, markPoints, pointers, marginNotes)
        notebook,         // NotebookState (current page, page number, turning flag)
        cursor,
        currentTopicId,
        currentSnapshot,  // BoardSnapshot at current playback point (feat/unify_boardstate)
        pause, play, applyDoubtBeat,
    } = useExtractionPlayback({ chapter, autoStart: true });

    // Doubt-resolution state machine
    const [doubtState, setDoubtState]                 = useState<"idle"|"listening"|"thinking"|"error">("idle");
    const [satisfactionOptions, setSatisfactionOptions] = useState<SatisfactionOption[] | null>(null);
    const [errorMessage, setErrorMessage]             = useState<string | null>(null);

    // Listen on doubt_signal channel for worker messages
    useDataChannel("doubt_signal", useCallback(msg => {
        const data = JSON.parse(new TextDecoder().decode(msg.payload));
        switch (data.type) {
            case "doubt_captured":    /* worker confirms it heard us */ break;
            case "thinking":          setDoubtState("thinking"); break;
            case "resolution_ready":  /* prepares for beat delivery */ break;
            case "doubt_beat_start":  applyDoubtBeat(data, chapter); break;
            case "satisfaction_prompt": setSatisfactionOptions(data.options); break;
            case "doubt_resolution_failed": setDoubtState("error"); setErrorMessage(data.reason); break;
            case "lecture_resume":    setDoubtState("idle"); play(); break;
        }
    }, [chapter, applyDoubtBeat, play]));

    const room = useRoomContext();

    async function onAskFeynman() {
        pause();
        setDoubtState("listening");
        await room.localParticipant.publishData(
            new TextEncoder().encode(JSON.stringify({
                type: "doubt_intent",
                chapter_id: chapterId,
                cursor,
                topic_id: currentTopicId,
                board_snapshot: currentSnapshot,
            })),
            { topic: "doubt_signal", reliable: true },
        );
    }

    async function onSatisfactionChoose(key: string) {
        setSatisfactionOptions(null);
        await room.localParticipant.publishData(
            new TextEncoder().encode(JSON.stringify({ type: "satisfaction_choice", option: key })),
            { topic: "doubt_signal", reliable: true },
        );
    }

    return (
        <>
            <SplitBoard slide={slide} notebook={notebook} mode="split" viewport="responsive" />
            <AskFeynmanButton state={doubtState} onActivate={onAskFeynman} onRetry={() => { setDoubtState("idle"); play(); }} errorMessage={errorMessage} />
            {satisfactionOptions && <SatisfactionPrompt options={satisfactionOptions} onChoose={onSatisfactionChoose} />}
        </>
    );
}
```

Key things:
- Audio playback is driven by `useExtractionPlayback` via an `HTMLAudioElement`. The hook returns `pause`/`play` for the cursor-stepped state machine.
- The worker sees `topic="doubt_signal"` messages and routes them via `DoubtDelivery` (see `04-livekit-agent-worker.md` §5).
- `currentSnapshot` (from `feat/unify_boardstate`) is the **single canonical board state** passed to the worker so it doesn't have to query DOM.
- Timeouts guard against stuck states: 12s for `listening` (no STT capture), 75s for `thinking` (planner stuck).

### `ClassroomScreen.tsx` (~72 lines) — branching entry

```tsx
function ClassroomScreen({ lectureChapterId }) {
    if (lectureChapterId) return <LectureViewer chapterId={lectureChapterId} />;
    return <LiveAgentClassroom />;
}

function LiveAgentClassroom() {
    const visualChannelState = useVisualChannel();
    const syncManager        = useCreateSyncManager();

    // Feed transcribed words into the sync manager
    useAgentTranscription(useCallback(word => syncManager.onWord(word), [syncManager]));

    const { slide, notebook } = useSplitBoardState(
        visualChannelState.activeInstructions,
        visualChannelState.pendingSlide,
    );

    return (
        <SyncManagerContext.Provider value={syncManager}>
            {config.splitBoardEnabled
                ? <SplitBoard slide={slide} notebook={notebook} mode="split" />
                : <WhiteboardScene
                    instructions={visualChannelState.activeInstructions}
                    walks={visualChannelState.activeWalks}
                    activeBoardId={visualChannelState.activeBoardId}
                    activeBoardMeta={visualChannelState.activeBoardMeta}
                    pendingTransition={visualChannelState.pendingTransition}
                    cameraState={visualChannelState.cameraState}
                  />}
        </SyncManagerContext.Provider>
    );
}
```

### `WaitingScreen.tsx` (~106 lines)

Pre-session form: text input for topic ("Kinematics"), dropdown for subject (physics/math/chemistry/biology). On submit calls `onStart({ topic, subject })` → `useSession().startSession()`.

### Other screens

| File | Purpose |
|---|---|
| `LecturePreviewScreen.tsx` | Manual chapter selection at fixed 1600×900 viewport for precompute QA. Renders `SplitBoard` with `viewport="preview"`. |
| `DiagramGenerationTestScreen.tsx` | Plugin lab; consumes `/diagtest/*` endpoints from the backend's experiments router. Strategy + model + prompt selectors, history list. |
| `SplitBoardPrototype.tsx` | Early UI iteration sandbox. |
| `DevHarness.tsx` | Interactive component playground using `dev-fixtures.ts`. |
| `dev-fixtures.ts` | Sample `VisualInstruction[]`, `DiagramSpec`, fake chapters. |

---

## 3. The rendering engine — `src/engine/`

The architecture moved from canvas-based to **HTML-first component tree** in Phase 2+. The high-level shape:

```
<VisualScene> or <WhiteboardScene> or <SplitBoard>
├─ ElementRegistryContext.Provider
├─ BoardLayoutContext.Provider (whiteboard only)
├─ <div.scene-viewport> | <div.wb-viewport> | <div.split-board>
│  ├─ <VisualCard> → <InstructionSwitch> → <Content Component>
│  └─ ... more cards / panels ...
├─ <HighlightOverlay /> (CSS-driven, headless)
└─ <AnnotationLayer /> (SVG overlay for freehand strokes)
```

### Core files

| File | Purpose |
|---|---|
| `VisualScene.tsx` | Legacy card-list renderer. Used when `VITE_SPLIT_BOARD=false`. Manages auto-scroll. |
| `Canvas.tsx` | **Deprecated.** Old canvas-based rendering, kept for rollback safety. |
| `InstructionSwitch.tsx` | Type dispatcher. Switches on `instruction.type` and returns the right content component. |
| `VisualCard.tsx` | Card wrapper that registers itself in `ElementRegistry` on mount, sets `data-type` / `data-element-id` attrs. |
| `elements.ts` | Element registry (`React.Context` over `useRef<Map>`). Methods: `register`, `unregister`, `get`, `entries`. Used by `HighlightOverlay` to look up DOM nodes. |
| `renderer.ts` | Lower-level render helpers. |
| `theme.ts` | Design tokens (colors, layout, fonts). `injectThemeVars(el)` sets CSS custom properties. `TYPE_ACCENT` map: instruction type → color. |
| `chart-defaults.ts` | Chart.js defaults. |
| `math-eval.ts` | Safe math expression evaluation (also used by `DiagramRenderer`). |
| `SyncManager.ts` | Voice-visual sync engine. |
| `useSyncManager.ts` | Hook + context for `SyncManager`. |

### Content components — `src/engine/content/`

| Component | Renders |
|---|---|
| `TextContent.tsx` | `show_text` with style variants (default/definition/key_point/example). |
| `EquationContent.tsx` | `show_equation` via KaTeX, supports `none/fade_in/term_by_term/write_on` animations. |
| `StepEquationContent.tsx` | `step_equation` with progressive reveal + optional term highlighting (driven by `SyncManager`). |
| `DiagramContent.tsx` | `draw_diagram` with auto-layout (dagre/circular/two-column). |
| `GraphContent.tsx` | `show_graph` (Chart.js integration pending in Phase 6). |
| `HighlightOverlay.tsx` | Headless component that applies a CSS class to the target card by ID lookup. |

### Whiteboard subsystem — `src/engine/whiteboard/`

Living-board view with multi-board support, infinite canvas, and zone-based placement.

| File | Purpose |
|---|---|
| `WhiteboardScene.tsx` | Multi-board renderer. Computes layout via `useBoardScale()` + `computeBoardLayout()`. Renders placed cards, walks, annotations, board navigator, bounds reporter. |
| `WhiteboardCard.tsx` | Absolutely-positioned card; renders content via `InstructionSwitch`. |
| `useBoardStore.ts` | Multi-board state manager (useRef Maps + useState for active/transitions). |
| `types.ts` | Board constants: `BOARD_WIDTH=1920, BOARD_HEIGHT=1080`, zone enum (9 zones). |
| `zone-layout.ts` | Divides 1920×1080 into 9 zones (3×3) with outer + inner padding. |
| `board-coords.ts` | Logical-board ↔ viewport-pixel space conversion. |
| `content/DesignDiagramContent.tsx` | Renders design-agent specs (SVG primitives + parameters + KaTeX overlay). |
| `content/RoughDiagramContent.tsx` | Hand-drawn aesthetic via rough.js. |
| `content/AnnotationLayer.tsx` | SVG overlay covering full board, renders annotation overlays. |
| `scene/` | Semantic scene components (free-body, circuits, chemistry, optics, geometry). Each has shape components (box, force-arrow, spring, surface) and layout strategies. |
| `fonts/` | Hershey vector font for handwritten text rendering. |

### `useBoardStore` — multi-board state manager

The frontend mirror of the backend's `BoardManager`. Tracks per-board state, active board, transitions, camera position.

```typescript
function useBoardStore() {
    const boardsRef = useRef<Map<string, VisualInstruction[]>>(new Map());
    const metasRef = useRef<Map<string, BoardMeta>>(new Map());
    const camerasRef = useRef<Map<string, CameraState>>(new Map());
    const [activeBoardId, setActiveBoardId] = useState("main");
    const [activeInstructions, setActiveInstructions] = useState<VisualInstruction[]>([]);
    const [pendingTransition, setPendingTransition] = useState<BoardTransition | null>(null);
    const [pendingSlide, setPendingSlide] = useState<Record<string, PendingSlide | undefined>>({});

    function addInstruction(instr) {
        const board = boardsRef.current.get(activeBoardId) ?? [];
        boardsRef.current.set(activeBoardId, [...board, instr]);
        if (instr.board_id === activeBoardId) setActiveInstructions(prev => [...prev, instr]);
    }

    function switchBoard(instr: SwitchBoardInstruction) {
        if (!boardsRef.current.has(instr.board_id)) {
            boardsRef.current.set(instr.board_id, []);
            metasRef.current.set(instr.board_id, { label: instr.label, intent: instr.intent });
        }
        setPendingTransition({ to: instr.board_id, intent: instr.intent });
        setActiveBoardId(instr.board_id);
        setActiveInstructions(boardsRef.current.get(instr.board_id) ?? []);
    }

    function clearBoard(boardId?: string, targetId?: string) {
        const bid = boardId ?? activeBoardId;
        if (targetId) {
            boardsRef.current.set(bid, (boardsRef.current.get(bid) ?? []).filter(i => i.element_id !== targetId));
        } else {
            boardsRef.current.set(bid, []);
        }
        setActiveInstructions(boardsRef.current.get(activeBoardId) ?? []);
    }

    return { ... };
}
```

---

## 4. Split-board system — `src/engine/whiteboard/split/`

The two-panel UI: Slide (left) + Notebook (right). What the `LectureViewer` and the live-agent classroom (when `VITE_SPLIT_BOARD=true`) render.

| File | Purpose |
|---|---|
| `SplitBoard.tsx` | Top-level. Props: `slide, notebook, mode (split/slide_full/notebook_full), viewport (responsive/preview)`. CSS-driven transitions. |
| `SlidePanel.tsx` | Renders the active slide (design diagram or sketch). Implements spotlight system. Two presentation modes: `build_up` (elements hidden, revealed on focus) and `overview` (dimmed, spotlit on focus). |
| `Notebook.tsx` | Renders notebook pages. Supports pagination, indentation, strikethrough. |
| `useSplitBoardState.ts` | Adapter — derives SlideState + NotebookState from live instruction stream. Partitions on `instruction.panel`. |
| `types.ts` | `SlideState`, `NotebookState`, `NotebookEntry` union (13 types), `TraceState`, `MarkPointState`, `PointerState`, `MarginNoteState`. |

### `SlideState` and `NotebookState`

```typescript
interface SlideState {
    status: "empty" | "loading" | "ready";
    active: DiagramSpec | null;              // current slide diagram
    liveInstruction: VisualInstruction | null;
    focusedElementId: string | null;          // spotlight target
    annotations: AnnotationState[];
    traces: TraceState[];
    markPoints: MarkPointState[];
    pointers: PointerState[];
    marginNotes: MarginNoteState[];
}

interface NotebookState {
    currentPage: number;
    turning: boolean;
    pages: NotebookPage[];
}

interface NotebookPage {
    page: number;
    entries: NotebookEntry[];
}

type NotebookEntry =
    | EquationEntry | StepEntry | TextEntry | SectionEntry | AnswerEntry | GraphEntry
    | KeyPointEntry | DerivationEntry | ...   // 13 types total
```

### `useSplitBoardState` — the live adapter

In live-agent mode, `useSplitBoardState(activeInstructions, pendingSlide)` walks the instruction stream and produces the slide + notebook state. Live-agent equivalent of the precomputed `useExtractionPlayback`:

```typescript
const SLIDE_TYPES = new Set([
    "draw_design_diagram", "draw_diagram", "draw_scene", "show_text", "show_equation",
]);
const NOTEBOOK_TYPES = new Set([
    "write_equation", "write_step", "write_text", "write_section", "write_answer",
    "strikethrough", "new_page", "show_equation"  // notebook show_equation
]);

function useSplitBoardState(instructions, pendingSlide) {
    const slide = useMemo(() => {
        const slideInstructions = instructions.filter(i => SLIDE_TYPES.has(i.type) && i.panel !== "notebook");
        const latest = slideInstructions[slideInstructions.length - 1];
        // Build SlideState from `latest` (cast to DiagramSpec if it's a design diagram)
        return buildSlideState(latest, instructions, pendingSlide);
    }, [instructions, pendingSlide]);

    const notebook = useMemo(() => {
        const notebookInstructions = instructions.filter(i => NOTEBOOK_TYPES.has(i.type) && i.panel === "notebook");
        return buildNotebookState(notebookInstructions);
    }, [instructions]);

    return { slide, notebook };
}
```

The split is by `instruction.panel`. Backend tools call `_stamp_panel()` to set this based on instruction type.

### `DesignDiagramContent.tsx` (slide renderer)

The frontend mirror of the standalone design_agent's `DiagramRenderer.jsx`. Renders the 11 SVG primitive types + KaTeX overlay + slider parameters from a `DiagramSpec`. Adds `data-design-element={id}` on every element so highlight walks and focuses can target sub-elements.

Spotlight implementation (used by `SlidePanel`):
- `focusedElementId` set → all other elements dimmed (`opacity: 0.3`), focused one gets a glow filter.
- In `build_up` mode: all elements start hidden (`opacity: 0`), revealed as they become focused in sequence.
- In `overview` mode: all elements visible from the start, spotlight is purely additive.

### `AnnotationLayer.tsx`

SVG overlay covering the full slide area, `pointer-events: none`. Renders:
- `TraceState` → animated stroke along an element's path (via `<animate>` SVG primitive).
- `MarkPointState` → small `<circle>` / `<polygon>` star/cross at viewBox coords with optional label.
- `PointerState` → SVG arrow pointing at an element from one of four sides.
- `MarginNoteState` → text positioned in the margin.

---

## 5. Voice-visual sync — `SyncManager`

```typescript
export class SyncManager {
    private terms = new Map<string, TermSync>();          // term_id → {trigger_words, callback}
    private walks = new Map<string, WalkSync>();
    private revealedTerms = new Set<string>();

    register(id: string, hints: TermSyncHint[], callbacks: Record<string, () => void>): () => void {
        // Register hints + their callbacks; return unregister fn
    }

    registerWalk(id: string, hints: TermSyncHint[], callbacks): () => void {
        // Spotlight walk semantics (one term active at a time, deactivates previous)
    }

    onWord(word: string) {
        // Normalize lowercase + alphanumeric only
        const n = word.toLowerCase().replace(/[^a-z0-9]/g, "");
        for (const [termId, sync] of this.terms) {
            if (this.revealedTerms.has(termId)) continue;
            if (sync.trigger_words.includes(n)) {
                this.revealedTerms.add(termId);
                sync.callback();
            }
        }
        // Same for walks
    }

    revealAll(id: string): void { /* fire all unrevealed callbacks */ }
    clear(): void               { /* reset everything */ }
}
```

Used by `StepEquationContent` and `HighlightWalkOverlay`:

```typescript
function StepEquationContent({ instruction }) {
    const syncManager = useSyncManager();
    const stepRefs = useRef<Map<string, HTMLElement>>(new Map());

    useEffect(() => {
        if (!instruction.term_hints) return;
        const unregister = syncManager.register(
            instruction.element_id,
            instruction.term_hints,
            Object.fromEntries(instruction.term_hints.map(h => [h.term_id, () => {
                const el = stepRefs.current.get(h.term_id);
                if (el) gsap.to(el, { opacity: 1, duration: 0.3 });
            }])),
        );
        return unregister;
    }, [instruction, syncManager]);

    return ( ... );
}
```

When the agent says the trigger word, the callback fires and GSAP animates the term reveal.

`useAgentTranscription` (`src/livekit/useAgentTranscription.ts`) listens to `RoomEvent.TranscriptionReceived`, filters out the local participant (student STT), iterates finalized segments, splits by whitespace, and calls `onWord(word)` for each — feeding the sync manager.

---

## 6. LiveKit client — `src/livekit/`

### `RoomProvider.tsx`

```tsx
function RoomProvider({ token, serverUrl, children }) {
    return (
        <LiveKitRoom
            token={token}
            serverUrl={serverUrl}
            connect={true}
            audio={true}
            video={false}
            onConnected={() => console.log("LK connected")}
            onDisconnected={() => console.log("LK disconnected")}
            onError={err => console.error("LK error", err)}
        >
            <RoomAudioRenderer />
            {children}
        </LiveKitRoom>
    );
}
```

`<RoomAudioRenderer />` is from `@livekit/components-react` and handles all inbound audio (the agent's TTS).

### `useVisualChannel.ts` (~235 lines) — the core data channel hook

Already extensively covered in `07-contracts-and-protocols.md` §5. Subscribes to `topic="visuals"`, decodes JSON, defers `sync_mode="after_next_sentence"` until the next sentence boundary, routes to `useBoardStore`.

Returns:

```typescript
{
    lastInstruction: VisualInstruction | null,
    instructions: VisualInstruction[],            // legacy flat array
    activeInstructions: VisualInstruction[],      // current board
    activeWalks: HighlightWalkInstruction[],
    activeBoardId: string,
    activeBoardMeta: BoardMeta | null,
    pendingTransition: BoardTransition | null,
    cameraState: CameraState,
    pendingSlide: Record<string, PendingSlide | undefined>,
    clearTransition: () => void,
    getBoardInstructions: (boardId: string) => VisualInstruction[],
}
```

### `useAgentTranscription.ts`

Feeds transcribed agent words into the sync manager. 36 lines.

---

## 7. Hooks — `src/hooks/`

| Hook | Purpose |
|---|---|
| `useSession.ts` (~37 lines) | Session lifecycle: `idle` → `connecting` → `connected` → `error`. Returns `{ sessionId, token, livekitUrl, lectureChapterId, status, error, startSession }`. `startSession()` calls `POST /api/sessions` via `lib/api.ts`. |
| `useExtractionPlayback.ts` (~100+ lines) | Walks `chapter.events[]` sequentially. Handles audio playback (HTMLAudioElement), pause/play with cursor rewind, all 27 manifest event types. Returns `{ slide, notebook, cursor, currentTopicId, currentSnapshot, play, pause, applyDoubtBeat }`. |
| `useHashRoute.ts` | Subscribes to `window.location.hash`. |
| `useLectureChapterParam.ts` | Reads `?lecture=` from URL. |

---

## 8. Lib — `src/lib/`

### `config.ts`

```typescript
export const config = {
    livekitUrl: import.meta.env.VITE_LIVEKIT_URL ?? "ws://localhost:7880",
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api",
    splitBoardEnabled: (import.meta.env.VITE_SPLIT_BOARD ?? "true") !== "false",
} as const;
```

The Vite dev server proxies `/api` → `http://localhost:8000` and `/lecture-api/` + `/lecture-artifacts/` → `http://127.0.0.1:8080`. See `vite.config.ts` below.

### `api.ts`

```typescript
export interface CreateSessionRequest {
    topic?: string;
    subject?: string;
    grade_level?: string;
    lecture_chapter_id?: string;
}

export interface CreateSessionResponse {
    session_id: string;
    token: string;             // LiveKit JWT
    livekit_url: string;
    room_name: string;
    lecture_chapter_id?: string | null;
}

export async function createSession(body?: CreateSessionRequest): Promise<CreateSessionResponse> {
    const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body ?? {}),
    });
    if (!res.ok) throw new Error(`session create failed: ${res.status}`);
    return res.json();
}
```

---

## 9. Types — `src/types/visuals.ts`

Mirrors `contracts/visuals.schema.json` and backend Pydantic. Fully covered in `07-contracts-and-protocols.md`. The frontend has the 25 instruction types as a discriminated union plus the design diagram element types (12 SVG primitive types + GraphElement) + slider param + element meta + the precompute manifest's 27 event types (mirrored for `LectureViewer`).

---

## 10. Components — `src/components/`

### `AskFeynmanButton.tsx` (~282 lines)

Floating button bottom-right of the screen. State machine: `idle` → `listening` → `thinking` → `error`.

Visual affordances:
- **idle**: blue pill, mic glyph, "Ask Feynman", enabled.
- **listening**: red pulsing dot, "I'm listening...", disabled (VAD-controlled).
- **thinking**: spinner, "Feynman is thinking...", disabled.
- **error**: warning triangle, error message, "Try again" button.

CSS keyframes (`afb-pulse`, `afb-spin`) injected on module load.

### `SatisfactionPrompt.tsx` (~161 lines)

Modal overlay shown after a doubt-resolution sequence completes. Backdrop blur + centered card. Props: `options: SatisfactionOption[], onChoose: (key: string) => void`.

Options come from the worker's `satisfaction_prompt` message:
- `crystal_clear` (primary cyan)
- `counter_doubt` (secondary)
- `somewhat_cleared` (secondary)
- `start_over` (secondary)

---

## 11. Diagram-lab — `src/diagram-lab/`

Plugin lab for testing diagram generation strategies. Consumes `/diagtest/*` endpoints from the backend's experiments router (`backend/src/feynman/experiments/diagram_lab/router.py`).

| File | Purpose |
|---|---|
| `types.ts` | Mirrors testbed response shapes (`StrategyDescriptor`, `StrategyResult`, `RunResponse`, `HistoryEntry`, `AnnotationInjectResponse`). |
| `api.ts` | Fetch client for `/diagtest/*`. |
| `StrategyOptionsForm.tsx` | Dynamic form builder from JSON Schema. |

Accessed via `#/diagram_generation_test`.

---

## 12. Styles — `src/styles/`

| File | Purpose |
|---|---|
| `global.css` | Reset + root setup. Body bg `#0a0a0a`, text `#fafafa`, `system-ui` font, html/body/root all 100% with `overflow: hidden`. |
| Component-scoped CSS | `VisualScene.css`, `WhiteboardScene.css`, `SplitBoard.css` — colocated with their components. |
| Inline styles | `AskFeynmanButton` and `SatisfactionPrompt` use inline styles for fixed-position behaviors and keyframes. |

---

## 13. Build & dev config

### `vite.config.ts` (~31 lines)

```typescript
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/api":               "http://localhost:8000",
            "/ws":                "ws://localhost:8000",
            "/lecture-api":       "http://127.0.0.1:8080",
            "/lecture-artifacts": "http://127.0.0.1:8080",
        },
    },
});
```

Explicit `127.0.0.1` for the preview server avoids Node DNS IPv6 quirks (a Phase-2 bug).

### `package.json` headline deps

- `react@19.2`, `react-dom@19.2`
- `@livekit/components-react@2.9`, `livekit-client@2.13`
- `katex@0.16.33` — LaTeX rendering
- `chart.js@4.5`, `expr-eval@2.0` — graphing + math expressions
- `roughjs@4.6` — hand-drawn aesthetic
- `gsap@3.14` — animations (term reveals)
- `html2canvas@1.4` — board snapshots
- `perfect-freehand@1.2` — handwriting stroke smoothing
- `@dagrejs/dagre@2.0` — graph layout for `draw_diagram`

Dev: TypeScript 5.9, ESLint 9 (flat config), Prettier, Vitest, `@testing-library/react@16.3`, `jsdom@26.1`.

### Scripts

```json
{
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "format": "prettier --write .",
    "test": "vitest"
}
```

---

## 14. Control-flow traces

### Trace A — student joins live session

```
1. App.tsx (MainEntry):
   - useSession() → idle state
   - <WaitingScreen onStart={...}> renders

2. Student fills form, clicks Start:
   - startSession({ topic: "Kinematics", subject: "physics" })
   - lib/api.ts::createSession() → POST /api/sessions
   - Backend creates session, mints LK token, returns { session_id, token, livekit_url, room_name }

3. useSession() transitions: idle → connecting → connected
4. <RoomProvider token={...} serverUrl={...}> wraps <ClassroomScreen>
   - LiveKitRoom hook initiates WebRTC; onConnected fires

5. <ClassroomScreen> → <LiveAgentClassroom>
   - useVisualChannel() subscribes to topic="visuals" (data channel)
   - useCreateSyncManager() instantiates manager
   - useAgentTranscription(handleWord) listens for transcription events

6. <SplitBoard mode="split" /> (or WhiteboardScene if VITE_SPLIT_BOARD=false)
   - empty state — agent hasn't said anything yet

7. Worker side: same time, LiveKit dispatches a new agent job.
   - entrypoint() reads room metadata
   - Builds TeachingStateMachine + TeachingContext
   - on_enter loads curriculum, plans concept 0 + 1, builds prompt
   - Greets the student via TTS
```

### Trace B — agent emits a visual instruction (live mode)

```
Worker (agent decides to draw something):
   Tool draw_design_diagram(prompt="right triangle ladder against wall")
   → design_bridge.generate_design_diagram(...)
   → spec returned
   → DrawDesignDiagramInstruction wrapped, _publish_visual()
     ├── element_id = "design-5"
     ├── resolve_placement → (position_x, position_y)
     ├── board_manager.record() updates BoardState atomically
     ├── audit.record()
     ├── wait_for_playout() if ON_PLAYOUT (default)
     └── publish_data(topic="visuals", data=json(instruction))

LiveKit routes data over WebRTC

Frontend useVisualChannel.onMessage:
   const text = TextDecoder.decode(msg.payload)
   const parsed = JSON.parse(text) as VisualInstruction
   if parsed.sync_mode === "after_next_sentence" → enqueueDeferred
   else applyInstruction(parsed):
     - not switch_board / scroll_view / clear / highlight_walk
     - addInstruction(parsed) via useBoardStore
     - setActiveInstructions(prev => [...prev, parsed])

ClassroomScreen re-renders:
   useSplitBoardState() partitions instructions:
     - design diagram → slide.active = spec, slide.status = "ready"
   <SplitBoard slide={...} notebook={...} />
   <SlidePanel> renders <DesignDiagramContent spec={spec}>
     - Walks elements, renders each as SVG primitive
     - LaTeX overlays positioned absolutely on top
     - Slider parameters become live <input type="range">
   DOM updates

ResizeObserver:
   - BoundsReporter walks registered DOM nodes via ElementRegistry
   - Builds BoundsReportPayload { board_id, timestamp, elements: [...] }
   - publish_data(topic="bounds", data=json)

Worker _on_data_received:
   - report = BoundsReportPayload.model_validate_json(packet.data)
   - board_manager.update_bounds(report.board_id, report)
   - BoardState.update_spatial(report) — atomic refresh of scene_graph + spatial_solver
```

### Trace C — precomputed lecture plays

```
1. LectureHomeScreen mounts
   - fetch /lecture-api/chapters → preview_server.py returns ChapterListEntry[]
   - Renders chapter grid

2. Student clicks chapter
   - window.location.search = "?lecture=chapter:phys:001"

3. App.tsx re-renders, MainEntry sees lectureChapterId param
   - <MainApp lectureChapterId={...}>
   - useEffect: startSession({ lecture_chapter_id: "chapter:phys:001" })
   - POST /api/sessions returns token + livekit_url
   - <RoomProvider> wraps <ClassroomScreen>
   - ClassroomScreen sees lectureChapterId → renders <LectureViewer>

4. LectureViewer
   - fetch /lecture-api/chapter/chapter:phys:001 → ChapterPayload (full manifest)
   - useExtractionPlayback({ chapter, autoStart: true })
     - cursor = 0
     - effect fires play()
       - playOne() loop:
         - For each event in chapter.events:
           - audio:         audioElement.src = event.url; play; await ended
           - pause:         await sleep(event.duration_ms)
           - show_diagram:  setSlide({ active: event.spec, status: "ready" })
           - focus:         setSlide(s => ({...s, focusedElementId: event.target_element_id}))
           - trace/mark_point/point_at/write_margin:
                            append to slide.{traces|markPoints|pointers|marginNotes}
           - write_*:       append to notebook.pages[currentPage].entries
           - strikethrough: mark entry as struck
           - new_page:      turn page, optionally copy carry_forward_ids
           - clear_annotations: wipe traces/markPoints/pointers
           - cursor++

5. Worker side (parallel):
   - entrypoint() reads metadata, sees lecture_chapter_id
   - _run_lecture_mode(ctx, chapter_id=...)
   - LectureDoubtSession loads chapter context
   - DoubtDelivery publishes its own audio track (silent until needed)
   - Listens on topic="doubt_signal"

6. Student watches lecture. Audio plays from the frontend's HTMLAudioElement
   (not from the worker — the worker is silent in lecture mode).
   Visuals update from manifest events.

7. Student taps "Ask Feynman":
   - LectureViewer.onAskFeynman():
     - pause() → cursor rewinds 1 event
     - setDoubtState("listening")
     - publish_data on topic="doubt_signal" with:
       { type: "doubt_intent", chapter_id, cursor, topic_id, board_snapshot }
   - board_snapshot is currentSnapshot from useExtractionPlayback — the unified board state
   - Worker resolves and streams beats (see 04-livekit-agent-worker.md §5)
   - LectureViewer applies beats via applyDoubtBeat()
   - SatisfactionPrompt shows, student picks → publish_data → "lecture_resume" → play()
```

---

## 15. Reading order for a new engineer

1. `frontend/CLAUDE.md`.
2. This doc.
3. `src/App.tsx` — the routing.
4. `src/screens/LectureViewer.tsx` — the most feature-rich screen, including doubt resolution.
5. `src/hooks/useExtractionPlayback.ts` — manifest playback.
6. `src/livekit/useVisualChannel.ts` — live instruction stream.
7. `src/engine/whiteboard/split/useSplitBoardState.ts` — live state derivation.
8. `src/engine/whiteboard/split/SplitBoard.tsx` + `SlidePanel.tsx` + `Notebook.tsx` — the production rendering path.
9. `src/engine/whiteboard/content/DesignDiagramContent.tsx` — how design specs become SVG.
10. `src/engine/SyncManager.ts` — voice-visual sync.
