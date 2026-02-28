# Visuals Module — Visual Instruction Engine

Backend generates **typed visual instructions**, frontend renders them. Clean contract.

## How It Works

1. Teaching agent decides to show something visual (diagram, equation, graph)
2. Agent creates a typed instruction (e.g., `ShowEquationInstruction(latex="E=mc^2")`)
3. Instruction is serialized to JSON and published via LiveKit data channel (topic="visuals")
4. Frontend receives the instruction and renders it

## Architecture: Discriminated Union

`VisualInstruction` is a Pydantic discriminated union of all instruction types, tagged by `type`:

```python
from feynman.visuals.instructions import VisualInstruction
from feynman.visuals.schemas import ShowEquationInstruction

# Create typed instruction
instr = ShowEquationInstruction(latex=r"\frac{-b \pm \sqrt{b^2-4ac}}{2a}", label="Quadratic")

# Parse from wire format
parsed = TypeAdapter(VisualInstruction).validate_json(raw_json)
```

Wire format is **flattened** — no nested `payload`:

```json
{ "type": "show_equation", "latex": "E = mc^2", "label": "Einstein" }
```

## Files

| File              | Purpose                                                       |
| ----------------- | ------------------------------------------------------------- |
| `schemas.py`      | All typed instruction models + sub-models (enums, nodes, etc) |
| `instructions.py` | `VisualInstruction` discriminated union type + re-exports     |
| `protocol.py`     | `VisualFrame` for future batching                             |

## Instruction Types

| Type            | Model                     | Required Fields                     |
| --------------- | ------------------------- | ----------------------------------- |
| `clear`         | `ClearInstruction`        | (none — clears everything)          |
| `show_text`     | `ShowTextInstruction`     | `text`                              |
| `show_equation` | `ShowEquationInstruction` | `latex`                             |
| `draw_diagram`  | `DrawDiagramInstruction`  | `description` OR `nodes`            |
| `show_graph`    | `ShowGraphInstruction`    | `graph_type` + `series`/`functions` |
| `highlight`     | `HighlightInstruction`    | `target_id`                         |

All instructions share optional `element_id` (for incremental rendering identity) and `duration_ms` (for animation timing).

## Contract

Defined in `contracts/visuals.schema.json` (auto-generated from Pydantic models) and mirrored:

- Backend: `feynman.visuals.schemas` (source of truth)
- Frontend: `frontend/src/types/visuals.ts`
