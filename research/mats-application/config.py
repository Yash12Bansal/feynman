"""Central config. Edit MODEL_ID / GENERATOR_MODEL / JUDGE_MODEL before anything else.

Design rules encoded here (each exists to kill a specific confound):
- 12 topics so we can hold out 4 entire topics at eval time (tests the CONCEPT of
  user-competence, not topic recognition).
- 3 competence levels (fewer, cleaner levels beat a fancy scale in 20 hours).
- Subject model != generator model != judge model families, so stylistic quirks of
  one model can't leak label information into another.
"""

# ---- models -----------------------------------------------------------------
# Subject model: newest Qwen DENSE ~9B instruct per Nanda's MATS doc recommendation
# ("Qwen 3.5/3.6 dense 4B/9B/27B are good defaults"). Check HuggingFace for the
# current id and update. Escalate to the 27B sibling only if 9B signals are weak.
MODEL_ID = "Qwen/Qwen3-8B"          # <-- UPDATE to current Qwen dense ~9B instruct
MODEL_ID_BIG = "Qwen/Qwen3-32B"     # <-- escalation target (27B/32B class)

# Generator & judge run via OpenRouter; three DIFFERENT model families on purpose:
#   subject = Qwen (what we study) | generator = Claude | judge = Gemini
# so no model is grading text written in its own style, and no generator quirk can
# leak label information into the thing we probe.
# Verified live on OpenRouter (Sep 2026). Prices per million tokens:
GENERATOR_MODEL = "anthropic/claude-sonnet-5"     # $2 in / $10 out
JUDGE_MODEL = "google/gemini-2.5-pro"             # $1.25 in / $10 out
# Rough budget: ~1000 dialogue generations x ~800 output tokens = ~$8 for the full
# dataset; judging adds well under $1. Load $15-20 of OpenRouter credit.
# To halve the cost at some quality risk: GENERATOR_MODEL="google/gemini-2.5-flash"
# and JUDGE_MODEL="anthropic/claude-haiku-4.5" (keeps families distinct).

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ---- dataset shape ----------------------------------------------------------
TOPICS = {
    # topic: (subtopic question seed, two novice misconceptions)
    "optics":        ("how lenses form images",
                      ["magnification only depends on lens size",
                       "focal length changes when you move the object"]),
    "probability":   ("independent events and streaks",
                      ["a streak of heads makes tails 'due'",
                       "50/50 means alternating outcomes"]),
    "personal_finance": ("index funds vs stock picking",
                      ["past fund returns predict future returns",
                       "more trades means more profit"]),
    "music_theory":  ("why chords sound consonant or dissonant",
                      ["minor keys are just sad major keys",
                       "dissonance means playing wrong notes"]),
    "cooking_chem":  ("what makes bread rise",
                      ["yeast and baking soda work the same way",
                       "kneading adds air which makes bread rise"]),
    "immunology":    ("how vaccines create immunity",
                      ["vaccines work by killing germs already in you",
                       "antibodies are white blood cells"]),
    "databases":     ("indexes and query speed",
                      ["indexes speed up every query",
                       "adding RAM is the same as adding an index"]),
    "climate":       ("greenhouse effect basics",
                      ["the ozone hole causes global warming",
                       "CO2 traps heat by blocking sunlight coming in"]),
    "chess":         ("why piece activity beats material sometimes",
                      ["the queen is always worth more than any three pieces",
                       "doubled pawns are always bad"]),
    "materials":     ("why metals bend and ceramics shatter",
                      ["harder always means stronger",
                       "metals bend because they are soft"]),
    "statistics":    ("what a p-value does and doesn't tell you",
                      ["p<0.05 means the hypothesis is 95% likely true",
                       "a significant result means a large effect"]),
    "networking":    ("what latency vs bandwidth means",
                      ["more bandwidth always reduces lag",
                       "wifi speed equals internet speed"]),
}
HELDOUT_TOPICS = ["immunology", "chess", "statistics", "networking"]  # eval-only

LEVELS = {
    "novice": (
        "has the listed common misconceptions and states at least one as a belief; "
        "uses everyday words for technical things; asks 'what is / why does' questions; "
        "overconfident in one wrong place, vague elsewhere"),
    "intermediate": (
        "correct on the basics, imprecise at the edges; mixes one correct technical "
        "term with one slightly-off usage; asks 'how / when does' questions"),
    "expert": (
        "precise terminology; asks about edge cases and trade-offs; hedges exactly "
        "where the field is genuinely uncertain; may correct a small imprecision in "
        "their own earlier phrasing"),
}

N_DIALOGUES_PER_CELL = 15     # per (topic x level) -> 12*3*15 = 540 dialogues
N_USER_TURNS = (4, 8)         # min, max user turns
USER_TURN_WORDS = (25, 60)    # length band, SAME for all levels (kills length confound)

# ---- extraction -------------------------------------------------------------
DTYPE = "bfloat16"
SAVE_DIR = "data"
ACT_DIR = "activations"
FIG_DIR = "figures"

# ---- figures (palette validated w/ dataviz checks; always direct-label lines)
COLORS = {"blue": "#0072B2", "orange": "#D55E00", "green": "#009E73", "pink": "#CC79A7"}


# ---- chat template helper ---------------------------------------------------
def chat_text(tok, messages, add_generation_prompt=True):
    """Serialize messages with the model's chat template, with THINKING DISABLED.

    Why: Qwen3 is a hybrid reasoning model — by default it emits a long <think>
    block before its actual reply. For our experiments that is pure noise:
      * E1/E2 read activations at the END OF THE USER TURN (before any reply),
        so thinking tokens only add irrelevant state and slow generation.
      * E3 needs the assistant's ACTUAL answer to the user's claim; a 500-token
        deliberation makes the judge's job ambiguous and costs GPU time.
    Studying the thinking trace is a great FOLLOW-UP question, but mixing it into
    v1 would confound "what the model believes about the user" with "what the
    model says while reasoning". One variable at a time.
    """
    try:
        return tok.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=add_generation_prompt,
                                       enable_thinking=False)
    except TypeError:      # tokenizer without a thinking switch
        return tok.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=add_generation_prompt)
