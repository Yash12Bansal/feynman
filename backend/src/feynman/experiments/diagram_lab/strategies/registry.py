# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman). See docs/engineering/13-redundant-code-audit.md Group 1. Safe to delete.
# """Auto-discovers GenerationStrategy subclasses in this package.

# Drop a new file in `strategies/` with a `GenerationStrategy` subclass and it
# appears in `GET /api/diagtest/strategies` on next reload — no registration
# boilerplate.
# """

# from __future__ import annotations

# import importlib
# import inspect
# import pkgutil

# from feynman.experiments.diagram_lab.strategies.base import GenerationStrategy

# _registry: dict[str, GenerationStrategy] = {}


# def _discover() -> None:
#     """Import every module in this package and instantiate strategy classes."""
#     package = importlib.import_module("feynman.experiments.diagram_lab.strategies")
#     for _, name, _ in pkgutil.iter_modules(package.__path__):
#         if name in ("base", "registry", "__init__"):
#             continue
#         module = importlib.import_module(f"{package.__name__}.{name}")
#         for _attr, obj in inspect.getmembers(module, inspect.isclass):
#             if (
#                 issubclass(obj, GenerationStrategy)
#                 and obj is not GenerationStrategy
#                 and obj.__module__ == module.__name__
#             ):
#                 strat = obj()
#                 if strat.id in _registry:
#                     raise RuntimeError(
#                         f"Duplicate strategy id '{strat.id}': "
#                         f"{_registry[strat.id].__class__.__name__} vs {obj.__name__}"
#                     )
#                 _registry[strat.id] = strat


# def all_strategies() -> list[GenerationStrategy]:
#     if not _registry:
#         _discover()
#     return list(_registry.values())


# def get_strategy(strategy_id: str) -> GenerationStrategy:
#     if not _registry:
#         _discover()
#     if strategy_id not in _registry:
#         raise KeyError(f"Unknown strategy '{strategy_id}'. Known: {sorted(_registry)}")
#     return _registry[strategy_id]
