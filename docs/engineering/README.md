# Feynman Engineering Documentation

End-to-end engineering deep-dive of the Feynman AI teaching agent. Read these in order if you're new, or jump to the module you care about.

**Last verified against branch:** `feat/unify_boardstate` · **Date:** 2026-05-28

## Documents

| # | Doc | Scope | Read if you... |
|---|---|---|---|
| 00 | [System Overview](./00-system-overview.md) | The whole map — processes, modules, critical paths, two playback modes | ...are new and want the 30-minute orientation. |
| 01 | [Precompute Pipeline](./01-precompute-pipeline.md) | `data_pre_compute_v2/` — 12-phase offline pipeline turning PDFs into Neo4j + audio + diagrams | ...want to ingest a textbook, understand the manifest, or modify a phase. |
| 02 | [Backend FastAPI](./02-backend-fastapi.md) | `backend/` HTTP layer — session lifecycle, DB, Redis, knowledge stubs | ...want to add an HTTP endpoint or understand session state. |
| 03 | [Teaching State Machine](./03-teaching-state-machine.md) | `backend/src/feynman/agent/` + `visuals/` — the core IP. Stack-based branching, 40+ tools, unified board state | ...want to add a teaching tool, change behavior in a state, or understand the agent's decision loop. |
| 04 | [LiveKit Agent Worker](./04-livekit-agent-worker.md) | `backend/src/feynman/livekit/` — real-time STT→LLM→TTS, action tags, lecture-mode doubt delivery | ...want to understand the audio pipeline or the worker process. |
| 05 | [Teaching Kernel](./05-feynman-teaching-kernel.md) | `feynman_teaching_kernel/` — shared planning models, prompts, validators | ...want to change planning behavior across live + recorded teaching. |
| 06 | [Design Agent](./06-design-agent.md) | `design_agent/` + main backend's `design_bridge.py` — diagram authoring | ...want to tune diagram aesthetics, A/B prompts, or understand DiagramSpec. |
| 07 | [Contracts & Protocols](./07-contracts-and-protocols.md) | `contracts/visuals.schema.json` ↔ Pydantic ↔ TypeScript + LiveKit data channels | ...want to add an instruction type or understand the wire format. |
| 08 | [Frontend Architecture](./08-frontend-architecture.md) | `frontend/` — React 19, screens, engine, split-board, lecture viewer | ...want to add a screen or change rendering. |
| 09 | [End-to-end Trace](./09-end-to-end-trace.md) | One concrete student session through every module | ...want to see how a real session flows from click to resolution. |
| 10 | [Data Stores](./10-data-stores.md) | Postgres / Redis / Neo4j / filesystem / in-memory teaching context | ...want to understand persistence, schema, or production readiness. |
| 11 | [Precompute Playback Flow](./11-precompute-playback-flow.md) | Deep file:line trace of lecture playback — the sync model, event coverage, render path, known issues | ...want to know exactly how a lecture plays and stays in sync. |
| 12 | [Ask Feynman Flow](./12-ask-feynman-flow.md) | Deep file:line trace of the doubt pipeline — capture → classify → plan → match → deliver → resume, sync analysis, known issues | ...want to know how Ask Feynman works and where board/planning sync is weak. |
| 13 | [Redundant-Code Audit](./13-redundant-code-audit.md) | Inventory of code not used by the three active pipelines + a sequenced deletion plan | ...want to remove the parked interactive subsystem and other dead code. |
| 14 | [GCP Deployment & Operations](./14-gcp-deployment-and-operations.md) | How the LIVE product is deployed on GCP (`feynman-basic`) — every resource + networking, request flows, build/deploy flow, **all incidents** (incl. the lectures outage + root causes) + the ops runbook | ...are running, debugging, redeploying, or onboarding to the production system. |

> **Active-product note:** the product today is precompute teaching + Ask Feynman (docs 11, 12). The **interactive live-teaching mode** described in docs 03–04 (state machine, ~40 tools, board manager, anticipation) is **parked** — see doc 13 for what that makes redundant. Docs 03–04 remain accurate descriptions of that subsystem, but it is not in the active runtime path.

## Reading orders

### "I have 30 minutes"

[00-system-overview.md](./00-system-overview.md) → [09-end-to-end-trace.md](./09-end-to-end-trace.md).

### "I want the exact runtime flow of the active product"

[00](./00-system-overview.md) → [11-precompute-playback-flow.md](./11-precompute-playback-flow.md) → [12-ask-feynman-flow.md](./12-ask-feynman-flow.md). These two are the deepest file:line traces of what actually runs today.

### "I want to delete dead code"

[13-redundant-code-audit.md](./13-redundant-code-audit.md) (read Part C catches + Part D runbook), with [03-teaching-state-machine.md](./03-teaching-state-machine.md) + [04-livekit-agent-worker.md](./04-livekit-agent-worker.md) as context for the parked subsystem being removed.

### "I want to understand teaching"

00 → [05-feynman-teaching-kernel.md](./05-feynman-teaching-kernel.md) → [03-teaching-state-machine.md](./03-teaching-state-machine.md) → [04-livekit-agent-worker.md](./04-livekit-agent-worker.md) → 09.

### "I want to understand the visual stack"

00 → [06-design-agent.md](./06-design-agent.md) → [07-contracts-and-protocols.md](./07-contracts-and-protocols.md) → [08-frontend-architecture.md](./08-frontend-architecture.md) → 09.

### "I want to understand the offline pipeline"

00 → [01-precompute-pipeline.md](./01-precompute-pipeline.md) → [10-data-stores.md](./10-data-stores.md) → [05-feynman-teaching-kernel.md](./05-feynman-teaching-kernel.md).

### "I'm shipping this to production" / "it's live and I'm operating it"

[14-gcp-deployment-and-operations.md](./14-gcp-deployment-and-operations.md) is the authoritative deploy + ops + incident reference for the live system. For deeper context: 00 → [10-data-stores.md](./10-data-stores.md) §11 → [02-backend-fastapi.md](./02-backend-fastapi.md) → [04-livekit-agent-worker.md](./04-livekit-agent-worker.md) → 09 §"Critical timings".

## Conventions in these docs

- **File references** use `path:line_no` so you can paste into your editor's go-to-line. The branch is `feat/unify_boardstate`; line numbers drift over time.
- **Code blocks** quote real code where it best communicates intent. Sometimes light editing for readability — see the file for the canonical version.
- **ASCII diagrams** prefer monospace clarity over prettier rendered diagrams; you can read them in a terminal `less`.
- **Cross-references** are explicit (e.g., "see 03 §6"). Use them; the docs compose.
- **"TL;DR"** at the top of each doc is honest about scope, not marketing.
- **No emojis** because the engineering content is dense enough.

## Maintenance

If you change architectural behavior, update the matching doc(s) in the same PR. The docs are designed to be opened directly while reading code, so a stale doc is worse than no doc.

If a doc grows past ~1500 lines, split it. The current docs target 400-1200 lines each.

If you find a `file_path:line_no` reference that's drifted, fix it as you go — these references are the most fragile thing in the docs and the most useful when accurate.

## Out-of-scope (not covered here)

- Strategy and product thesis: see `docs/strategy/` and `memory/MEMORY.md`.
- In-progress design proposals: see `docs/design/`.
- Per-module CLAUDE.md files (for AI assistants working on each module): see `backend/CLAUDE.md`, `frontend/CLAUDE.md`, etc.
- Day-to-day "what changed recently": `git log` is authoritative; these docs explain *how things work*, not *what changed*.
