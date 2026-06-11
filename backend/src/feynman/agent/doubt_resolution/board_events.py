"""Board events — the wire vocabulary a doubt resolution emits to the frontend.

A doubt resolution is a real-time mini-lecture. Each `ResolutionBeat` compiles
to an ordered list of board events whose shapes mirror the precompute lecture's
`ManifestEvent` union (same field names, `type` discriminator) — so the
frontend plays a doubt through the *identical* `applySyncEvent` path it uses for
the lecture, just on a separate doubt board. This is the `unify_boardstate`
thesis: one board-event vocabulary, two producers (precompute + live doubt).

The compiler is deterministic: the planner (LLM) decides intent (which diagram,
what to write, what to annotate); this module turns that intent into concrete,
id-stamped events. Keeping id assignment + diagram stamping out of the LLM's
hands is what makes the output reliable.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from feynman.agent.doubt_resolution.models import (
    AnimateParameterAction,
    FocusAction,
    MarkPointAction,
    NotebookWrite,
    PointAtAction,
    ResolutionBeat,
    RevealStepAction,
    SetParameterAction,
    TraceAction,
    WriteEquationBlock,
    WriteKeyPointBlock,
    WriteSectionBlock,
    WriteStepBlock,
    WriteTextBlock,
)

# Reveal-all sentinel: a build_up diagram leaving the doubt board (swap / end)
# emits RevealStepBE(step=REVEAL_ALL_STEP); the frontend clamps it to the last
# reveal group and fills idempotently, so nothing is left hidden (mirrors the
# precompute walker + the frontend clamp).
REVEAL_ALL_STEP = 10_000


# ── Wire events (mirror the frontend ManifestEvent subset; `type` discr.) ────


class ShowDiagramBE(BaseModel):
    type: Literal["show_diagram"] = "show_diagram"
    diagram_id: str
    # Mirrors the precompute ShowDiagramEvent: build_up reveals elements as the
    # doubt annotates them; overview shows the figure complete. None ⇒ frontend
    # default (overview). Reused diagrams default overview (recap); freshly
    # generated diagrams default build_up (staged reveal of the new explanation).
    presentation_mode: Literal["build_up", "overview"] | None = None


class WriteSectionBE(BaseModel):
    type: Literal["write_section"] = "write_section"
    id: str
    title: str


class WriteEquationBE(BaseModel):
    type: Literal["write_equation"] = "write_equation"
    id: str
    latex: str
    align_group: str | None = None
    boxed: bool = False


class WriteStepBE(BaseModel):
    type: Literal["write_step"] = "write_step"
    id: str
    text: str
    indent: int = 0


class WriteTextBE(BaseModel):
    type: Literal["write_text"] = "write_text"
    id: str
    text: str


class WriteKeyPointBE(BaseModel):
    type: Literal["write_key_point"] = "write_key_point"
    id: str
    text: str


class FocusBE(BaseModel):
    type: Literal["focus"] = "focus"
    diagram_id: str
    target_element_id: str | None = None
    # Co-highlight several elements at once (the frontend reads this first, then
    # falls back to the single id). Driven by an inline `<<FOCUS:a+b>>` marker.
    target_element_ids: list[str] | None = None
    target_role: str | None = None
    text: str | None = None


class ClearAnnotationsBE(BaseModel):
    type: Literal["clear_annotations"] = "clear_annotations"
    diagram_id: str


class TraceBE(BaseModel):
    type: Literal["trace"] = "trace"
    diagram_id: str
    element_id: str
    duration_ms: int = 1500


class PointAtBE(BaseModel):
    type: Literal["point_at"] = "point_at"
    diagram_id: str
    element_id: str
    from_side: Literal["top", "bottom", "left", "right"] = "left"


class MarkPointBE(BaseModel):
    type: Literal["mark_point"] = "mark_point"
    diagram_id: str
    x: float
    y: float
    kind: Literal["dot", "cross", "star"] = "dot"
    label: str = ""


class RevealStepBE(BaseModel):
    """Advance a build_up diagram's staged reveal (or, with REVEAL_ALL_STEP,
    flush it to fully-revealed). Mirrors the precompute RevealStepEvent."""

    type: Literal["reveal_step"] = "reveal_step"
    diagram_id: str
    step: int = 0


class SetParameterBE(BaseModel):
    """Set an interactive diagram parameter (mirrors SetParameterEvent)."""

    type: Literal["set_parameter"] = "set_parameter"
    diagram_id: str
    name: str
    value: float


class AnimateParameterBE(BaseModel):
    """Tween a parameter — the sweep IS the explanation (mirrors
    AnimateParameterEvent). `from_` serializes as `from` under by_alias; the
    delivery dump MUST use by_alias=True or the frontend reads it as undefined.
    """

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["animate_parameter"] = "animate_parameter"
    diagram_id: str
    name: str
    to: float
    from_: float | None = Field(default=None, alias="from")
    duration_ms: int | None = None


BoardEvent = Annotated[
    ShowDiagramBE
    | WriteSectionBE
    | WriteEquationBE
    | WriteStepBE
    | WriteTextBE
    | WriteKeyPointBE
    | FocusBE
    | ClearAnnotationsBE
    | TraceBE
    | PointAtBE
    | MarkPointBE
    | RevealStepBE
    | SetParameterBE
    | AnimateParameterBE,
    Field(discriminator="type"),
]


# ── Compiler ─────────────────────────────────────────────────────────────────


def _notebook_to_event(write: NotebookWrite, block_id: str) -> BoardEvent:
    if isinstance(write, WriteEquationBlock):
        return WriteEquationBE(
            id=block_id,
            latex=write.latex,
            align_group=write.align_group,
            boxed=write.boxed,
        )
    if isinstance(write, WriteStepBlock):
        return WriteStepBE(id=block_id, text=write.text, indent=write.indent)
    if isinstance(write, WriteTextBlock):
        return WriteTextBE(id=block_id, text=write.text)
    if isinstance(write, WriteKeyPointBlock):
        return WriteKeyPointBE(id=block_id, text=write.text)
    if isinstance(write, WriteSectionBlock):
        return WriteSectionBE(id=block_id, title=write.title)
    raise TypeError(f"unknown notebook write: {type(write).__name__}")


def _annotation_to_event(action: object, diagram_id: str) -> BoardEvent:
    if isinstance(action, FocusAction):
        return FocusBE(
            diagram_id=diagram_id,
            target_element_id=action.target_element_id,
            target_role=action.target_role,
            text=action.text,
        )
    if isinstance(action, PointAtAction):
        return PointAtBE(
            diagram_id=diagram_id,
            element_id=action.element_id,
            from_side=action.from_side,
        )
    if isinstance(action, TraceAction):
        return TraceBE(
            diagram_id=diagram_id,
            element_id=action.element_id,
            duration_ms=action.duration_ms,
        )
    if isinstance(action, MarkPointAction):
        return MarkPointBE(
            diagram_id=diagram_id,
            x=action.x,
            y=action.y,
            kind=action.kind,
            label=action.label,
        )
    if isinstance(action, RevealStepAction):
        return RevealStepBE(diagram_id=diagram_id, step=action.step)
    if isinstance(action, SetParameterAction):
        return SetParameterBE(diagram_id=diagram_id, name=action.name, value=action.value)
    if isinstance(action, AnimateParameterAction):
        return AnimateParameterBE(
            diagram_id=diagram_id,
            name=action.name,
            to=action.to,
            from_=action.from_,
            duration_ms=action.duration_ms,
        )
    raise TypeError(f"unknown annotation action: {type(action).__name__}")


def compile_plan(
    beats: list[ResolutionBeat],
    resolved_diagram_ids: list[str | None],
    *,
    presentation_modes: list[str | None] | None = None,
    id_prefix: str = "doubt",
) -> list[list[BoardEvent]]:
    """Compile a resolved plan into per-beat board-event lists.

    `resolved_diagram_ids[i]` is the diagram id to *newly show* for beat i — the
    reuse target, or the freshly generated diagram's id — or None when the beat
    shows no new diagram (keep / none / generation-failed). The compiler tracks
    the active diagram across beats so a `keep`/`none` beat's annotations attach
    to whatever diagram is already on the doubt board.

    `presentation_modes[i]` is the show mode for that beat's new diagram
    ("build_up" / "overview" / None). A build_up diagram reveals as it's
    annotated; to guarantee nothing is left hidden, a terminal reveal-all
    (`RevealStepBE(step=REVEAL_ALL_STEP)`) is injected when the build_up diagram
    is swapped off the board and once more at the end of the resolution.

    Order within a beat: [reveal-all outgoing build_up] → show_diagram (if any)
    → notebook writes → annotations. Notebook block ids are unique across the
    whole resolution.
    """
    if len(resolved_diagram_ids) != len(beats):
        raise ValueError(
            f"resolved_diagram_ids ({len(resolved_diagram_ids)}) must align "
            f"with beats ({len(beats)})"
        )
    modes = presentation_modes if presentation_modes is not None else [None] * len(beats)
    if len(modes) != len(beats):
        raise ValueError(f"presentation_modes ({len(modes)}) must align with beats ({len(beats)})")

    out: list[list[BoardEvent]] = []
    active_diagram_id: str | None = None
    open_build_up_id: str | None = None
    block_seq = 0

    for i, beat in enumerate(beats):
        events: list[BoardEvent] = []

        new_diagram_id = resolved_diagram_ids[i]
        if new_diagram_id:
            mode = modes[i]
            # Flush the OUTGOING build_up diagram to fully-revealed before it
            # leaves the board, so an element the annotations never focused is
            # never stranded half-built (fires while it's still active).
            if open_build_up_id and open_build_up_id != new_diagram_id:
                events.append(RevealStepBE(diagram_id=open_build_up_id, step=REVEAL_ALL_STEP))
            events.append(ShowDiagramBE(diagram_id=new_diagram_id, presentation_mode=mode))
            active_diagram_id = new_diagram_id
            open_build_up_id = new_diagram_id if mode == "build_up" else None
        # `keep`/`none` inherit the existing active diagram + open build_up.

        for write in beat.notebook_writes:
            block_seq += 1
            events.append(_notebook_to_event(write, f"{id_prefix}-b{i}-n{block_seq}"))

        # Annotations only render against a diagram that's on the board. Drop
        # silently when there's nothing to anchor to (the planner shouldn't do
        # this, but a stray annotation must never crash delivery).
        if active_diagram_id and beat.annotation_actions:
            for action in beat.annotation_actions:
                # Focus/Trace now live as inline <<FOCUS>>/<<TRACE>> markers in
                # the narration — the delivery loop fires them synced to the
                # spoken phrase, so skip them here (don't ALSO dump them at
                # beat-start, which is the old "highlights disconnected from
                # voice" behaviour).
                if isinstance(action, (FocusAction, TraceAction)):
                    continue
                events.append(_annotation_to_event(action, active_diagram_id))

        out.append(events)

    # End of the resolution: flush a still-open build_up diagram.
    if open_build_up_id and out:
        out[-1].append(RevealStepBE(diagram_id=open_build_up_id, step=REVEAL_ALL_STEP))

    return out
