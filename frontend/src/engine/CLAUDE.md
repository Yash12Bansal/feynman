# Visual Rendering Engine

Renders visual instructions from the backend onto the classroom screen.

## How It Works

1. Backend sends `VisualFrame` messages over WebSocket
2. Each frame contains a list of `VisualInstruction` objects
3. `renderer.ts` interprets each instruction and draws on the Canvas
4. `Canvas.tsx` manages the HTML5 Canvas element and resize handling

## Supported Instructions

- `clear` — wipe the canvas
- `show_text` — render text
- `draw_diagram` — structured diagrams (planned)
- `show_equation` — LaTeX equations (planned)
- `show_graph` — data visualizations (planned)
- `animate` — animation sequences (planned)
- `highlight` — highlight existing elements (planned)

## Future

The engine will evolve from Canvas 2D to WebGL for richer animations.
