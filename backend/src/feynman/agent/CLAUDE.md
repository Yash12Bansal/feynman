# Agent Module — Teaching State Machine

This is the **core IP** of Feynman.

## Architecture

The teaching session is modeled as a tree/graph (like git):

- **Main branch** = linear sequence of concepts for today's lesson
- **Doubt branches** = spawn when a student asks a question
- **Nested doubts** = branches from branches

Implementation: async state machine with a **stack** of `BranchContext` objects.

- `push_branch()` to handle a doubt (push onto stack)
- `pop_branch()` to return to the parent branch (pop from stack)
- The stack always preserves the return path

## Files

| File               | Purpose                                                        |
| ------------------ | -------------------------------------------------------------- |
| `state_machine.py` | `TeachingStateMachine` class — stack-based async state machine |
| `states.py`        | `TeachingState` enum — all possible states                     |
| `prompts.py`       | System prompts for the LLM                                     |
| `tools.py`         | LLM function tools (draw, show equation, etc.)                 |

## Key Decision: NOT LangGraph

We use a custom async state machine, not LangGraph. Reasons:

- Stack-based branching is a natural fit, zero overhead
- Full control over the teaching flow
- Can wrap as a LangGraph node later if ever needed
