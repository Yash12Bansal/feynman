# Visuals Module — Visual Instruction Engine

Backend generates **typed visual instructions**, frontend renders them. Clean contract.

## How It Works

1. Teaching agent decides to show something visual (diagram, equation, graph)
2. Agent emits a `VisualInstruction` with a type and payload
3. Instructions are batched into `VisualFrame`s
4. Frames are streamed to frontend over WebSocket
5. Frontend Canvas/WebGL renderer draws them

## Types

- `VisualType.DRAW_DIAGRAM` — structured diagram data
- `VisualType.SHOW_EQUATION` — LaTeX equation
- `VisualType.SHOW_TEXT` — text on the board
- `VisualType.SHOW_GRAPH` — data visualization
- `VisualType.ANIMATE` — animation sequence
- `VisualType.HIGHLIGHT` — highlight existing element
- `VisualType.CLEAR` — clear the board

## Contract

The visual protocol is defined in `contracts/visuals.schema.json` (JSON Schema) and mirrored on both sides:

- Backend: `feynman.visuals.instructions` + `feynman.visuals.protocol`
- Frontend: `src/types/visuals.ts`
