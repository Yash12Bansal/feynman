# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """Bridge to the design_agent diagram generator.

# Reads the design agent's system prompt and calls Claude directly
# to generate full SVG-based DiagramSpec dictionaries. This produces
# much higher quality diagrams than the structured node/edge approach.

# The design_agent source lives at ``<project_root>/design_agent/backend/``.
# We read its prompt at runtime so changes to the prompt propagate automatically.
# """

# from __future__ import annotations

# import copy
# import hashlib
# import json
# import re
# from collections import OrderedDict
# from collections.abc import Iterator
# from datetime import datetime
# from pathlib import Path
# from typing import Any

# import anthropic
# import httpx
# import structlog

# logger = structlog.get_logger()

# # ── Prompt loading ─────────────────────────────────────────

# _DESIGN_AGENT_DIR = Path(__file__).resolve().parents[4] / "design_agent" / "backend"
# _PROMPT_FILE = _DESIGN_AGENT_DIR / "prompts.py"
# _PYTHON_PROMPT_FILE = _DESIGN_AGENT_DIR / "prompts_python.py"

# _cached_prompt: str | None = None
# _cached_python_prompt: str | None = None


# def _load_system_prompt() -> str:
#     """Read SYSTEM_PROMPT from the design_agent prompts module."""
#     global _cached_prompt
#     if _cached_prompt is not None:
#         return _cached_prompt

#     if not _PROMPT_FILE.exists():
#         raise FileNotFoundError(
#             f"design_agent prompts not found at {_PROMPT_FILE}. "
#             "Ensure the design_agent directory is present in the project root."
#         )

#     ns: dict[str, Any] = {}
#     exec(compile(_PROMPT_FILE.read_text(), _PROMPT_FILE, "exec"), ns)
#     _cached_prompt = ns["SYSTEM_PROMPT"]
#     return _cached_prompt


# def _load_python_system_prompt() -> str:
#     """Read SYSTEM_PROMPT_PYTHON from the Python-DSL prompts module.

#     Phase 3 of the diagram-awareness re-architecture — used by
#     ``generate_via_python``. Mirrors ``_load_system_prompt`` so the
#     on-disk file stays the source of truth and changes propagate
#     without code edits.
#     """
#     global _cached_python_prompt
#     if _cached_python_prompt is not None:
#         return _cached_python_prompt

#     if not _PYTHON_PROMPT_FILE.exists():
#         raise FileNotFoundError(
#             f"Python-DSL prompt not found at {_PYTHON_PROMPT_FILE}. "
#             "Ensure the design_agent directory contains prompts_python.py."
#         )

#     ns: dict[str, Any] = {}
#     exec(compile(_PYTHON_PROMPT_FILE.read_text(), _PYTHON_PROMPT_FILE, "exec"), ns)
#     _cached_python_prompt = ns["SYSTEM_PROMPT_PYTHON"]
#     return _cached_python_prompt


# # ── JSON extraction & repair (ported from design_agent) ────

# _CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
# _PYTHON_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


# def _extract_python(text: str) -> str:
#     """Return Python source from a Claude response, stripping markdown fences."""
#     match = _PYTHON_FENCE_RE.search(text)
#     if match:
#         return match.group(1).strip()
#     return text.strip()


# def _extract_json(text: str) -> str:
#     """Return the JSON payload from *text*, stripping optional markdown fences."""
#     match = _CODE_FENCE_RE.search(text)
#     if match:
#         return match.group(1).strip()

#     text = text.strip()
#     start = text.find("{")
#     end = text.rfind("}")
#     if start != -1 and end != -1 and end > start:
#         return text[start : end + 1]

#     return text


# def _repair_json(json_str: str) -> dict[str, Any] | None:
#     """Try to repair truncated JSON by closing open brackets/braces."""
#     s = json_str.rstrip()
#     s = re.sub(r",\s*$", "", s)
#     s = re.sub(r',?\s*"[^"]*"\s*:\s*$', "", s)
#     s = re.sub(r',?\s*"[^"]*"\s*:\s*"[^"]*$', "", s)
#     s = re.sub(r",?\s*\{[^}]*$", "", s)

#     opens = 0
#     open_sq = 0
#     in_string = False
#     escape = False
#     for ch in s:
#         if escape:
#             escape = False
#             continue
#         if ch == "\\":
#             escape = True
#             continue
#         if ch == '"':
#             in_string = not in_string
#             continue
#         if in_string:
#             continue
#         if ch == "{":
#             opens += 1
#         elif ch == "}":
#             opens -= 1
#         elif ch == "[":
#             open_sq += 1
#         elif ch == "]":
#             open_sq -= 1

#     s += "]" * max(0, open_sq)
#     s += "}" * max(0, opens)

#     try:
#         return json.loads(s)
#     except json.JSONDecodeError:
#         return None


# def _parse_response(raw_text: str) -> dict[str, Any]:
#     """Extract JSON from the model output, validate structure, and return dict.

#     Phase 3-4: also runs ``_ensure_dictionary_completeness`` so every element
#     has a dictionary entry by the time the caller sees the spec.
#     """
#     json_str = _extract_json(raw_text)

#     try:
#         data = json.loads(json_str)
#     except json.JSONDecodeError as exc:
#         data = _repair_json(json_str)
#         if data is None:
#             logger.error(
#                 "design_bridge.json_parse_failed",
#                 chars=len(json_str),
#                 preview=json_str[:500],
#             )
#             raise ValueError("Claude returned invalid/truncated JSON for diagram.") from exc

#     # Basic structural validation
#     if not isinstance(data, dict) or "elements" not in data:
#         raise ValueError("Response missing required 'elements' field.")

#     return _ensure_dictionary_completeness(data)


# # ── Dispatch heuristic (Phase 3-4) ─────────────────────────

# _PYTHON_TRIGGERS_RE = re.compile(
#     r"\b(?:"
#     # Phase 3-4: geometric-precision triggers
#     r"exact\s+angle"
#     r"|exactly\s+\d+\s*°?"
#     r"|perpendicular"
#     r"|tangent\s+(?:to|line|at)"
#     r"|intersect(?:ion)?"
#     r"|parallel\s+to"
#     r"|normal\s+(?:to|force)"
#     r"|bisect(?:or)?"
#     r"|parametric"
#     r"|at\s+(?:an\s+)?angle\s+of"
#     r"|polar(?:\s+coord)?"
#     # Phase 3-5: composite triggers — when a STEM diagram name is
#     # mentioned, the Python path has a single-call composite for it.
#     r"|right\s+triangle"
#     r"|free[-\s]?body(?:\s+diagram)?"
#     r"|fbd"
#     r"|ray\s+diagram"
#     r"|(?:convex|concave)\s+lens"
#     r"|lens"
#     r"|lewis(?:\s+structure)?"
#     r"|methane"
#     r"|ammonia"
#     r")\b",
#     re.IGNORECASE,
# )


# def _dispatch_mode(prompt: str) -> str:
#     """Choose ``direct`` vs ``python`` for ``mode="auto"`` callers.

#     Conservative: only escalate to ``python`` when a strong geometric
#     signal is present in the prompt; default to ``direct``. The LLM can
#     still override with explicit ``mode="python"`` when the prompt is
#     ambiguous (the override bypasses this heuristic entirely).
#     """
#     if _PYTHON_TRIGGERS_RE.search(prompt):
#         return "python"
#     return "direct"


# # ── Auto-dictionary completion (Phase 3-4) ─────────────────


# def _walk_elements(elements: Any) -> Iterator[dict[str, Any]]:
#     """Yield every element dict in ``elements``, recursing into svg_group children."""
#     if not isinstance(elements, list):
#         return
#     for elem in elements:
#         if not isinstance(elem, dict):
#             continue
#         yield elem
#         if elem.get("type") == "svg_group":
#             yield from _walk_elements(elem.get("elements"))


# def _ensure_dictionary_completeness(spec: dict[str, Any]) -> dict[str, Any]:
#     """Fill missing dictionary entries with auto-derived role/semantic.

#     Idempotent — existing entries are preserved unchanged. New entries
#     use ``role=element_id`` and ``semantic=f"a {type_short}"`` (the
#     element-type prefix). Walks into ``svg_group`` children so nested
#     elements get entries on par with top-level ones, matching the flat
#     dictionary convention from Canvas DSL.
#     """
#     raw_dict = spec.get("dictionary") or {}
#     dictionary: dict[str, Any] = dict(raw_dict) if isinstance(raw_dict, dict) else {}
#     for elem in _walk_elements(spec.get("elements")):
#         eid = elem.get("id")
#         if not eid or eid in dictionary:
#             continue
#         type_short = str(elem.get("type", "element")).removeprefix("svg_")
#         dictionary[eid] = {
#             "role": eid,
#             "semantic": f"a {type_short}",
#             "position": "center",
#             "spatial_relations": [],
#         }
#     spec["dictionary"] = dictionary
#     return spec


# # ── In-memory FIFO cache (Phase 3-4) ───────────────────────

# _CACHE_MAX_SIZE = 64
# _DIAGRAM_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()


# def _cache_key(prompt: str, *, mode: str, model: str) -> str:
#     """SHA-256 key over prompt + mode + provider + model + prompt/schema mtimes.

#     Including the prompt-file and schema-file mtimes invalidates the
#     cache the moment either is edited — no manual flush needed.
#     """
#     from feynman.config import settings

#     provider = settings.design_agent_provider
#     direct_mtime = _PROMPT_FILE.stat().st_mtime if _PROMPT_FILE.exists() else 0.0
#     python_mtime = _PYTHON_PROMPT_FILE.stat().st_mtime if _PYTHON_PROMPT_FILE.exists() else 0.0
#     schema_file = _DESIGN_AGENT_DIR / "schema.py"
#     schema_mtime = schema_file.stat().st_mtime if schema_file.exists() else 0.0
#     key_src = f"{prompt}|{mode}|{provider}|{model}|{direct_mtime}|{python_mtime}|{schema_mtime}"
#     return hashlib.sha256(key_src.encode("utf-8")).hexdigest()[:16]


# def _cache_get(key: str) -> dict[str, Any] | None:
#     """Return a deep copy of the cached spec, or ``None`` on miss."""
#     cached = _DIAGRAM_CACHE.get(key)
#     if cached is None:
#         return None
#     return copy.deepcopy(cached)


# def _cache_put(key: str, spec: dict[str, Any]) -> None:
#     """Insert into the cache; FIFO-evict when at capacity.

#     Stores a deep copy so subsequent mutations by callers don't bleed
#     into cached values.
#     """
#     if key in _DIAGRAM_CACHE:
#         return
#     _DIAGRAM_CACHE[key] = copy.deepcopy(spec)
#     while len(_DIAGRAM_CACHE) > _CACHE_MAX_SIZE:
#         _DIAGRAM_CACHE.popitem(last=False)


# # ── Model mapping ──────────────────────────────────────────

# _MODELS = {
#     "opus": "claude-opus-4-20250514",
#     "sonnet": "claude-sonnet-4-20250514",
#     "haiku": "claude-haiku-4-5-20251001",
# }

# # ── Public API ─────────────────────────────────────────────

# _async_client: anthropic.AsyncAnthropic | None = None


# def _get_client() -> anthropic.AsyncAnthropic:
#     global _async_client
#     if _async_client is None:
#         from feynman.config import settings

#         _async_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
#     return _async_client


# async def _call_anthropic(
#     user_message: str,
#     model: str = "sonnet",
#     max_tokens: int = 16000,
# ) -> dict[str, Any]:
#     """Send a message to Claude with the design agent system prompt and parse the response."""
#     system_prompt = _load_system_prompt()
#     model_id = _MODELS.get(model, model)
#     client = _get_client()

#     logger.info(
#         "design_bridge.calling", provider="anthropic", prompt=user_message[:100], model=model_id
#     )

#     accumulated = ""
#     async with client.messages.stream(
#         model=model_id,
#         max_tokens=max_tokens,
#         system=system_prompt,
#         messages=[{"role": "user", "content": user_message}],
#     ) as stream:
#         async for text in stream.text_stream:
#             accumulated += text

#         final = await stream.get_final_message()
#         if final.stop_reason == "max_tokens":
#             logger.warning("design_bridge.truncated", chars=len(accumulated))

#     return _parse_response(accumulated)


# async def _call_ollama(
#     user_message: str,
#     model: str,
#     max_tokens: int = 16000,
# ) -> dict[str, Any]:
#     """Send a message to Ollama with the design agent system prompt and parse the response.

#     Works with any model served by Ollama — Qwen2.5-VL, Llama, Codestral, etc.
#     Uses Ollama's ``/api/chat`` endpoint (non-streaming for simplicity).
#     """
#     from feynman.config import settings

#     system_prompt = _load_system_prompt()
#     base_url = settings.ollama_base_url.rstrip("/")

#     logger.info("design_bridge.calling", provider="ollama", prompt=user_message[:100], model=model)

#     async with httpx.AsyncClient(timeout=180.0) as client:
#         response = await client.post(
#             f"{base_url}/api/chat",
#             json={
#                 "model": model,
#                 "messages": [
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": user_message},
#                 ],
#                 "stream": False,
#                 "options": {
#                     "num_predict": max_tokens,
#                     "temperature": 0.3,
#                 },
#             },
#         )
#         response.raise_for_status()
#         data = response.json()

#     raw_text = data["message"]["content"]

#     if data.get("done_reason") == "length":
#         logger.warning("design_bridge.truncated", chars=len(raw_text))

#     return _parse_response(raw_text)


# async def _route_call(
#     user_message: str,
#     model: str = "sonnet",
#     max_tokens: int = 16000,
# ) -> dict[str, Any]:
#     """Route to Anthropic or Ollama based on settings."""
#     from feynman.config import settings

#     if settings.design_agent_provider == "ollama":
#         ollama_model = settings.design_agent_model or model
#         return await _call_ollama(user_message, model=ollama_model, max_tokens=max_tokens)
#     return await _call_anthropic(user_message, model=model, max_tokens=max_tokens)


# async def generate_design_diagram(
#     prompt: str,
#     model: str = "sonnet",
#     max_tokens: int = 16000,
# ) -> dict[str, Any]:
#     """Generate a DiagramSpec using the design agent prompt.

#     Routes to Anthropic or Ollama based on ``settings.design_agent_provider``.
#     Phase 3-4 wraps the call in an in-memory cache; identical prompts (same
#     model, provider, prompt-file mtimes) skip the LLM round-trip.

#     Args:
#         prompt: Natural language description of the diagram to draw.
#         model: Model key — for Anthropic: "opus"/"sonnet"/"haiku";
#                for Ollama: overridden by ``settings.design_agent_model``.
#         max_tokens: Maximum response tokens.

#     Returns:
#         A validated DiagramSpec dict with elements, title, etc.
#     """
#     key = _cache_key(prompt, mode="direct", model=model)
#     cached = _cache_get(key)
#     if cached is not None:
#         logger.info(
#             "design_bridge.cache_hit",
#             path="direct",
#             key=key,
#             prompt=prompt[:60],
#         )
#         return cached

#     spec = await _route_call(prompt, model=model, max_tokens=max_tokens)
#     # `_parse_response` already ran `_ensure_dictionary_completeness`.

#     _cache_put(key, spec)
#     _save_spec(spec, prompt)
#     logger.info(
#         "design_bridge.complete",
#         title=spec.get("title", ""),
#         elements=len(spec.get("elements", [])),
#     )
#     return spec


# async def modify_design_diagram_spec(
#     existing_spec: dict[str, Any],
#     modification: str,
#     model: str = "sonnet",
#     max_tokens: int = 16000,
# ) -> dict[str, Any]:
#     """Modify an existing DiagramSpec by sending it + modification to Claude.

#     Much faster than generating from scratch (~1-3s vs 5-15s) because Claude
#     has the full spec as context and only needs to make targeted changes.

#     Args:
#         existing_spec: The current DiagramSpec dict to modify.
#         modification: Natural language description of what to change.
#         model: Model key for the provider.
#         max_tokens: Maximum response tokens.

#     Returns:
#         A complete, validated modified DiagramSpec dict.
#     """
#     spec_json = json.dumps(existing_spec, indent=2)
#     user_message = (
#         f"Here is an existing diagram specification:\n\n"
#         f"```json\n{spec_json}\n```\n\n"
#         f"Modify this diagram: {modification}\n\n"
#         f"Return the complete updated diagram specification as a single JSON object. "
#         f"Keep all unchanged elements exactly as they are. "
#         f"Only modify, add, or remove elements as described above."
#     )

#     spec = await _route_call(user_message, model=model, max_tokens=max_tokens)

#     _save_spec(spec, f"MODIFY: {modification}")
#     logger.info(
#         "design_bridge.modify_complete",
#         title=spec.get("title", ""),
#         elements=len(spec.get("elements", [])),
#         modification=modification[:80],
#     )
#     return spec


# # ── Python-DSL path (Phase 3, walking skeleton) ────────────


# async def _call_anthropic_python(
#     user_message: str,
#     model: str = "sonnet",
#     max_tokens: int = 8000,
# ) -> str:
#     """Call Claude with the Python-DSL system prompt; return raw text response."""
#     system_prompt = _load_python_system_prompt()
#     model_id = _MODELS.get(model, model)
#     client = _get_client()

#     logger.info(
#         "design_bridge.python.calling",
#         provider="anthropic",
#         prompt=user_message[:100],
#         model=model_id,
#     )

#     accumulated = ""
#     async with client.messages.stream(
#         model=model_id,
#         max_tokens=max_tokens,
#         system=system_prompt,
#         messages=[{"role": "user", "content": user_message}],
#     ) as stream:
#         async for text in stream.text_stream:
#             accumulated += text

#         final = await stream.get_final_message()
#         if final.stop_reason == "max_tokens":
#             logger.warning("design_bridge.python.truncated", chars=len(accumulated))

#     return accumulated


# async def generate_via_python(
#     prompt: str,
#     model: str = "sonnet",
#     max_tokens: int = 8000,
# ) -> dict[str, Any]:
#     """Generate a DiagramSpec by asking Claude to write Python in our DSL.

#     Phase 3 (walking skeleton) of the diagram-awareness re-architecture
#     (`docs/design/16-diagram-awareness-rearchitecture.md`). The LLM
#     authors a short script using ``feynman.visuals.canvas_dsl``; the
#     sandbox runs it; we export the resulting Canvas to the same dict
#     shape that ``generate_design_diagram`` returns, so all downstream
#     code (Pydantic validation, WS publishing, frontend rendering,
#     annotation dictionary) sees identical wire format.

#     Args:
#         prompt: Natural-language description of the diagram to draw.
#         model: Anthropic model key — "opus" / "sonnet" / "haiku".
#         max_tokens: Maximum response tokens.

#     Returns:
#         A validated DiagramSpec dict.

#     Raises:
#         ValueError: if Claude's response is empty, malformed, or the
#             sandbox rejects it. Caller surfaces this to the tool layer
#             so the teaching agent can fall back to direct-JSON generation.
#     """
#     from feynman.config import settings
#     from feynman.visuals.sandbox import SandboxError, execute_python_diagram

#     # Phase 3-1 routes Anthropic only — Ollama support is a later phase.
#     if settings.design_agent_provider == "ollama":
#         raise ValueError(
#             "Python-DSL diagram path is not yet wired for the Ollama provider. "
#             "Switch DESIGN_AGENT_PROVIDER=anthropic or use mode='direct'."
#         )

#     key = _cache_key(prompt, mode="python", model=model)
#     cached = _cache_get(key)
#     if cached is not None:
#         logger.info(
#             "design_bridge.cache_hit",
#             path="python",
#             key=key,
#             prompt=prompt[:60],
#         )
#         return cached

#     raw_response = await _call_anthropic_python(prompt, model=model, max_tokens=max_tokens)
#     code = _extract_python(raw_response)
#     if not code:
#         raise ValueError("design_bridge.python: model returned no Python code.")

#     try:
#         canvas = await execute_python_diagram(code)
#     except SandboxError as exc:
#         logger.warning(
#             "design_bridge.python.sandbox_failed",
#             error=str(exc),
#             code_preview=code[:300],
#         )
#         raise ValueError(f"Python-DSL sandbox failed: {exc}") from exc

#     # Canvas DSL auto-registers via `_register`, but run completeness as a
#     # belt-and-suspenders pass — also protects against any direct-dict
#     # construction users add later.
#     spec = _ensure_dictionary_completeness(canvas.export())
#     _cache_put(key, spec)
#     _save_spec(spec, f"PYTHON: {prompt}")
#     logger.info(
#         "design_bridge.python.complete",
#         title=spec.get("title", ""),
#         elements=len(spec.get("elements", [])),
#         code_chars=len(code),
#     )
#     return spec


# # ── Spec persistence ───────────────────────────────────────

# _GENERATED_DIR = Path(__file__).resolve().parents[4] / "design_agent" / "generated"


# def _save_spec(spec: dict[str, Any], prompt: str) -> None:
#     """Save the diagram spec alongside the design_agent's generated files."""
#     try:
#         _GENERATED_DIR.mkdir(parents=True, exist_ok=True)
#         title = spec.get("title", "untitled")
#         slug = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower()[:50]
#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#         filename = f"{timestamp}_{slug}.json"
#         filepath = _GENERATED_DIR / filename
#         filepath.write_text(json.dumps({"prompt": prompt, "spec": spec}, indent=2))
#         logger.debug("design_bridge.saved", path=str(filepath))
#     except Exception:
#         logger.warning("design_bridge.save_failed", exc_info=True)
