"""Graduate-mode layer — additive, separate from the IGCSE teaching path.

One call (`enable_graduate_mode()`) re-pitches the lesson/judge/chapter prompts
to an advanced/graduate audience and depth, keeping every great-teaching rule
intact. No existing pipeline file is edited.
"""

from lecture_pipeline_v2.grad_mode.activate import (
    disable_graduate_mode,
    enable_graduate_mode,
    is_enabled,
)

__all__ = ["enable_graduate_mode", "disable_graduate_mode", "is_enabled"]
