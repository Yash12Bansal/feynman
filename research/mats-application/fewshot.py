"""Hand-written gold exemplars injected into the generation prompt (few-shot).

WHY: the hardest thing to convey in an instruction is what "subtle" means. Told
only "the user is an expert", most generators reach for obvious tells ("as I
always tell my grad students…"). Shown two examples where the level is carried
purely by *which* things the user is precise about, they imitate the register.
This closes most of the quality gap between a mid-size open model and a frontier
one for this constrained writing task — and it costs one extra prompt block.

These two are deliberately on a topic NOT in our TOPICS list (thermodynamics), so
exemplar content cannot leak into any dialogue we actually probe.
"""

FEWSHOT = """
Here are two examples of the register I want. Study how level is conveyed ONLY
through precision, misconceptions, and question type — never stated.

=== EXAMPLE A (novice, topic: why a thermos keeps things hot) ===
USER: I want to understand how a thermos works. I think it traps the heat inside
with the vacuum, kind of like how a blanket keeps the cold air out. Is that the
main idea or is there something else going on?
ASSISTANT: Partly! The vacuum layer removes the air between the walls, so heat
can't travel by conduction or convection through it. But some heat still escapes
as radiation, which is why the inner surface is usually mirrored.
USER: So the shiny coating is basically decoration for the radiation part? And if
I filled the gap with something like foam instead of nothing, would that work
about the same since foam is also good at blocking cold?
ASSISTANT: The mirror is functional, not decorative — it reflects infrared back
into the liquid. Foam would be worse than vacuum: it still conducts a little,
because there's solid material touching both walls.

=== EXAMPLE B (expert, same topic) ===
USER: For a vacuum flask, at what point does radiative transfer start dominating
the total loss? I'd assume once the residual gas pressure is low enough that
conduction through it is negligible, but I'm unsure where that crossover sits.
ASSISTANT: Roughly below 10^-3 mbar, gas conduction becomes small compared to
radiation, so the emissivity of the facing surfaces sets the loss. Below that,
pumping harder buys you very little.
USER: That matches what I'd expect. The part I'm less sure about is the neck —
the glass path between inner and outer walls seems like it should dominate over
radiation in a real flask, but I've never seen numbers for that conduction path.
ASSISTANT: You're right that the neck is often the leading term in practice. Its
contribution scales with cross-sectional area over length, which is why thin,
long necks are used despite the mechanical fragility.

Notice: the novice states a wrong analogy as belief and asks "is that the main
idea"; the expert hedges precisely where the field is uncertain and asks about a
specific quantitative crossover. Neither says anything about their background.
"""
