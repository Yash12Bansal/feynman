# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """Backend notebook state reconstructor — Phase 5b.

# Walks the session audit's ``routing`` events and mirrors the frontend
# split-board adapter (``useSplitBoardState.ts``) on the backend. The
# reconstructed state is rendered into the LLM's system prompt on every
# rebuild so the agent sees what it has already written and can reason
# coherently across turns — no blind duplicate equations, no wrong
# strikethrough targets, no forgotten align groups.

# Source of truth: ``tc.audit.events_for("routing")``. Audit records for
# notebook-panel instructions include a ``content`` dict with the full
# Pydantic payload (added in ``_publish_visual``). Non-notebook records
# are ignored.

# Mirrors (intentionally) the shape of ``buildNotebookState`` on the
# frontend so prompt output and rendered UI stay in lockstep. Any
# divergence between this file and ``useSplitBoardState.ts`` is a bug.
# """

# from __future__ import annotations

# from dataclasses import dataclass, field
# from typing import Any

# from feynman.agent.session_audit import SessionAudit

# # Notebook-panel tools — matches INSTRUCTION_TYPE_TO_PANEL in tools.py.
# # Duplicated here (not imported) to keep this module import-safe from
# # prompts.py without pulling the full livekit/tools dependency graph.
# NOTEBOOK_TOOLS: frozenset[str] = frozenset(
#     {
#         "show_text",
#         "show_equation",
#         "step_equation",
#         "show_graph",
#         "write_equation",
#         "write_step",
#         "write_text",
#         "write_section",
#         "write_answer",
#         "strikethrough",
#         "new_page",
#     }
# )

# _PREVIEW_LEN = 60


# @dataclass
# class NotebookEntry:
#     """One reconstructed notebook entry — matches the frontend `NotebookEntry` shape."""

#     page: int
#     id: str
#     kind: str  # equation | step | text | section_header | key_point | answer | graph
#     content: str
#     align_group: str | None = None
#     indent: int = 0
#     struck: bool = False
#     carried_forward: bool = False


# @dataclass
# class NotebookState:
#     """Reconstructed notebook state at a point in time."""

#     pages: list[list[NotebookEntry]] = field(
#         default_factory=lambda: [[]]
#     )
#     struck_ids: set[str] = field(default_factory=set)

#     @property
#     def current_page(self) -> int:
#         return len(self.pages)

#     @property
#     def current_entries(self) -> list[NotebookEntry]:
#         return self.pages[-1] if self.pages else []

#     @property
#     def active_align_groups(self) -> list[str]:
#         """align_groups in use on the current page, sorted for stable output."""
#         groups: set[str] = set()
#         for entry in self.current_entries:
#             if entry.align_group:
#                 groups.add(entry.align_group)
#         return sorted(groups)


# def reconstruct(audit: SessionAudit) -> NotebookState:
#     """Replay the audit's routing events into live notebook state.

#     Walks events in chronological order (the order ``_publish_visual``
#     recorded them). For each notebook tool call, appends reconstructed
#     entries to the current page; ``new_page`` pushes a fresh page;
#     ``strikethrough`` accumulates into a global struck-id set applied
#     across all pages before carry-forward synthesis (so carried copies
#     reflect the original's live struck state).

#     Carried copies use derived id ``{original.id}__carried__p{N}`` —
#     matching the frontend adapter exactly — so they're inert to
#     strikethrough targeting.
#     """
#     state = NotebookState()
#     # Parallel list: carry_forward_ids provided on each `new_page`, indexed
#     # by page (index 0 → page 1, index 1 → page 2, …). Page 1 never carries
#     # from anywhere, so its slot is always empty.
#     carry_per_page: list[list[str]] = [[]]

#     for evt in audit.events_for("routing"):
#         tool = evt.metadata.get("tool")
#         if tool not in NOTEBOOK_TOOLS:
#             continue
#         content: dict[str, Any] = evt.metadata.get("content") or {}
#         element_id: str = evt.metadata.get("element_id") or content.get(
#             "element_id", ""
#         )

#         if tool == "new_page":
#             ids = list(content.get("carry_forward_ids") or [])
#             state.pages.append([])
#             carry_per_page.append(ids)
#             continue

#         if tool == "strikethrough":
#             target = content.get("target_id")
#             if target:
#                 state.struck_ids.add(target)
#             continue

#         entries = _tool_to_entries(
#             tool=tool,
#             content=content,
#             element_id=element_id,
#             page=state.current_page,
#         )
#         state.pages[-1].extend(entries)

#     # Apply strike globally so carried copies reflect resolved state.
#     if state.struck_ids:
#         for page in state.pages:
#             for entry in page:
#                 if entry.id in state.struck_ids:
#                     entry.struck = True

#     # Synthesize carried copies at the top of pages that requested them.
#     for i in range(1, len(state.pages)):
#         ids = carry_per_page[i] if i < len(carry_per_page) else []
#         if not ids:
#             continue
#         prev = state.pages[i - 1]
#         carried: list[NotebookEntry] = []
#         page_num = i + 1
#         for cid in ids:
#             src = next((e for e in prev if e.id == cid), None)
#             if src is None:
#                 continue
#             carried.append(
#                 NotebookEntry(
#                     page=page_num,
#                     id=f"{src.id}__carried__p{page_num}",
#                     kind=src.kind,
#                     content=src.content,
#                     align_group=src.align_group,
#                     indent=src.indent,
#                     struck=src.struck,
#                     carried_forward=True,
#                 )
#             )
#         if carried:
#             state.pages[i] = carried + state.pages[i]

#     return state


# def render_prompt_section(
#     state: NotebookState,
#     history_pages: int = 1,
# ) -> str:
#     """Render a compact notebook state block for the LLM system prompt.

#     Shows the current page in full + a short summary of the last
#     ``history_pages`` previous pages. Empty notebook yields a short
#     note. Designed to be appended to the existing board-state section.
#     """
#     if not state.current_entries and state.current_page == 1:
#         return (
#             "\n## Notebook State\n\n"
#             "The notebook is empty. Call `write_section`, `write_equation`, "
#             "`write_step`, `write_text`, or `write_answer` to begin. The "
#             "students see entries appear one after another down the page.\n"
#         )

#     lines: list[str] = ["\n## Notebook State\n"]
#     lines.append(f"**Current page**: {state.current_page}")

#     if state.active_align_groups:
#         groups = ", ".join(state.active_align_groups)
#         lines.append(
#             f"**Active align_groups on this page**: {groups} — reuse these "
#             "when writing related equations so they line up at `=`."
#         )

#     if state.struck_ids:
#         struck = ", ".join(sorted(state.struck_ids))
#         lines.append(
#             f"**Already struck (do NOT strike again)**: {struck}"
#         )

#     lines.append("")

#     if history_pages > 0 and len(state.pages) > 1:
#         start = max(0, len(state.pages) - 1 - history_pages)
#         for i in range(start, len(state.pages) - 1):
#             pnum = i + 1
#             page = state.pages[i]
#             if not page:
#                 continue
#             lines.append(f"**Page {pnum} (summary):**")
#             for entry in page:
#                 lines.append(_fmt_entry(entry))
#             lines.append("")

#     lines.append(f"**Page {state.current_page} (current):**")
#     if not state.current_entries:
#         lines.append("_(blank page — nothing written yet)_")
#     else:
#         for entry in state.current_entries:
#             lines.append(_fmt_entry(entry))

#     lines.append("")
#     lines.append(
#         "When referencing an existing entry — `strikethrough(target_id=...)` "
#         "or `new_page(carry_forward_ids=[...])` — use the `id` in brackets."
#     )
#     return "\n".join(lines) + "\n"


# # ── internals ─────────────────────────────────────────────────────────


# def _tool_to_entries(
#     tool: str,
#     content: dict[str, Any],
#     element_id: str,
#     page: int,
# ) -> list[NotebookEntry]:
#     """Map a single notebook tool call to one or more reconstructed entries.

#     Mirrors ``instructionToNotebookEntries`` in ``useSplitBoardState.ts``.
#     Keep these two in lockstep — any divergence is a bug the prompt won't
#     catch because the LLM sees only this side.
#     """
#     base_id = element_id or f"{tool}-?"

#     def eid(suffix: str = "") -> str:
#         if suffix and element_id:
#             return f"{element_id}-{suffix}"
#         if suffix:
#             return f"{base_id}-{suffix}"
#         return base_id

#     if tool == "show_text":
#         text = content.get("text", "")
#         title = content.get("title", "")
#         style = content.get("style", "default")
#         if style == "key_point":
#             return [
#                 NotebookEntry(
#                     page=page, id=eid(), kind="key_point", content=_preview(text)
#                 )
#             ]
#         if style == "definition":
#             out: list[NotebookEntry] = []
#             if title:
#                 out.append(
#                     NotebookEntry(
#                         page=page,
#                         id=eid("header"),
#                         kind="section_header",
#                         content=title,
#                     )
#                 )
#             out.append(
#                 NotebookEntry(
#                     page=page, id=eid("body"), kind="text", content=_preview(text)
#                 )
#             )
#             return out
#         if style == "example":
#             return [
#                 NotebookEntry(
#                     page=page,
#                     id=eid(),
#                     kind="text",
#                     content=_preview(text),
#                     indent=1,
#                 )
#             ]
#         return [
#             NotebookEntry(
#                 page=page, id=eid(), kind="text", content=_preview(text)
#             )
#         ]

#     if tool == "show_equation":
#         return [
#             NotebookEntry(
#                 page=page,
#                 id=eid(),
#                 kind="equation",
#                 content=_preview(content.get("latex", "")),
#             )
#         ]

#     if tool == "step_equation":
#         out = []
#         title = content.get("title", "")
#         if title:
#             out.append(
#                 NotebookEntry(
#                     page=page,
#                     id=eid("header"),
#                     kind="section_header",
#                     content=title,
#                 )
#             )
#         steps = content.get("steps") or []
#         for i, step in enumerate(steps):
#             latex = step.get("latex", "") if isinstance(step, dict) else ""
#             out.append(
#                 NotebookEntry(
#                     page=page,
#                     id=eid(f"step-{i}"),
#                     kind="equation",
#                     content=_preview(latex),
#                     indent=1,
#                 )
#             )
#         return out

#     if tool == "show_graph":
#         title = content.get("title", "") or "graph"
#         return [
#             NotebookEntry(
#                 page=page, id=eid(), kind="graph", content=_preview(title)
#             )
#         ]

#     if tool == "write_equation":
#         align = content.get("align_group")
#         return [
#             NotebookEntry(
#                 page=page,
#                 id=eid(),
#                 kind="equation",
#                 content=_preview(content.get("latex", "")),
#                 align_group=align if align else None,
#                 indent=_clamp_indent(content.get("indent")),
#             )
#         ]

#     if tool == "write_step":
#         number = content.get("number")
#         text = content.get("text", "")
#         prefix = f"({number}) " if number else ""
#         return [
#             NotebookEntry(
#                 page=page,
#                 id=eid(),
#                 kind="step",
#                 content=_preview(prefix + text),
#                 indent=_clamp_indent(content.get("indent")),
#             )
#         ]

#     if tool == "write_text":
#         style = content.get("style", "default")
#         kind = "key_point" if style == "key_point" else "text"
#         return [
#             NotebookEntry(
#                 page=page,
#                 id=eid(),
#                 kind=kind,
#                 content=_preview(content.get("text", "")),
#                 indent=_clamp_indent(content.get("indent")),
#             )
#         ]

#     if tool == "write_section":
#         return [
#             NotebookEntry(
#                 page=page,
#                 id=eid(),
#                 kind="section_header",
#                 content=content.get("title", ""),
#             )
#         ]

#     if tool == "write_answer":
#         latex = content.get("latex")
#         text = content.get("text")
#         return [
#             NotebookEntry(
#                 page=page,
#                 id=eid(),
#                 kind="answer",
#                 content=_preview(latex or text or ""),
#             )
#         ]

#     return []


# def _preview(s: str, n: int = _PREVIEW_LEN) -> str:
#     s = (s or "").strip()
#     if len(s) <= n:
#         return s
#     return s[: n - 1] + "…"


# def _clamp_indent(raw: Any) -> int:
#     try:
#         n = int(raw)
#     except (TypeError, ValueError):
#         return 0
#     return max(0, min(3, n))


# def _fmt_entry(entry: NotebookEntry) -> str:
#     flags: list[str] = []
#     if entry.struck:
#         flags.append("STRUCK")
#     if entry.carried_forward:
#         flags.append("CARRIED")
#     if entry.kind == "answer":
#         flags.append("BOXED")
#     flag_str = f"  [{' '.join(flags)}]" if flags else ""
#     align = f"  align={entry.align_group}" if entry.align_group else ""
#     indent_str = f"  indent={entry.indent}" if entry.indent else ""
#     kind_label = entry.kind.replace("_", " ").upper().ljust(10)
#     return f"- [{entry.id}] {kind_label} {entry.content}{align}{indent_str}{flag_str}"
