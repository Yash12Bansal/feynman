"""Short CoT prompt for the solution-diagram generator.

ONE call does both jobs (no separate classify call → no extra latency/cost):
decide `diagram_needed`, and if true, emit a `diagram_spec` in the SAME
DesignDiagramSpec shape the frontend already renders. Compressed from the
pipeline's full diagram prompt — just the element vocabulary the renderer needs.
"""

from __future__ import annotations

SOLUTION_DIAGRAM_SYSTEM = """\
You decide whether what you are shown needs a diagram, and if so, you draw it. \
Reason briefly, then emit ONE tool call.

steps (array of strings): ONLY when the user prompt asks you to explain a \
solution (not for a question setup figure). The worked solution as an ORDERED \
list of steps that BUILD to the answer. Size it to difficulty: an easy question \
is ONE step (the direct reason); a multi-part one is several, each a single move \
in the reasoning (set up → key idea → apply → conclude). Each step is 1-3 \
sentences of plain spoken prose (it will be read aloud), self-contained, and \
flows from the previous — so a student who got it wrong can be shown them one at \
a time. Write NEUTRAL and standalone: this is shown to every student regardless \
of what they picked, so do NOT address the reader ("you"), do NOT assume they \
answered right or wrong, no "correct"/"incorrect" meta commentary, no step \
labels ("Step 1:"), no preamble, no markup. The LAST step states the answer and \
why. Omit `steps` entirely for setup-figure requests.

diagram_needed (boolean): true ONLY when a figure materially helps the student \
SEE it — geometry, forces, rays/optics, circuits, graphs, spatial or vector \
relationships. For pure-algebra, arithmetic, definitional, or conceptual cases, \
it is false. Most cases are false — be strict; a needless diagram is worse than \
none.

diagram_spec (object, ONLY when diagram_needed is true; null otherwise): a \
DesignDiagramSpec. It is a DIAGRAM, not a slide — no definitions, no bullet \
lists, no paragraphs of text. The visuals carry the meaning: clean geometry, \
neon accent arrows (cyan #7fd4ff / green / pink) on a dark board, tiny labels \
at element tips, generous whitespace, nothing extra. One concept per canvas.

Shape:
{ "title": "<short>", "width": 900, "height": 650,
  "backgroundColor": "transparent", "elements": [ ... ] }

Each element needs "type" + a unique "id". Default stroke "#e8e8ee" (reads on \
the dark board). Shapes are OUTLINED — "fill": "none". Coordinates are pixels, \
origin top-left, y down. Element types:
- svg_line   {x1,y1,x2,y2,stroke,strokeWidth}
- svg_rect   {x,y,width,height,stroke,fill:"none",rx}
- svg_circle {cx,cy,r,stroke,fill:"none"}
- svg_ellipse{cx,cy,rx,ry,stroke,fill:"none"}
- svg_arc    {cx,cy,r,startAngle,endAngle,stroke}   (degrees, 0=right, +=cw)
- svg_path   {d,stroke,fill:"none"}
- svg_arrow  {x1,y1,x2,y2,stroke}   force/velocity/ray vectors; colour by meaning
- svg_text   {x,y,text,fontSize:12,fill,textAnchor:"middle"}   labels only, terse
- svg_latex  {expression,x,y,fontSize,color}   math in proper notation

Use only the few elements the concept needs. Emit via the tool. No prose."""


def build_solution_user_prompt(
    *, q_text: str, answer: str, options: list[str] | None = None
) -> str:
    opts = ""
    if options:
        opts = "OPTIONS:\n" + "\n".join(o.strip() for o in options) + "\n\n"
    return (
        f"QUESTION:\n{q_text.strip()}\n\n"
        f"{opts}"
        f"CORRECT ANSWER:\n{answer.strip()}\n\n"
        "Write the worked solution as `steps` — an ordered array that builds to "
        "the answer. ONE step if it's simple; several if it genuinely has parts "
        "(each step one move in the reasoning). Keep them NEUTRAL and standalone "
        "— don't assume the reader's answer, don't say anyone is correct/"
        "incorrect. Then decide whether a diagram materially helps understand it, "
        "and draw it if so."
    )


def build_question_user_prompt(*, q_text: str) -> str:
    return (
        f"QUESTION:\n{q_text.strip()}\n\n"
        "Decide whether THIS question needs a setup figure to be answerable "
        "(e.g. a circuit, a force diagram, a geometric figure the question "
        "refers to). Most multiple-choice questions are pure text and need "
        "none. Draw the setup figure ONLY if the question can't be answered "
        "without seeing it. Never draw the answer."
    )
