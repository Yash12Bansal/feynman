# Instructions for the research agent (copy to the repo root on the GPU pod)

You are assisting a mechanistic-interpretability research project: probing whether
LLMs form dynamic internal models of what the user knows. The human is the
researcher; you execute and they verify. Read README_START_HERE.md first.

## Kernel discipline
- A persistent Jupyter kernel is available via MCP (or IPython in tmux). Load the
  model and tokenizer ONCE in a dedicated top cell; NEVER reload or restart the
  kernel without asking.
- Save every plot to figures/ as PNG (also display inline). Save every result dict
  to a results_*.json. Checkpoint expensive artifacts (activations, generated
  datasets) to disk immediately.
- Long generation jobs: background script with a log file, not a notebook cell.

## Science discipline (non-negotiable)
- Before any experiment, restate: the hypothesis being tested, the prediction on
  file in logbook.md, and what result would falsify it.
- Report results as claims + the exact numbers + the file they came from. NEVER
  summarize a result as "it worked" — show the numbers and the caveats.
- After every experiment, list the two dumbest ways the result could be wrong
  (leakage, length/topic confound, judge gaming, broken parsing) and whether you
  checked them.
- When you produce a dataset or judged labels, ALWAYS print 5 randomly selected
  raw examples for the human to read. Random, never cherry-picked.
- Do not silently change experimental parameters (layers, alphas, splits, prompts).
  Propose, get confirmation, then run.
- Negative and inconclusive results are reported exactly as prominently as
  positive ones.

## Writing discipline
- Draft graphs and analysis freely. NEVER ghost-write the executive summary or
  application-form answers — the human writes those in their own voice.
- End each work session with a brief technical report: what ran, exact settings,
  outputs produced, what remains unverified.
