# Visual Rendering Engine

React component architecture for rendering visual instructions on the classroom screen.

## Architecture (Phase 2+)

The engine uses **HTML-first rendering** — HTML divs for layout/cards, with SVG and Canvas embedded inside specific cards that need them.

```
<VisualScene instructions={[...]}>
  <ElementRegistryProvider>
    <div.scene-viewport>
      <div.scene-content>
        <VisualCard> → <InstructionSwitch> → <TextContent>
        <VisualCard> → <InstructionSwitch> → <EquationContent>
        <VisualCard> → <InstructionSwitch> → <DiagramContent>
        ...
      </div>
    </div>
    <HighlightOverlay />  (headless — applies CSS to target card)
  </ElementRegistryProvider>
</VisualScene>
```

## File Map

| File                              | Purpose                                                               |
| --------------------------------- | --------------------------------------------------------------------- |
| `VisualScene.tsx`                 | Root component. Separates elements from effects, manages auto-scroll. |
| `VisualScene.css`                 | Scene/card/highlight styles. CSS custom properties from theme.        |
| `VisualCard.tsx`                  | Card wrapper with accent stripe. Registers in element registry.       |
| `InstructionSwitch.tsx`           | Dispatches `instruction.type` to content component.                   |
| `elements.ts`                     | Element registry (React Context + `useRef<Map>`). No re-renders.      |
| `theme.ts`                        | Design tokens (colors, layout, fonts) + CSS variable injection.       |
| `content/TextContent.tsx`         | `show_text` — title + body with style variants.                       |
| `content/EquationContent.tsx`     | `show_equation` — KaTeX rendering + GSAP animation.                   |
| `content/StepEquationContent.tsx` | `step_equation` — multi-step equation solve with progressive reveal.  |
| `content/DiagramContent.tsx`      | `draw_diagram` — SVG renderer with auto-layout + GSAP animation.      |
| `layout/diagram-layout.ts`        | Pure layout engine (dagre, circular, radial, two-column). No React.   |
| `content/GraphContent.tsx`        | `show_graph` — placeholder (Chart.js in Phase 6).                     |
| `content/HighlightOverlay.tsx`    | Headless. Applies CSS highlight class to target element via registry. |

## Deprecated Files

| File          | Status                                                                   |
| ------------- | ------------------------------------------------------------------------ |
| `Canvas.tsx`  | Replaced by `VisualScene.tsx`. Kept for rollback until Phase 3 verified. |
| `renderer.ts` | Replaced. Design token source during migration — now use `theme.ts`.     |

## Key Patterns

- **Element registry**: VisualCard registers on mount, unregisters on unmount. HighlightOverlay and future GSAP animations look up targets by ID.
- **Incremental rendering**: React reconciliation handles it. Array grows → new cards append. Existing DOM untouched.
- **`clear` instruction**: Handled in `useVisualChannel` (data layer), not in the renderer. Resets or filters the instructions array.
- **Highlight**: CSS-based via `data-highlight` attribute. Animations defined in `VisualScene.css`.
- **Theme**: Single source of truth in `theme.ts`. Injected as CSS custom properties on the viewport.

## Adding a New Visual Type

1. Add TypeScript types in `types/visuals.ts`
2. Create `content/FooContent.tsx`
3. Add case to `InstructionSwitch.tsx`
4. Add accent color to `TYPE_ACCENT` in `theme.ts`
5. Add `data-type` CSS rules in `VisualScene.css` if needed
