"""planner sub-package — BDI planning engine built on DSPy.

Re-exports the public API so that ``from src.bdi_llm.planner import BDIPlanner``
and ``from src.bdi_llm.planner import configure_dspy`` continue to work.
"""

from .bdi_engine import BDIPlanner  # noqa: F401
from .dspy_config import configure_dspy  # noqa: F401

# Re-export Signature classes for backward compatibility with
# scripts/batch/prepare_batch_jsonl.py and other modules.
from .signatures import (  # noqa: F401
    GeneratePlan,
    GeneratePlanLogistics,
    GeneratePlanDepots,
    RepairPlan,
)

# Also re-export private prompt constants for backward compatibility with
# coding_planner.py and other modules that import them from `.planner`.
from .prompts import (  # noqa: F401
    _GRAPH_STRUCTURE_COMMON,
    _STATE_TRACKING_HEADER,
    _COS_REPRESENTATION_HEADER,
    _LOGICOT_HEADER,
    _LOGICOT_PROTOCOL_DETAILED,
    _REMINDER,
)
