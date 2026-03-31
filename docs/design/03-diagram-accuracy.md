# Diagram Accuracy: Layered Validation Architecture

## The Problem

When the AI is teaching, if it says "see the chloroplast here" and the diagram doesn't have a chloroplast, or the chloroplast is in the wrong place, or a circuit diagram has wrong connections — that destroys trust instantly. Especially in education, inaccuracy is unacceptable.

A wrong diagram while teaching is **worse than no diagram** — it actively teaches misinformation.

---

## The Three Failure Categories

### 1. Technical Incorrectness — the diagram itself is wrong
- Circuit with open loop (won't work physically)
- Chemical equation not balanced
- Force arrows pointing wrong direction
- Plant cell missing cell wall
- Molecular structure with wrong valences

### 2. Speech-Visual Mismatch — AI says one thing, diagram shows another
- "Notice the THREE resistors" -> diagram has two
- "See the chloroplast here" -> no chloroplast in diagram
- "Look at the arrow pointing up" -> arrow points down

**This is the WORST failure mode** — it's gaslighting the student. The student doubts themselves instead of the diagram.

### 3. Pedagogical Incompleteness — diagram technically correct but teaches poorly
- Leaves out the part that matters for this explanation
- Labels are ambiguous or in wrong positions
- Proportions mislead (nucleus drawn bigger than cell)
- Too much detail for the student's level (information overload)

---

## The Defense: Five-Layer Validation Architecture

No single layer catches everything. You need defense in depth.

```
LLM generates diagram spec (semantic, NOT rendering code)
        |
        v
   +--------------------------------------------------+
   |     LAYER 1: CONSTRAINED GENERATION               |
   |  LLM picks from validated components,             |
   |  NOT generating arbitrary visuals                  |
   |  -> Eliminates rendering errors entirely           |
   +------------------------+--------------------------+
                            |
                            v
   +--------------------------------------------------+
   |     LAYER 2: SCHEMA VALIDATION                    |
   |  Does the spec conform to the format?             |
   |  Required fields present? Types correct?          |
   |  -> Catches malformed specs (< 10ms)              |
   +------------------------+--------------------------+
                            |
                            v
   +--------------------------------------------------+
   |     LAYER 3: DOMAIN RULES ENGINE                  |
   |  Physics: closed circuits, balanced forces         |
   |  Chemistry: balanced equations, valid valences     |
   |  Biology: required organelles per cell type        |
   |  Math: expression validity                         |
   |  -> Catches technical errors (< 50ms)             |
   +------------------------+--------------------------+
                            |
                            v
   +--------------------------------------------------+
   |     LAYER 4: SPEECH-VISUAL CONSISTENCY             |
   |  Cross-reference: what does speech mention?        |
   |  Is it present in the diagram?                     |
   |  -> Catches mismatch errors (< 100ms)             |
   +------------------------+--------------------------+
                            |
                            v
   +--------------------------------------------------+
   |     LAYER 5: REFERENCE GROUNDING                  |
   |  If verified diagram exists for this concept       |
   |  -> diff against reference                         |
   |  -> Catches omissions (< 50ms)                    |
   +------------------------+--------------------------+
                            |
                      PASS? |
            +---------------+---------------+
            |               |               |
         ALL PASS       FIXABLE         NOT FIXABLE
            |               |               |
            v               v               v
         Render       Auto-fix &         Fallback
                      re-validate
```

### Total validation time: < 300ms
This is fast enough to run in the beat buffer window — validation happens on generated-but-not-yet-played beats. Zero added latency to the student experience.

---

## Layer 1: Constrained Generation (The Big One)

This eliminates 70% of errors before validation even starts.

**The LLM NEVER generates visual code. It selects and composes from a library of verified building blocks.**

```
BAD (what most people try):
  LLM -> "draw a circle at (100,200) with label 'nucleus',
          draw a rectangle around it..."
  -> LLM can put nucleus OUTSIDE the cell, mislabel, wrong shape

GOOD (what we do):
  LLM -> {"diagram_type": "plant_cell",
          "components": ["cell_wall", "cell_membrane", "nucleus",
                         "chloroplast", "vacuole", "mitochondria"],
          "highlight": ["chloroplast"],
          "labels": "all",
          "style": "simplified_for_grade_8"}
  -> Renderer knows EXACTLY how to draw a plant cell
  -> Chloroplast is ALWAYS green, ALWAYS inside the cell
  -> Nucleus is ALWAYS the right relative size
  -> The LLM's job is WHAT to show, not HOW to draw it
```

We already have 41 validated components in our diagram engine:
- 5 mechanics components
- 8 optics components
- 11 circuit components
- 9 geometry components
- 8 chemistry components

Each one is hand-verified for technical correctness. The LLM composes from these — it can't accidentally draw a physically impossible circuit because the circuit components enforce valid topology.

**For novel diagrams** (not in the component library): the LLM composes from verified sub-components. Like LEGO blocks — each block is correct, the LLM decides which blocks and where. The 5 layout strategies enforce spatial rules.

---

## Layer 3: Domain Rules Engine (The Underrated One)

These are deterministic, codified rules — no LLM needed, near-instant.

### Physics
```python
def validate_circuit(spec):
    errors = []
    # Rule 1: Circuit must be closed
    if not is_closed_loop(spec.connections):
        errors.append("Open circuit -- no current will flow")
    # Rule 2: No short circuits
    if has_short_circuit(spec.connections):
        errors.append("Short circuit detected")
    # Rule 3: Kirchhoff's laws
    if spec.annotations and not kirchhoff_voltage_valid(spec):
        errors.append("Voltage annotations violate KVL")
    return errors
```

### Chemistry
```python
def validate_chemical_equation(spec):
    errors = []
    # Rule 1: Equation must be balanced
    lhs_atoms = count_atoms(spec.reactants)
    rhs_atoms = count_atoms(spec.products)
    if lhs_atoms != rhs_atoms:
        errors.append(f"Unbalanced: {diff(lhs_atoms, rhs_atoms)}")
    # Rule 2: Valid molecular formulas
    for molecule in spec.all_molecules:
        if not is_valid_formula(molecule):
            errors.append(f"Invalid formula: {molecule}")
    return errors
```

### Biology
```python
REQUIRED_COMPONENTS = {
    "plant_cell": ["cell_wall", "cell_membrane", "nucleus",
                   "chloroplast", "vacuole", "mitochondria"],
    "animal_cell": ["cell_membrane", "nucleus", "mitochondria",
                    "ribosome", "endoplasmic_reticulum"],
    "human_heart": ["left_atrium", "right_atrium",
                    "left_ventricle", "right_ventricle",
                    "aorta", "pulmonary_artery"],
}

def validate_biology_diagram(spec):
    required = REQUIRED_COMPONENTS.get(spec.diagram_type, [])
    present = {c.id for c in spec.components}
    missing = set(required) - present
    if missing:
        return ValidationResult(
            errors=[f"Missing required: {missing}"],
            auto_fix={"add_components": list(missing)}  # <- can auto-fix!
        )
```

**Key insight: you don't need an LLM to check if a circuit is closed — that's graph traversal. You don't need an LLM to check if an equation is balanced — that's atom counting.** Fast, deterministic, 100% reliable.

---

## Layer 4: Speech-Visual Consistency (The Trust Saver)

Catches the most embarrassing failure: AI talks about something not in the diagram.

```python
def check_speech_visual_consistency(speech_text, diagram_spec):
    # Extract what the speech references
    speech_entities = extract_referenced_entities(speech_text)
    # e.g., ["chloroplast", "sunlight", "three arrows"]

    diagram_entities = get_diagram_elements(diagram_spec)
    # e.g., ["cell_wall", "nucleus", "chloroplast", "vacuole"]

    # Check: everything speech mentions must be in diagram
    missing = []
    for entity in speech_entities:
        if not fuzzy_match(entity, diagram_entities):
            missing.append(entity)

    # Check: counts match
    # "three resistors" -> diagram must have exactly 3 resistors
    count_refs = extract_count_references(speech_text)
    for item, expected_count in count_refs:
        actual = count_in_diagram(item, diagram_spec)
        if actual != expected_count:
            missing.append(f"Speech says {expected_count} {item}, diagram has {actual}")

    return ConsistencyResult(missing=missing)
```

This works because both the speech text and the diagram spec are structured data we control. We're not comparing pixels to audio — we're comparing JSON to text.

---

## Layer 5: Reference Grounding (The Accuracy Floor)

**For curriculum content, diagrams should be grounded in textbook-verified references, not generated from scratch.**

```
Precompute phase:
  Textbook diagram of plant cell
       |
       v
  Decompose into semantic spec (human verified):
  {
    "type": "plant_cell",
    "components": [...with verified positions, labels, relationships...],
    "verified": true,
    "source": "NCERT Class 8 Biology Chapter 8 Figure 8.1"
  }
       |
       v
  Store in Reference Library (indexed by concept)

Live phase:
  LLM wants to show a plant cell
       |
       v
  Check: does Reference Library have a verified plant cell?
       |
    YES (90% of cases) --> Use reference spec
    |                       (adapt: add highlights, simplify, annotate)
    |                       (but DON'T change structure)
    |
    NO (doubt handling) --> Generate fresh, run full validation pipeline
```

**For core curriculum content, diagrams are as accurate as the textbook.** The LLM's role is presentation (what to highlight, what to label, how to animate) — not creation of the underlying structure.

The LLM ADAPTS the reference, it doesn't REPLACE it:
- Reference: full plant cell with all organelles
- LLM decides: "For this explanation, highlight chloroplast, dim everything else, add arrow showing sunlight entering"
- The base structure is textbook-verified. The adaptation is safe.

---

## How Validation Fits in the Beat Architecture

Validation runs in the beat buffer window:

```
Time: --------------------------------------------->

LLM:     [generate beat 4]   [generate beat 5]   [generate beat 6]
              |                    |
Validate: [validate diagram    [validate diagram
            in beat 4 - 200ms]  in beat 5 - 200ms]
              |                    |
          PASS -> ready         FAIL -> auto-fix
                                     -> re-validate
                                     -> or fall back

Play:    > beat 2 >>>>> beat 3 >>>>> beat 4 >>>>> beat 5

By the time we PLAY beat 4, it's been validated for 5+ seconds.
```

**Validation is invisible to the student.** It happens in the buffer, not in the playback path.

---

## Graceful Degradation When Validation Fails

```
Validation fails
       |
       +---> Auto-fixable? (e.g., missing component -> add it)
       |        -> Fix, re-validate, use fixed version
       |
       +---> Reference available?
       |        -> Fall back to pre-verified reference diagram
       |
       +---> Neither?
       |        -> Skip visual for this beat
       |        -> Rewrite beat speech: remove diagram references
       |        -> "Let me explain this with words first..."
       |        -> Queue diagram for retry in next beat
       |
       +---> NEVER show an unvalidated diagram
```

The student never sees a wrong diagram. They might occasionally get a verbal-only explanation (which is fine — teachers do this all the time), but never misinformation.

---

## For the Prototype

**Hand-build 15-20 reference diagrams for the demo lesson.** That gives you 100% accuracy for core content, and the validation pipeline catches the edge cases during doubt handling.

The full domain rules engine can be built incrementally — start with the rules for your demo subject (e.g., physics: circuits must be closed, forces must balance), then expand.

---

## Decision Points for Yash

1. **Which layer to build first?** Layer 1 (constrained generation) is already done (41 components). Layer 5 (reference library) is highest ROI for the demo. Layer 3 (domain rules) is highest ROI long-term. Layers 2 and 4 are quick wins.

2. **How many reference diagrams for the demo?** 15-20 covers a full chapter. Hand-verify each one.

3. **How to handle the novel diagram case?** During doubts, the AI might need a diagram that doesn't exist in the reference library. Options: (a) generate + validate (slower, riskier), (b) compose from verified building blocks (safer), (c) skip the diagram and explain verbally (safest).

4. **Auto-fix or reject?** When validation catches an error, should the system try to fix it (add missing component, balance equation) or reject and fall back? Auto-fix for simple cases (missing component), reject for complex cases (wrong topology).
