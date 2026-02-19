# Contracts — Shared Backend/Frontend Schemas

JSON Schema definitions for the visual instruction protocol shared between backend and frontend.

## How It Works

The backend (Python/Pydantic) generates visual instructions. The frontend (TypeScript) renders them. Both sides must agree on the shape of these messages.

This directory contains the **single source of truth** as JSON Schema files. Both sides mirror these types:

| Contract              | Backend                        | Frontend               |
| --------------------- | ------------------------------ | ---------------------- |
| `visuals.schema.json` | `feynman.visuals.instructions` | `src/types/visuals.ts` |

## When Updating

1. Update the JSON Schema file here
2. Update the backend Pydantic models
3. Update the frontend TypeScript types
4. All three must stay in sync
