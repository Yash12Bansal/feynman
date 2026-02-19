# Frontend — Feynman

React 19 + TypeScript + Vite. The classroom screen rendered on a big display.

## Structure

| Directory  | Purpose                                            |
| ---------- | -------------------------------------------------- |
| `screens/` | Full-screen views (ClassroomScreen, WaitingScreen) |
| `engine/`  | Canvas/WebGL visual rendering engine               |
| `livekit/` | LiveKit client integration (room, audio)           |
| `hooks/`   | React hooks for session, state                     |
| `types/`   | TypeScript types (mirrors backend protocol)        |
| `lib/`     | API client, config                                 |
| `styles/`  | Global CSS                                         |

## Commands

```bash
pnpm dev          # Dev server on :5173
pnpm build        # Production build
pnpm lint         # ESLint
pnpm format       # Prettier
pnpm test         # Vitest
```

## Conventions

- **Named exports only** — no default exports (except pages if needed)
- **Functional components + hooks** — no class components
- **Vitest + Testing Library** for testing
- Visual types in `types/visuals.ts` must stay in sync with `contracts/visuals.schema.json` and backend
