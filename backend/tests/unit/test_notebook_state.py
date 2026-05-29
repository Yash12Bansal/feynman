# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for the notebook state reconstructor (split-board Phase 5b).

# These exercise `reconstruct` and `render_prompt_section` against synthetic
# SessionAudit logs shaped exactly as `_publish_visual` produces them — tool
# name in metadata["tool"], full payload in metadata["content"].
# """

# from __future__ import annotations

# from typing import Any

# import pytest

# from feynman.agent.notebook import (
#     NOTEBOOK_TOOLS,
#     NotebookState,
#     reconstruct,
#     render_prompt_section,
# )
# from feynman.agent.session_audit import SessionAudit


# def _record(
#     audit: SessionAudit,
#     tool: str,
#     content: dict[str, Any] | None = None,
#     element_id: str | None = None,
# ) -> None:
#     """Shape an audit record exactly like `_publish_visual` does."""
#     meta = {
#         "tool": tool,
#         "element_id": element_id or (content or {}).get("element_id", "") or "",
#         "zone": "none",
#         "concept_index": -1,
#     }
#     if content is not None:
#         meta["content"] = content
#     audit.record("routing", "tool_call", f"{tool} zone=none", **meta)


# @pytest.fixture
# def audit() -> SessionAudit:
#     return SessionAudit()


# def test_empty_audit_yields_blank_notebook(audit: SessionAudit) -> None:
#     state = reconstruct(audit)
#     assert isinstance(state, NotebookState)
#     assert state.current_page == 1
#     assert state.current_entries == []
#     section = render_prompt_section(state)
#     assert "notebook is empty" in section.lower()


# def test_single_write_equation_creates_one_entry(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "eq-1", "latex": "F = m a"},
#     )
#     state = reconstruct(audit)
#     assert len(state.current_entries) == 1
#     entry = state.current_entries[0]
#     assert entry.id == "eq-1"
#     assert entry.kind == "equation"
#     assert entry.content == "F = m a"


# def test_write_equation_with_align_group_surfaces(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "write_equation",
#         {
#             "type": "write_equation",
#             "element_id": "eq-1",
#             "latex": "F = m a",
#             "align_group": "g1",
#             "indent": 1,
#         },
#     )
#     state = reconstruct(audit)
#     e = state.current_entries[0]
#     assert e.align_group == "g1"
#     assert e.indent == 1
#     assert state.active_align_groups == ["g1"]


# def test_non_notebook_tool_is_ignored(audit: SessionAudit) -> None:
#     """Slide/reference tools must not bleed into notebook state."""
#     _record(
#         audit,
#         "draw_design_diagram",
#         {"type": "draw_design_diagram", "element_id": "d1"},
#     )
#     state = reconstruct(audit)
#     assert state.current_entries == []


# def test_new_page_pushes_fresh_page(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "eq-1", "latex": "x = 1"},
#     )
#     _record(audit, "new_page", {"type": "new_page", "carry_forward_ids": []})
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "eq-2", "latex": "y = 2"},
#     )
#     state = reconstruct(audit)
#     assert state.current_page == 2
#     # Page 1 is retained; page 2 is current and has only eq-2.
#     assert len(state.pages) == 2
#     assert len(state.current_entries) == 1
#     assert state.current_entries[0].id == "eq-2"


# def test_strikethrough_marks_entry_across_pages(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "bad", "latex": "wrong"},
#     )
#     _record(
#         audit,
#         "strikethrough",
#         {"type": "strikethrough", "target_id": "bad"},
#     )
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "good", "latex": "right"},
#     )
#     state = reconstruct(audit)
#     bad = next(e for e in state.current_entries if e.id == "bad")
#     good = next(e for e in state.current_entries if e.id == "good")
#     assert bad.struck is True
#     assert good.struck is False
#     assert "bad" in state.struck_ids


# def test_carry_forward_synthesizes_copy(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "eq-1", "latex": "F = m a"},
#     )
#     _record(
#         audit,
#         "new_page",
#         {"type": "new_page", "carry_forward_ids": ["eq-1"]},
#     )
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "eq-2", "latex": "a = 5"},
#     )
#     state = reconstruct(audit)
#     # Page 2 starts with the carried copy, then the new entry.
#     assert len(state.current_entries) == 2
#     carried = state.current_entries[0]
#     assert carried.carried_forward is True
#     assert carried.id == "eq-1__carried__p2"
#     assert carried.content == "F = m a"
#     assert state.current_entries[1].id == "eq-2"
#     assert state.current_entries[1].carried_forward is False


# def test_carry_forward_reflects_struck_state(audit: SessionAudit) -> None:
#     """Carried copies mirror the original's resolved struck state."""
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "bad", "latex": "wrong"},
#     )
#     _record(
#         audit,
#         "strikethrough",
#         {"type": "strikethrough", "target_id": "bad"},
#     )
#     _record(
#         audit,
#         "new_page",
#         {"type": "new_page", "carry_forward_ids": ["bad"]},
#     )
#     state = reconstruct(audit)
#     carried = next(e for e in state.current_entries if e.carried_forward)
#     assert carried.struck is True


# def test_carry_forward_unknown_id_silently_drops(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "new_page",
#         {"type": "new_page", "carry_forward_ids": ["ghost"]},
#     )
#     state = reconstruct(audit)
#     assert state.current_page == 2
#     assert state.current_entries == []


# def test_step_equation_expands_with_title(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "step_equation",
#         {
#             "type": "step_equation",
#             "element_id": "s1",
#             "title": "Solve for a",
#             "steps": [{"latex": "F = m a"}, {"latex": "a = F/m"}],
#         },
#     )
#     state = reconstruct(audit)
#     entries = state.current_entries
#     assert len(entries) == 3
#     assert entries[0].kind == "section_header"
#     assert entries[0].content == "Solve for a"
#     assert entries[1].kind == "equation"
#     assert entries[2].kind == "equation"


# def test_write_answer_produces_answer_entry(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "write_answer",
#         {"type": "write_answer", "element_id": "a1", "latex": "a = 5"},
#     )
#     state = reconstruct(audit)
#     e = state.current_entries[0]
#     assert e.kind == "answer"
#     assert e.content == "a = 5"


# def test_render_prompt_shows_current_page_entries(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "write_section",
#         {"type": "write_section", "element_id": "sec", "title": "Solve"},
#     )
#     _record(
#         audit,
#         "write_equation",
#         {
#             "type": "write_equation",
#             "element_id": "eq-1",
#             "latex": "F = m a",
#             "align_group": "g1",
#         },
#     )
#     state = reconstruct(audit)
#     section = render_prompt_section(state)
#     assert "Page 1 (current):" in section
#     assert "[sec]" in section
#     assert "[eq-1]" in section
#     assert "align=g1" in section
#     # The LLM is told how to reference entries.
#     assert "carry_forward_ids" in section
#     assert "Active align_groups" in section


# def test_render_prompt_shows_previous_page_summary(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "eq-1", "latex": "x = 1"},
#     )
#     _record(audit, "new_page", {"type": "new_page", "carry_forward_ids": []})
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "eq-2", "latex": "y = 2"},
#     )
#     state = reconstruct(audit)
#     section = render_prompt_section(state, history_pages=1)
#     assert "Page 1 (summary):" in section
#     assert "Page 2 (current):" in section
#     assert "[eq-1]" in section
#     assert "[eq-2]" in section


# def test_render_prompt_flags_struck_in_summary(audit: SessionAudit) -> None:
#     _record(
#         audit,
#         "write_equation",
#         {"type": "write_equation", "element_id": "bad", "latex": "wrong"},
#     )
#     _record(
#         audit,
#         "strikethrough",
#         {"type": "strikethrough", "target_id": "bad"},
#     )
#     state = reconstruct(audit)
#     section = render_prompt_section(state)
#     assert "STRUCK" in section
#     assert "Already struck" in section


# def test_notebook_tools_set_matches_panel_mapping() -> None:
#     """Guardrail: if a new notebook tool is added in tools.py it must also be
#     listed here, or state reconstruction silently drops it."""
#     from feynman.agent.tools import INSTRUCTION_TYPE_TO_PANEL
#     from feynman.visuals.schemas import Panel

#     expected = {
#         t for t, p in INSTRUCTION_TYPE_TO_PANEL.items() if p == Panel.NOTEBOOK
#     }
#     assert expected == set(NOTEBOOK_TOOLS)
