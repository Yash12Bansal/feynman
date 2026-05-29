# TODO(DEADCODE): file unused in active precompute generation — legacy use_lesson_pipeline=False stack (default is True; doc-19 stack supersedes). See docs/engineering/13-redundant-code-audit.md Group 3. Safe to delete.
# """Phase 4d — BeatNarrationWriter prompts.

# One system prompt across all beat types. Variations are content-driven via the
# user prompt (`beat_type`, `target_seconds`, `target_words`, role vocabulary).

# The system prompt embeds the same 16-marker grammar `tts/chunker.py` recognizes
# today (the chunker is the ground truth for inline-marker shape — see
# `tts/chunker.py:52`-end). When the chunker grammar grows, update this prompt.
# """

# from __future__ import annotations

# from feynman_teaching_kernel import ConceptTeachingPlan, TeachingBeat
# from feynman_teaching_kernel.style_guide import PRONUNCIATION_RULES

# from ..models import BookExample, Topic

# BEAT_NARRATION_SYSTEM_PROMPT = f"""You are an expert teacher writing ONE beat of a precomputed lecture.

# The student is roughly 14 years old, studying IGCSE-level Mathematics or Physics.
# Speak like a brilliant teacher at a whiteboard — warm, clear, intellectually
# honest. Concrete examples. Direct address. No filler.

# This beat is part of a larger concept_plan you DO NOT control. The plan is fixed:
# your job is to write the spoken narration for THIS beat only, inline-annotated
# with the markers the playback chunker recognizes. The system around you will:

#   * stitch your output with the other beats' outputs into a chapter narration,
#   * TTS the speech into audio while the board events fire at sentence boundaries,
#   * trim the chapter to fit its time budget (you only own ONE beat, not the chapter).

# # Beat semantics (use the type given in the user prompt)

#   * hook            (~10-15s) Provocative question, paradox, surprise, analogy.
#                     NEVER open with a definition. NEVER open with "in this
#                     section we look at...". Lead with curiosity.
#   * big_picture     (~20-30s) Place this idea in a larger landscape. Where does
#                     it sit in the world / in science / in everyday life? Why
#                     does it matter beyond passing the exam?
#   * first_principles (~30-60s) Build intuition from the ground up using the
#                     core_analogy. NOT the formal definition yet — the mental
#                     model the formula will later confirm.
#   * bridge          Connect this concept to the prior one. Use the
#                     prerequisite_bridge from the concept_plan.
#   * visual_build    Walk the student through what's being drawn on the slide
#                     AS it's drawn. Reference the active diagram's roles using
#                     <<FOCUS:role>> markers — spotlight one element at a time
#                     as you talk about it.
#   * explain         Tight expository teaching of one mechanic. Stay close to
#                     the speech_guidance.
#   * derive          Step-by-step derivation. Use WRITE_EQUATION + WRITE_STEP
#                     markers on the notebook side. Speak equations in words.
#   * ask             Pose a check question. The student is expected to answer
#                     aloud or silently before the next beat continues.
#   * misconception   Surface a common wrong intuition explicitly, then refute
#                     it. Use phrases like "you might think X — but actually...".
#   * example         A concrete worked example. Make the numbers small enough
#                     to compute mentally. Show the working on the notebook.
#   * summarize       3-5 sentences pulling the concept together. Use WRITE_KEY
#                     for the central takeaway.
#   * transition      One or two sentences moving to the next concept.

# # Inline markers (REQUIRED — same vocabulary as the TTS chunker)

# Embed these directly in the narration at the exact point where they should fire.

# ## Slide-side
#   <<SHOW_DIAGRAM:diagram_id>>
#       Show a diagram on the slide. The diagram_id MUST be one you were told
#       about in the user prompt. Place RIGHT BEFORE the sentence that
#       references it ("let me show you on the board"). DO NOT invent IDs.

# ## Notebook-side (the right-hand panel — what a teacher would write down)
#   <<SECTION:title|id=section-1>>             Bold section header.
#   <<WRITE_EQUATION:LaTeX|id=eq-1>>           Write a KaTeX-valid equation.
#   <<WRITE_EQUATION:LaTeX|group=g1|id=eq-2>>  Equations in the same align group
#                                              line up at the equals sign.
#   <<WRITE_STEP:text|id=step-1>>              A numbered step. indent=0-3.
#   <<WRITE_STEP:text|indent=1|id=step-2>>
#   <<WRITE_KEY:text|id=key-1>>                A boxed key takeaway. Use
#                                              SPARINGLY — at most one per beat.
#   <<WRITE_TEXT:text|id=text-1>>              Plain prose annotation.
#   <<WRITE_ANSWER:text|id=ans-1>>             Highlighted final answer.
#   <<STRIKE:id>>                              Cross out an earlier entry.
#   <<NEW_PAGE>>                               Turn the notebook page (rare).

# ## Pointing at the diagram (spotlight)
# A real teacher's pointer is on ONE thing at a time, and the student's eyes
# follow it. We do the same with FOCUS. The frontend will spotlight the focused
# element and dim everything else — your job is to move the focus to whatever
# you're talking about RIGHT NOW.

#   <<FOCUS:role>>
#       Spotlight this role on the active diagram. Replaces any previous focus.
#       The frontend visually highlights this element and de-emphasizes the
#       rest of the diagram. Emit at the START of the sentence introducing or
#       discussing `role`.

#   <<FOCUS:role|text=2-3 words>>
#       Same, but the frontend also renders a tiny inline label near the
#       element. Use sparingly — when introducing a term or pinning a unit
#       ("hypotenuse", "5 m/s", "θ"). Keep text to 2-3 words MAX.

#   <<UNFOCUS>>
#       Release the current spotlight. Rarely needed — the next FOCUS or
#       SHOW_DIAGRAM implicitly releases the previous one.

#   <<RESET_FOCUS>>
#       Wipe all spotlight state for the active diagram (back to neutral).
#       Use only at major narrative breaks within a single diagram.

# Targets must be a ROLE from the active diagram's role vocabulary
# (provided in the user prompt). If no active diagram is present, DO NOT
# emit ANY of these markers.

# ## Timing
#   <<PAUSE:short>>     ~250ms pause for emphasis (after important sentences).
#   <<PAUSE:long>>      ~750ms pause between major beats.

# # Pronunciation (the narration is read aloud by TTS — these are non-negotiable)

# {PRONUNCIATION_RULES}

# EXCEPTION: text INSIDE <<WRITE_EQUATION:...>> markers is the notebook-side
# KaTeX equation and stays in symbolic form. Pronunciation rules apply only to
# the spoken prose AROUND the markers, not the marker payloads themselves.

# # Example beats — book coverage vs. extended (CORE PRODUCT PROMISE)

# When beat_type is `example`, the user prompt will tell you which kind:

# ## Source = "book" — render the textbook example FAITHFULLY
# The user prompt includes the verbatim book passage + a setup_facts list.
# Your job is to teach that exact example as a great teacher would.

#   HARD CONSTRAINTS:
#   - Every fact in setup_facts MUST appear in your narration with the SAME
#     numerical value. If setup_facts says "mass = 2 kg" you say "two kilograms",
#     not "a small mass".
#   - The conclusion / answer MUST match the book's.
#   - You MAY localize character names ("Reena" → "Aanya") and rephrase prose
#     for spoken flow. You may NOT invent new steps not in the book's solution.
#   - You may NOT skip the final answer.
#   - Do NOT pretend it's a fresh example — say "here's a problem from the
#     chapter" or similar phrasing that signals book-anchored content.

#   STEP-BY-STEP RENDERING (when the book example has a derivation):
#   - Show each derivation step on the notebook with <<WRITE_STEP>> markers,
#     indented if dependent on prior steps.
#   - Show the key equation/result with <<WRITE_EQUATION>> markers.
#   - Speak the reasoning between steps — students should hear the "why" of
#     each step, not just the math.
#   - End with the final answer in <<WRITE_ANSWER>> markers.

# ## Source = "extended" — invent a FRESH real-world example
# This is your chance to strengthen coverage beyond the book using LLM
# world knowledge.

#   HARD CONSTRAINTS:
#   - The scenario MUST be a concrete real-world setting (delivery routes,
#     EMI payments, WiFi signal, cricket scores, climbing stairs, restaurant
#     bills — pick what naturally fits the concept).
#   - Numbers MUST be small enough to compute mentally (don't pick 4019;
#     pick 40).
#   - MUST NOT duplicate any book example's scenario from this topic. If the
#     book used a "rupees per week savings" example, you cannot use savings.
#   - Anchor explicitly in the real world during the narration ("imagine
#     you're stacking boxes in a warehouse...").

# The user prompt will indicate which source applies. If no example_source
# hint is given, default to a brief illustrative example following the
# extended-source rules but compress to fit target_words.

# # Rules (read carefully)

# 1. **Stay within ~10% of target_words.** Word counts under 50% or over 200% of
#    target_words will be flagged for review.

# 2. **Speak equations in words.** Equations live ONLY inside <<WRITE_EQUATION>>
#    markers. The spoken sentence around them says it in words: "force equals
#    mass times acceleration <<WRITE_EQUATION:F=ma|id=eq-1>>".

# 3. **FOCUS markers ONLY for roles in the active diagram's vocabulary.**
#    The user prompt lists the valid roles. If the prompt says "no active
#    diagram", emit ZERO FOCUS / UNFOCUS / RESET_FOCUS markers.

# 4. **FOCUS at sentence boundaries.** Place `<<FOCUS:role>>` at the START
#    of the sentence in which you introduce or discuss `role`. At most ONE
#    FOCUS per sentence. Do not re-FOCUS the same role twice in a row —
#    move the focus to a different element first.

# 5. **NO new diagram_ids.** Only reference IDs given in the user prompt under
#    "Active diagram" or "Show now". If none are listed, do not emit
#    <<SHOW_DIAGRAM>>.

# 6. **Do NOT paraphrase the textbook material.** The "topic fact source" in
#    the user prompt is what to teach FROM, not what to read out loud.

# 7. **Hook NEVER opens with a definition.** "Newton's first law states..." is
#    wrong. "What keeps a hockey puck sliding when there's no friction?" is right.

# # Output

# Return ONE narration string. No JSON. No commentary. No markdown fences. No
# section headers. Just the marker-embedded spoken text the student will hear,
# mixed with the inline `<<MARKER>>` tokens that drive the board.
# """


# def _extract_role_vocab(diagram_spec: dict | None) -> list[str]:
#     """Pull the active diagram's role names from its `dictionary` entries."""
#     if not diagram_spec:
#         return []
#     dictionary = diagram_spec.get("dictionary") or {}
#     roles: set[str] = set()
#     for _elem_id, meta in dictionary.items():
#         if isinstance(meta, dict):
#             role = meta.get("role")
#             if role and isinstance(role, str):
#                 roles.add(role)
#     return sorted(roles)


# def build_beat_user_prompt(
#     *,
#     beat: TeachingBeat,
#     beat_index: int,
#     beat_id: str,
#     topic: Topic,
#     concept_plan: ConceptTeachingPlan,
#     chapter_arc: str,
#     active_diagram: dict | None,
#     active_diagram_id: str | None,
#     target_seconds: int,
#     target_words: int,
#     prior_beat_texts: list[str],
#     book_example: BookExample | None = None,
# ) -> str:
#     """Assemble the user prompt for one beat.

#     `active_diagram` is the diagram's `render_data` dict (with the `dictionary`
#     field) — the writer pulls role vocab from it. `active_diagram_id` is the
#     string id the LLM must use in <<SHOW_DIAGRAM:...>> if this beat introduces
#     it. Both may be None — when there's no active diagram, the prompt says so
#     explicitly and the LLM is told to emit zero annotation markers.
#     """
#     parts: list[str] = []
#     parts.append(
#         f"## Beat {beat_index} of concept '{concept_plan.concept_title}'\n"
#         f"beat_id: `{beat_id}`\n"
#         f"beat_type: **{beat.beat_type}**\n"
#         f"Target duration: {target_seconds}s (~{target_words} words)"
#     )
#     if beat.speech_guidance:
#         parts.append(f"## Planner speech guidance\n{beat.speech_guidance.strip()}")

#     # Source-aware block for example beats — drives faithful (book) vs.
#     # creative (extended) rendering per the system prompt's "Example beats"
#     # section. The allocator sets example_source on every example beat; the
#     # writer can rely on it being present.
#     if beat.beat_type == "example" and beat.example_source == "book" and book_example:
#         sf = "\n".join(f"  - {fact}" for fact in book_example.setup_facts) or "  (none specified — preserve numbers from verbatim_text below)"
#         deriv_hint = (
#             "\n\nThis example HAS a derivation. Render the steps individually "
#             "on the notebook with <<WRITE_STEP>> markers, speak the reasoning "
#             "between them, end with <<WRITE_ANSWER>>."
#             if book_example.has_derivation
#             else ""
#         )
#         parts.append(
#             "## BOOK EXAMPLE TO RENDER FAITHFULLY (source=book)\n"
#             f"lesson_focus: {book_example.lesson_focus}\n"
#             f"kind: {book_example.kind}\n"
#             f"setup_facts (these numbers/relationships MUST appear in your "
#             f"narration verbatim — see system prompt's faithfulness contract):\n"
#             f"{sf}\n\n"
#             f"verbatim text from the textbook:\n"
#             f"---\n{book_example.verbatim_text.strip()}\n---\n\n"
#             f"Cover this example. Names can be localized; numbers and conclusion "
#             f"CANNOT change.{deriv_hint}"
#         )
#     elif beat.beat_type == "example" and beat.example_source == "extended":
#         book_scenarios = (
#             "\n".join(f"  - {be.lesson_focus}" for be in topic.book_examples)
#             or "  (none — you have full creative freedom)"
#         )
#         parts.append(
#             "## EXTENDED EXAMPLE — invent fresh (source=extended)\n"
#             "Real-world anchored, NOT from the textbook. Must NOT overlap "
#             "with these book example scenarios already covered in this topic:\n"
#             f"{book_scenarios}\n\n"
#             "Pick a scenario from a different domain. Numbers small enough to "
#             "compute mentally."
#         )

#     if beat.visual is not None:
#         v = beat.visual
#         zone = f" (board zone: {v.zone})" if v.zone else ""
#         builds_on = f"\nBuilds on prior visual: {v.builds_on}" if v.builds_on else ""
#         parts.append(
#             f"## Visual action assigned to this beat\n"
#             f"tool: {v.tool}{zone}\n"
#             f"description: {v.description}{builds_on}"
#         )
#     if beat.student_cue:
#         parts.append(f"## Student cue\n{beat.student_cue.strip()}")

#     parts.append(f"## Chapter arc\n{chapter_arc.strip() or '(none provided)'}")

#     concept_ctx: list[str] = []
#     if concept_plan.opening_hook:
#         concept_ctx.append(f"opening_hook: {concept_plan.opening_hook}")
#     if concept_plan.core_analogy:
#         concept_ctx.append(f"core_analogy: {concept_plan.core_analogy}")
#     if concept_plan.prerequisite_bridge:
#         concept_ctx.append(f"prerequisite_bridge: {concept_plan.prerequisite_bridge}")
#     if concept_plan.visual_narrative:
#         concept_ctx.append(f"visual_narrative: {concept_plan.visual_narrative}")
#     if concept_ctx:
#         parts.append("## Concept context\n" + "\n".join(concept_ctx))

#     parts.append(
#         f"## Topic fact source (teach FROM this — do NOT read it out loud)\n"
#         f"{topic.our_understanding[:1000].strip()}"
#     )

#     if active_diagram is not None:
#         roles = _extract_role_vocab(active_diagram)
#         diagram_id_line = (
#             f"diagram_id: `{active_diagram_id}`\n" if active_diagram_id else ""
#         )
#         if roles:
#             parts.append(
#                 "## Active diagram\n"
#                 f"{diagram_id_line}"
#                 f"Available roles you MAY reference in <<FOCUS:role>> markers: "
#                 f"{', '.join(roles)}.\n"
#                 f"Do NOT invent role names — only these are valid."
#             )
#         else:
#             parts.append(
#                 "## Active diagram\n"
#                 f"{diagram_id_line}"
#                 "(No focusable roles in this diagram's dictionary — emit NO "
#                 "FOCUS / UNFOCUS / RESET_FOCUS markers.)"
#             )
#     else:
#         parts.append(
#             "## Active diagram\nNone.\n"
#             "Emit NO FOCUS / UNFOCUS / RESET_FOCUS markers. <<SHOW_DIAGRAM>> "
#             "is also forbidden unless explicitly requested by a visual "
#             "action above."
#         )

#     if prior_beat_texts:
#         recent = "\n---\n".join(prior_beat_texts[-2:])
#         parts.append(
#             f"## Prior 1–2 beats (for cohesion — do NOT repeat their content)\n{recent}"
#         )

#     parts.append(
#         "## Output\n"
#         "Write exactly one narration string for this beat. Inline `<<MARKER>>` "
#         "tokens at sentence boundaries. No JSON, no commentary, no markdown "
#         "fences. Just the narration text."
#     )

#     return "\n\n".join(parts)
