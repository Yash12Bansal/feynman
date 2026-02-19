# Knowledge Module — Per-Student Knowledge Graph

Tracks each student's learning progress, patterns, and misconceptions.

## Design Principle

**Enhancement, NOT dependency.** The system must work beautifully without any knowledge graph data. When data exists, it makes teaching better.

"Graceful when uncertain, delightful when accurate."

## Layers

1. **Concept mastery map** — what the student knows/doesn't know per subject
2. **Learning pattern profile** — what teaching styles work for this student (transfers across subjects)
3. **Session history** — record of all interactions

## Implementation

- **PostgreSQL** with abstract repository pattern (allows Neo4j swap later)
- **Per-subject graphs** with shared student profile
- Most students rarely ask doubts → graph is naturally sparse → system handles sparse data well
