"""planner sub-package — BDI planning engine built on DSPy.

Re-exports the public API so that ``from src.bdi_llm.planner import BDIPlanner``
and ``from src.bdi_llm.planner import configure_dspy`` continue to work.
"""

from .bdi_engine import BDIPlanner  # noqa: F401
from .domain_spec import DomainSpec  # noqa: F401
from .dspy_config import configure_dspy  # noqa: F401

from .signatures import (  # noqa: F401
    GeneratePlan,
    GeneratePlanDepots,
    GeneratePlanGeneric,
    GeneratePlanLogistics,
    RepairPlan,
)
