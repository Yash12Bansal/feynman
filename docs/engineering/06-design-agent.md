# 06 — Design Agent (`design_agent/`)

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

## TL;DR

The design_agent is a **standalone mini-app** for AI-powered diagram generation. It has its own FastAPI backend (port 8000), its own React frontend (port 3001), and its own Python venv (it does **not** use the main `backend/` uv environment).

But here's the catch: **the main backend does not use the design_agent over HTTP.** It imports `design_agent/backend/prompts.py:SYSTEM_PROMPT` and `prompts_python.py:SYSTEM_PROMPT_PYTHON` directly, and calls Claude in-process via `backend/src/feynman/agent/design_bridge.py`. The standalone design_agent is a **developer playground / authoring lab** — when you want to tune prompts, A/B models, or visually preview specs in isolation, you run it.

The precompute pipeline (`data_pre_compute_v2/`) keeps a **verbatim copy** of `SYSTEM_PROMPT` in `curriculum/enrichment/diagrams.py` so its precomputed diagrams use the same authoring rules. The file is annotated "DO NOT EDIT — synced VERBATIM."

```
┌──────────────────────── design_agent/ (standalone) ─────────────────────────┐
│                                                                              │
│   backend/  (FastAPI :8000)              frontend/  (React :3001)            │
│   ├─ main.py     (HTTP endpoints)        ├─ App.js                          │
│   ├─ agent.py    (Claude streaming)      ├─ PromptInput.jsx                 │
│   ├─ schema.py   (DiagramSpec)            ├─ DiagramRenderer.jsx             │
│   ├─ prompts.py        ◀─┐                └─ LatexBlock.jsx                 │
│   └─ prompts_python.py ◀─┤                                                  │
│                          │                                                   │
└──────────────────────────┼──────────────────────────────────────────────────┘
                           │ (imported by file, not HTTP)
                           │
┌──────────────────────────┴──────────────────────────────────────────────────┐
│  backend/src/feynman/agent/design_bridge.py                                  │
│  - Reads SYSTEM_PROMPT from design_agent/backend/prompts.py                  │
│  - Reads SYSTEM_PROMPT_PYTHON from design_agent/backend/prompts_python.py    │
│  - Calls Claude (or Ollama) directly                                         │
│  - Returns a DiagramSpec dict                                                │
│  - Caches 64 specs (FIFO) keyed by (prompt, mode, provider, model, mtime)    │
│  - Persists every generated spec to design_agent/generated/ for audit        │
└──────────────────────────────────────────────────────────────────────────────┘
                           ▲
                           │
┌──────────────────────────┴──────────────────────────────────────────────────┐
│  Main backend teaching tools (agent/tools.py)                                │
│  - draw_design_diagram(prompt, mode, ...)                                    │
│  - modify_design_diagram(target_id, modification)                            │
│                                                                              │
│  data_pre_compute_v2/.../diagrams.py keeps SYSTEM_PROMPT (verbatim copy)     │
│  data_pre_compute_v2/.../diagram_spec_generator.py uses it offline           │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Backend — `design_agent/backend/`

### `main.py` (310 lines, FastAPI on `:8000`)

```python
app = FastAPI()
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# In-memory job store
jobs: dict[str, dict] = {}    # job_id → {status, accumulated, elements, partial_spec, final_spec, error}
```

#### Endpoints

| Route | Method | Purpose |
|---|---|---|
| `/api/health` | GET | `{status: "ok", model: "..."}` |
| `/api/generate/start` | POST | Kick off async generation. Body: `{prompt: str, model: str}`. Returns `{job_id: str}` (8-hex UUID). |
| `/api/generate/status/{job_id}` | GET | Poll progress. Returns `{status, elements_count, partial_spec?, final_spec?, error?}`. |
| `/api/generate/status/{job_id}` | DELETE | Clean up job from memory. |
| `/api/generate` | POST | Synchronous fallback (legacy). |
| `/api/generated` | GET | List all saved specs in `design_agent/generated/`. |

#### Progressive streaming — the interesting bit

When `/api/generate/start` is called, it creates a job and spawns `_run_generation()` as an `asyncio.Task`:

```python
async def _run_generation(job_id: str, prompt: str, model: str):
    job = jobs[job_id]
    job["status"] = "generating"
    try:
        async for chunk in agent.generate_stream(prompt, model=model):
            job["accumulated"] += chunk
            new = _extract_elements_from_partial(job["accumulated"])
            if new and len(new["elements"]) > len(job["elements"]):
                job["elements"]     = new["elements"]
                job["partial_spec"] = new
        job["final_spec"] = agent.parse_response(job["accumulated"])
        # Persist to design_agent/generated/<timestamp>_<prompt-slug>.json
        job["status"] = "done"
    except Exception as e:
        job["status"] = "error"
        job["error"]  = str(e)
```

`_extract_elements_from_partial(accumulated_text)` regex-parses the (likely-truncated) JSON Claude has emitted so far:

1. Pull top-level fields (`title`, `description`, `width`, `height`, `backgroundColor`).
2. Walk the partial `elements` array and emit any **complete** element objects (closing brace + balanced brackets).
3. Return `{meta: {...}, elements: [...]}`.

Frontend polls `/api/generate/status/{job_id}` every ~500ms. As new complete elements appear, the partial spec updates and the frontend renders them live. By the time Claude finishes streaming, the diagram has already been "drawing itself" for several seconds.

When the stream completes, `agent.parse_response(accumulated)` validates the full text against the `DiagramSpec` schema and stores it as `final_spec`.

### `agent.py` (~290 lines) — `DiagramAgent` class

```python
AVAILABLE_MODELS = {
    "opus":   "claude-opus-4-20250514",
    "sonnet": "claude-sonnet-4-20250514",
    "haiku":  "claude-haiku-4-5-20251001",
}

class DiagramAgent:
    def __init__(self, model="opus", max_tokens=16000, provider=None, ollama_base_url=None):
        self.system_prompt = SYSTEM_PROMPT       # from design_agent.backend.prompts
        self.async_client = AsyncAnthropic()      # if provider == "anthropic"
        ...

    async def generate_stream(self, prompt, model=None) -> AsyncGenerator[str, None]:
        if self.provider == "anthropic":
            async with self.async_client.messages.stream(
                model=AVAILABLE_MODELS[model or self.model],
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        else:    # ollama
            # POST to {ollama_base_url}/api/chat with stream=True, yield each chunk's content

    def parse_response(self, raw_text: str) -> dict:
        # _repair_json() handles truncation: strip dangling kv pairs, close braces/brackets
        spec = self._repair_json(raw_text)
        DiagramSpec(**spec)    # validate
        return spec            # return dict (not Pydantic) to skip serializer warnings
```

`_repair_json` (`agent.py:234-288`) is the safety net — if Claude was cut off mid-output, this strips trailing incomplete key-value pairs, counts unclosed braces/brackets, and patches them. If still unparseable, returns `None` and the caller treats it as an error.

### `schema.py` (310 lines) — `DiagramSpec` and friends

Full type tree:

```python
Coord = float | str           # number OR expression string like "L * sin(theta)"

class SliderParameter(BaseModel):
    name:    str
    min:     float
    max:     float
    default: float
    step:    float = 0.1
    label:   Optional[str] = None

class ElementPosition(StrEnum):
    TOP="top"; BOTTOM="bottom"; LEFT="left"; RIGHT="right"; CENTER="center"; DIAGONAL="diagonal"; ...

class ElementMeta(BaseModel):
    role:              str                     # "hypotenuse", "vertex", "angle", "label"
    semantic:          str                     # "the ladder, 10m"; "angle of elevation, 60°"
    position:          ElementPosition         # canonical position keyword
    spatial_relations: list[str]               # ["adjacent_to:vertex_A", "above:side_BC"]
    bounds:            Optional[tuple[float, float, float, float]]   # (x, y, w, h)

class GraphCurve(BaseModel):
    expression: str                            # JS math expression in x
    color:      str = "steelblue"
    strokeWidth: float = 2

class GraphElement(BaseModel):
    type: Literal["graph"] = "graph"
    id: Optional[str] = None
    x: Coord = 0; y: Coord = 0
    width: Coord = 300; height: Coord = 200
    xDomain: tuple[float, float] = (-10, 10)
    yDomain: tuple[float, float] = (-10, 10)
    xLabel: str = ""; yLabel: str = ""
    backgroundColor: str = "#f9f9f9"; borderColor: str = "#ccc"
    curves: list[GraphCurve] = []
    showGrid: bool = True

# 11 element types — DiagramElement is a discriminated union
class SvgLine(BaseModel):
    type: Literal["svg_line"] = "svg_line"; id: str | None = None
    x1: Coord; y1: Coord; x2: Coord; y2: Coord
    stroke: str = "#e8e8ee"; strokeWidth: float = 2; strokeDasharray: str = ""
class SvgRect(BaseModel):
    type: Literal["svg_rect"] = "svg_rect"; ...
    x, y, width, height: Coord; fill: str = "none"; stroke: str = "#e8e8ee"; ...
class SvgCircle(BaseModel):
    type: Literal["svg_circle"] = "svg_circle"; ...
    cx, cy, r: Coord; stroke: str; fill: str = "none"; ...
class SvgEllipse(BaseModel):
    type: Literal["svg_ellipse"] = "svg_ellipse"; ...
class SvgPath(BaseModel):
    type: Literal["svg_path"] = "svg_path"; d: str; ...
class SvgText(BaseModel):
    type: Literal["svg_text"] = "svg_text"; x, y: Coord; text: str; fontSize: int = 14; ...
class SvgArc(BaseModel):
    type: Literal["svg_arc"] = "svg_arc"; cx, cy, r, startAngle, endAngle: Coord; ...
class SvgGroup(BaseModel):
    type: Literal["svg_group"] = "svg_group"; transform: str; elements: list[DiagramElement]
class SvgLatex(BaseModel):
    type: Literal["svg_latex"] = "svg_latex"; x, y: Coord; expression: str; fontSize: int = 16; color: str = "#e8e8ee"
class SvgArrow(BaseModel):
    type: Literal["svg_arrow"] = "svg_arrow"; x1, y1, x2, y2: Coord; ...
# + GraphElement above
DiagramElement = Annotated[SvgLine | SvgRect | SvgCircle | ... | GraphElement, Field(discriminator="type")]

class AnimationSpec(BaseModel):
    model_config = {"extra": "allow"}
    duration: float = 2.0
    loop:     bool = True

class DiagramSpec(BaseModel):
    title:           str = "Untitled Diagram"
    description:     str = ""
    width:           int = 900
    height:          int = 650
    backgroundColor: str = "#ffffff"

    elements:        list[DiagramElement]   = Field(default_factory=list)
    parameters:      list[SliderParameter]  = Field(default_factory=list)
    animations:      list[AnimationSpec]    = Field(default_factory=list)

    dictionary:      dict[str, ElementMeta] = Field(
        default_factory=dict,
        description=(
            "Maps element_id → ElementMeta. Populated by design_agent at generation time. "
            "Empty dict means legacy/unenriched spec — teaching agent falls back to ID-only references."
        ),
    )
```

### Coordinate expressions

Any `Coord` can be a string like `"100 + L * sin(theta_rad)"`. The frontend renderer evaluates these with a safe `new Function(...)` scope including the slider parameter values. So a single `DiagramSpec` becomes a **live, slider-driven, parametric diagram** at render time. This is the most important property of the design_agent: diagrams are not images, they are interactive equations.

### Element dictionary (`dictionary` field)

The crucial new field. For every element with an `id`, the LLM is asked to also emit an `ElementMeta` carrying:
- `role` — what the element is in the diagram's grammar (e.g., `"hypotenuse"`, `"vertex_A"`).
- `semantic` — a one-line plain-English description (e.g., `"the ladder, 10m"`).
- `position` — a coarse position keyword.
- `spatial_relations` — strings describing relations to other elements.
- `bounds` — pixel bounds.

The teaching agent uses this dictionary to refer to elements by **role**, not raw ID. Instead of `<highlight target="design-5-c3"/>`, the LLM emits `<highlight target="hypotenuse"/>` and the dispatcher resolves it via the spec's `dictionary`. This is what makes diagrams stable across regenerations.

### `prompts.py` — the JSON-direct system prompt

~28 KB, ~370 lines. Teaches Claude to output `DiagramSpec` JSON directly.

Key rules (from reading the prompt):

- **Dark classroom board aesthetic**: default background `#1a1a2e`, default stroke `#e8e8ee`. Neon accent palette: cyan `#7fd4ff`, green `#7fff9f`, pink `#ff7fc6`, amber `#ffe27f`.
- **No text on canvas** (except labels) — Feynman speaks the prose; SVG carries the geometry.
- **All shapes outlined** (`fill: "none"`) except text.
- **One concept per canvas.** No legends, no bullets, no narrative.
- **Comparisons as side-by-side sub-scenes on the same board**, not two panels.
- SVG coordinate system: origin top-left, y grows down.
- 11 element type specs with worked examples.
- Parameter slider syntax + expression syntax.
- Semantic dictionary format (the `dictionary` field).

### `prompts_python.py` — the Python-DSL system prompt

~24 KB, ~360 lines. Alternative authoring path: Claude writes **Python code** using a pre-built `Canvas` object that exports to the same `DiagramSpec` JSON. This trades JSON-fluency for code-fluency, and the LLM tends to produce more precise geometry (especially for right angles, perpendiculars, tangents, intersections) because it can use the helper functions.

In scope when Claude executes:
- `canvas` — a 900×650 `Canvas` instance with transparent background.
- `math` module.
- Helpers: `midpoint(p1, p2)`, `polar(center, radius, angle_deg)`, `perpendicular_to(p1, p2, base, length, side)`, `parallel_at_distance(p1, p2, base, distance, side)`, `intersect(line1, line2)`, `tangent_to(circle, point)`.
- Canvas methods: `add_line`, `add_rect`, `add_circle`, `add_text`, `add_arrow`, `add_ellipse`, `add_arc`, `add_path`, `add_latex`, `add_group`, `add_graph`.

The code is executed in the main backend's `visuals/sandbox.py` (AST whitelist, no imports, 2-second timeout). `canvas.to_dict()` returns the `DiagramSpec` dict.

### `requirements.txt`

```
fastapi
uvicorn
anthropic
pydantic
python-dotenv
```

Five deps. Minimal.

---

## 2. Frontend — `design_agent/frontend/`

Standalone React app on port 3001 (set by `PORT=3001 react-scripts start` in `package.json`). Uses Create React App (not Vite). This is one of the older subprojects.

### `package.json` key deps

| Dep | Purpose |
|---|---|
| `react@^18.2`, `react-dom@^18.2`, `react-scripts@5.0.1` | CRA scaffolding. |
| `@visx/{axis,grid,group,scale,shape,text}@^3.12` | Axis + grid + scale + curve rendering for `GraphElement`. |
| `katex@^0.16` | LaTeX rendering for `SvgLatex` elements (HTML overlay, not foreignObject). |
| `d3@^7.8` | Pulled in but mainly visx is used. |

### `src/App.js` — top-level UI

State:

```js
const [prompt, setPrompt]                = useState("");
const [model, setModel]                  = useState("opus");
const [diagramSpec, setDiagramSpec]      = useState(null);
const [loading, setLoading]              = useState(false);
const [error, setError]                  = useState(null);
const [history, setHistory]              = useState([]);
const [showJson, setShowJson]            = useState(false);
```

`<PromptInput>` on the left (textarea, generate button, history list). `<DiagramRenderer spec={diagramSpec}>` on the right. JSON toggle.

App calls the synchronous `POST /api/generate` endpoint (not the streaming `start`/`status` pair). Streaming-aware UI lives in the main Feynman frontend's diagram-lab; this standalone app is for one-shot generation.

### `src/components/DiagramRenderer.jsx` (~452 lines) — the rendering heart

The translator from `DiagramSpec` to live SVG + KaTeX. Read this if you want to understand what specs need to satisfy.

#### Expression evaluation — `evalMathExpr(expr, vars)`

Safely evaluates a string like `"100 + L * sin(theta)"` against the slider variables:

```js
function evalMathExpr(expr, vars) {
  try {
    const keys = Object.keys(vars);
    const values = Object.values(vars);
    const code = `with(Math) { return (${expr}); }`;
    return new Function(...keys, code).apply(null, values);
  } catch { return NaN; }
}
```

Available math symbols: `sin, cos, tan, sqrt, abs, PI, E, log, exp, pow, floor, ceil, min, max, atan2, asin, acos, sinh, cosh, tanh`. `with(Math)` makes them available without prefix.

#### Coordinate resolution — `resolveValue(val, paramValues)`

- If `val` is a number → return it.
- If `val` is a string → `evalMathExpr(val, paramValues)`.
- If NaN → return 0.

`resolvePoint(pt, paramValues)` resolves a `[x, y]` or `{x, y}`.

#### Per-element rendering — `renderElement(el, idx, paramValues)`

Switch on `el.type`:

| Type | Renders as |
|---|---|
| `svg_line`, `svg_rect`, `svg_circle`, `svg_ellipse`, `svg_path` | Native SVG elements with resolved coords. |
| `svg_text` | visx `Text` (supports rotation, anchoring). |
| `svg_arc` | Computed arc path via `arcPath()` helper. Angles in degrees, 0° = 3 o'clock, positive = clockwise. Converted to radians, then SVG `A` path command. |
| `svg_group` | visx `Group` with `transform` + recursive render of children. |
| `svg_arrow` | Line + SVG `<marker>` polygon arrowhead. |
| `svg_latex` | **Skipped here** — rendered separately as HTML overlay (see below). |
| `graph` | `GraphElement` sub-component (visx axes + grid + curves). |

#### Graph rendering — visx integration

For each curve in `el.curves`:
- Build a linear x-scale: `xDomain → [margin.left, width - margin.right]`.
- Build a linear y-scale similarly.
- Sample 200 points across the x-domain.
- For each point, evaluate `curve.expression` with `x` and any `paramValues`.
- Draw a `LinePath` via visx.

Optional grid via `GridRows` + `GridColumns`. Axes via `AxisBottom` + `AxisLeft`.

#### KaTeX overlay

```jsx
{latexElements.map((el, i) => (
  <LatexOverlay key={`latex-${i}`} el={el} paramValues={paramValues} />
))}
```

`LatexOverlay` is **HTML positioned absolute** on top of the SVG (not `<foreignObject>`, which has cross-browser quirks). KaTeX renders to a string via `katex.renderToString(tex, {throwOnError: false, displayMode: false})`, then injected via `dangerouslySetInnerHTML`. `pointerEvents: "none"`.

It also substitutes `{{param_name}}` placeholders in the LaTeX with current slider values, so equations are live too.

#### Slider UI

For each `SliderParameter`:

```jsx
<div className="param-slider">
  <label>{p.label || p.name}: <strong>{paramValues[p.name].toFixed(2)}</strong></label>
  <input type="range" min={p.min} max={p.max} step={p.step}
         value={paramValues[p.name]}
         onChange={e => handleParamChange(p.name, parseFloat(e.target.value))} />
</div>
```

On change, update `paramValues` state → re-render → expressions re-evaluate → SVG morphs in real time.

### `src/components/PromptInput.jsx`

Textarea, generate button (disabled if empty or loading), Ctrl+Enter shortcut, history list (clickable to restore a previous prompt + spec). Error display.

### `src/components/elements/LatexBlock.jsx`

Standalone KaTeX block (used elsewhere). 33 lines.

### `src/styles/App.css`

448 lines. Dark theme throughout: background `#1a1a2e`, text `#e0e0e0`, header gradient blue→purple, accent `#533483`. Slider thumb styling. Responsive on mobile.

---

## 3. Main backend integration — `agent/design_bridge.py`

The bridge in the main backend (NOT in design_agent itself) is what production teaching uses. Read this carefully:

```python
# backend/src/feynman/agent/design_bridge.py

# Load prompts directly from the design_agent files (no HTTP)
def _load_system_prompt() -> str:                  # lines 39-54
    path = Path(__file__).parents[5] / "design_agent" / "backend" / "prompts.py"
    src = path.read_text()
    # Extract the SYSTEM_PROMPT = """...""" block via regex
    return _extract_string_assignment(src, "SYSTEM_PROMPT")

def _load_python_system_prompt() -> str:           # lines 57-78
    path = Path(__file__).parents[5] / "design_agent" / "backend" / "prompts_python.py"
    return _extract_string_assignment(src, "SYSTEM_PROMPT_PYTHON")

# Each prompt is cached after first load; cache invalidated if file mtime changes.
```

### The two generation paths

```python
async def generate_design_diagram(prompt, model="sonnet", max_tokens=16000) -> dict:
    """JSON-direct path. The default."""
    # 1. Cache lookup: key = (prompt, mode="direct", provider, model, prompt_mtime, schema_mtime)
    #    Cache is a FIFO of 64 entries (recent specs).
    # 2. Route to _call_anthropic(prompt) or _call_ollama(prompt) per settings.design_agent_provider.
    # 3. _parse_response() extracts JSON, repairs truncation, validates against DiagramSpec.
    # 4. _ensure_dictionary_completeness() auto-fills missing dictionary entries (so backend doesn't choke).
    # 5. Persist to design_agent/generated/<timestamp>_<prompt-slug>.json for audit.
    # 6. Return spec dict.

async def generate_via_python(prompt, model="sonnet", max_tokens=8000) -> dict:
    """Python-DSL path. Selected by _dispatch_mode() when geometric precision is needed."""
    # 1. _call_anthropic_python() with the Python-DSL system prompt.
    # 2. Extract Python code from the response (strip markdown fences if any).
    # 3. execute_python_diagram(code) — calls visuals.sandbox.execute_python(code, imports={...}).
    # 4. canvas.to_dict() → DiagramSpec dict.
    # 5. Cache + persist + return like the JSON path.

def _dispatch_mode(prompt: str) -> Literal["direct", "python"]:
    """
    Regex check for geometric-precision keywords:
      exact angle, exactly, perpendicular, tangent, intersect, parallel, normal,
      bisect, parametric, polar
    + STEM diagram names:
      right triangle, free body, ray diagram, lens, lewis structure
    Match → python. Else → direct.
    """
```

### Provider dispatch

Controlled by `settings.design_agent_provider` (default `"anthropic"`):

| Provider | Method |
|---|---|
| `anthropic` | `AsyncAnthropic().messages.create(model, system, messages, max_tokens)`. Streaming. |
| `ollama` | `POST {ollama_base_url}/api/chat` with `model=settings.design_agent_model`. JSONL streaming. |

### Cache key

`(prompt, mode, provider, model, prompt_file_mtime, schema_file_mtime)`.

Including the file mtimes means: **changing the design prompt invalidates the cache automatically.** This is what makes the standalone design_agent useful — you edit `prompts.py`, restart the FastAPI worker, and every new diagram regenerates fresh while old cached ones remain (you can compare side by side).

### Call sites

| Caller | File | Tool / context |
|---|---|---|
| `tools.py:draw_design_diagram` | `agent/tools.py:1556-1757` | LLM tool emits the call. |
| `tools.py:modify_design_diagram` | `agent/tools.py:1759-1912` | Mutates a cached spec. |
| `anticipation.py:warm_for_concept` | `agent/anticipation.py:423, 590` | Pre-generates expected diagrams in the background. |

---

## 4. Precompute pipeline integration

Two patterns, depending on the phase:

### Pattern A: verbatim prompt copy

`data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/enrichment/diagrams.py` (~360 lines) carries a **verbatim copy** of `design_agent/backend/prompts.py:SYSTEM_PROMPT`. The header reads:

> DO NOT EDIT — synced VERBATIM from design_agent/backend/prompts.py.
> If the canonical design_agent prompt changes, copy the new version here.

This is Phase 5's enrichment generator. It calls Claude directly with this prompt for every topic that needs a diagram.

### Pattern B: per-beat generator

`curriculum/enrichment/diagram_spec_generator.py` is the doc-19 path. It uses the kernel's `ConceptTeachingPlan` + `TeachingBeat` types to generate **per-beat** diagrams (one diagram tied to one teaching beat). The system prompt here is more nuanced than the standalone design_agent's — it carries beat context (e.g., "the previous beat introduced concept X; this beat builds on it"). But the schema (`DiagramSpec`) and rendering rules are identical.

Why three places hold "the design prompt"? Because they evolve at different cadences:
- `design_agent/backend/prompts.py` — the playground, where engineers iterate.
- `agent/design_bridge.py` — production live teaching, loads the playground prompt at runtime.
- `data_pre_compute_v2/.../diagrams.py` — production precompute, must be a stable copy because pipeline runs are reproducible.

The verbatim-copy annotation is the discipline that keeps them in sync.

---

## 5. The standalone design_agent's role today

```
                                  ┌────────────────────────────┐
                                  │  Engineer iterating on     │
                                  │  diagram authoring prompts │
                                  └────────────┬───────────────┘
                                               │
                                               │ 1. Edit design_agent/backend/prompts.py
                                               │ 2. Run design_agent/backend & frontend
                                               │ 3. Type a prompt in the textarea
                                               │ 4. Watch Claude generate, render
                                               │ 5. Compare across models (opus/sonnet/haiku)
                                               │ 6. Iterate on the prompt
                                               │ 7. When happy: copy SYSTEM_PROMPT into
                                               │    data_pre_compute_v2/.../diagrams.py
                                               │    (Annotated "VERBATIM" copy)
                                               ▼
                          (Main backend's design_bridge.py reads the file directly,
                           so no copy needed — restart the worker, new prompt is live)
```

The standalone app does **not** participate in production live teaching or production precompute. It is the **prompt-authoring lab**.

> The main backend's port 8000 and the design_agent's port 8000 collide. Don't run them simultaneously. The README at root says so.

---

## 6. DiagramSpec lifecycle — end to end

To make the integration concrete, follow one diagram through the system:

```
1. Live teaching: agent decides "I need a right-triangle diagram for this beat."
2. Agent invokes tool draw_design_diagram(prompt="right triangle with 3-4-5 sides, ladder against wall")
3. backend/src/feynman/agent/tools.py:1556 (the tool body):
   - Generates element_id "design-5" via board_manager.next_id("design")
   - Calls design_bridge.generate_design_diagram(prompt, model="sonnet")
4. design_bridge.py:
   - Check cache. Miss.
   - _dispatch_mode("right triangle ...") → matches "right triangle" → "python" path
   - _call_anthropic_python(prompt, SYSTEM_PROMPT_PYTHON):
       Claude streams Python code using the Canvas DSL
   - execute_python_diagram(code):
       sandbox.execute_python() runs the code in 2s timeout, no imports
       canvas.to_dict() returns the DiagramSpec dict
   - _ensure_dictionary_completeness(spec) fills in any missing ElementMeta entries
   - Persist to design_agent/generated/<timestamp>_right-triangle-3-4-5-...json
   - Return spec dict
5. tools.py:1556 continues:
   - Wraps spec in a DrawDesignDiagramInstruction(spec=spec, element_id="design-5", ...)
   - Calls _publish_visual(instruction)
6. _publish_visual:
   - resolve_placement → (position_x, position_y)
   - board_manager.record() → BoardState._elements["design-5"] = ...
   - audit.record()
   - publish_data over LiveKit topic="visuals"
7. Frontend useVisualChannel onMessage:
   - Decodes JSON, applies instruction
   - Frontend's DesignDiagramContent component receives the spec
   - Calls evalMathExpr / resolveValue per element
   - Renders SVG + KaTeX overlay + slider UI
   - DOM updates
8. Frontend ResizeObserver → BoundsReportPayload → publish topic="bounds"
9. Worker _on_data_received → board_manager.update_bounds → BoardState.update_spatial
   → scene_graph + spatial_solver refresh
10. Next LLM turn:
    Agent prompt includes board snapshot + dictionary entries for "design-5" so the
    agent can refer back: <highlight target="hypotenuse"/> resolves via the dictionary.
```

This is the same path that runs every time the live agent draws a diagram, on every concept beat, throughout the session.

---

## File map summary

```
design_agent/
├── README.md                        (1 line: "Design agent")
├── backend/
│   ├── main.py                      (~310 lines — FastAPI :8000)
│   ├── agent.py                     (~290 lines — DiagramAgent + JSON repair)
│   ├── schema.py                    (~310 lines — DiagramSpec + 11 element types + Graph + ElementMeta)
│   ├── prompts.py                   (~370 lines — JSON-direct SYSTEM_PROMPT)
│   ├── prompts_python.py            (~360 lines — Python-DSL SYSTEM_PROMPT_PYTHON)
│   ├── requirements.txt             (5 deps)
│   └── venv/                        (its own venv — NOT the main backend's)
├── frontend/
│   ├── package.json                 (CRA + visx + katex, port 3001)
│   └── src/
│       ├── index.js                 (7 lines)
│       ├── App.js                   (~120 lines)
│       ├── components/
│       │   ├── PromptInput.jsx      (~78 lines)
│       │   ├── DiagramRenderer.jsx  (~452 lines — the rendering heart)
│       │   └── elements/LatexBlock.jsx  (~33 lines)
│       └── styles/App.css           (~448 lines, dark theme)
└── generated/
    └── <timestamp>_<prompt-slug>.json   (every generated spec persisted here)
```

The main backend's bridge:

```
backend/src/feynman/agent/design_bridge.py  (~640 lines)
```

The precompute pipeline's copy:

```
data_pre_compute_v2/src/lecture_pipeline_v2/curriculum/enrichment/diagrams.py
    └── carries verbatim copy of SYSTEM_PROMPT
```

---

## Reading order for a new engineer

1. This doc.
2. `design_agent/backend/schema.py` — every type, ground truth.
3. `design_agent/backend/prompts.py` first ~50 lines + section headers — feel the design philosophy.
4. `design_agent/frontend/src/components/DiagramRenderer.jsx` — the renderer, especially `evalMathExpr`, `resolvePoint`, `arcPath`, and the per-element switch.
5. `backend/src/feynman/agent/design_bridge.py` — the real production path.
6. (Optional) `prompts_python.py` + `visuals/canvas_dsl.py` + `visuals/sandbox.py` — only if you care about the Python-DSL path.
