"""DSPy Signature definitions for SWE-bench plan generation and repair.

Three signatures:
- ``GeneratePlanCodingBaseline`` — minimal Predict-only prompt (no CoT/LogiCoT)
- ``GeneratePlanCoding`` — re-exported from ``coding_planner`` (BDI w/ CoT)
- ``RepairPlanCoding`` — repair signature accepting test feedback + history
"""

from __future__ import annotations

import dspy

from ..schemas import BDIPlan
from ..coding_planner import GeneratePlanCoding  # noqa: F401
from ..planner.prompts import (
    _GRAPH_STRUCTURE_COMMON,
    _REMINDER,
)


class GeneratePlanCodingBaseline(dspy.Signature):
    """You are a Software Engineer tasked with fixing a GitHub issue.

    Given a bug report (Beliefs) and a goal (Desire), produce a structured
    plan as a directed acyclic graph of file read/edit/test actions.

    CODING DOMAIN ACTIONS:
      read-file   : {"file": <path>}
      edit-file   : {"file": <path>, "test": <test_id>}
      run-test    : {"test": <test_id>}
      create-file : {"file": <path>}

    Rules:
    1. read-file BEFORE edit-file.
    2. run-test AFTER edit-file.
    3. Minimise edits; do not break passing tests.
    """

    beliefs: str = dspy.InputField(
        desc="Current state: Repo structure, issue description, test status"
    )
    desire: str = dspy.InputField(
        desc="Goal: Fix the issue and make failing tests pass"
    )
    plan: BDIPlan = dspy.OutputField(
        desc="Execution plan as a DAG of coding actions"
    )


class RepairPlanCoding(dspy.Signature):
    """You previously generated a coding plan that FAILED test verification.
    The test runner found specific failures in your plan execution.

    Fix the plan by addressing EACH error reported by the test runner.

    CRITICAL REPAIR RULES:
    1. Read the test failure output CAREFULLY — identify the root cause.
    2. Your repaired plan must address every failing test.
    3. Do NOT remove test steps — add fixes for the failures.
    4. Preserve all passing tests (regression safety).
    5. You may add new read-file/edit-file steps as needed.

{graph_structure}

    CODING DOMAIN ACTIONS:
      read-file   : {{"file": <path>}}
      edit-file   : {{"file": <path>, "test": <test_id>}}
      run-test    : {{"test": <test_id>}}
      create-file : {{"file": <path>}}

    Preconditions:
    - read-file BEFORE edit-file (you need the content)
    - run-test AFTER edit-file (verify the fix)

{reminder}
    """

    beliefs: str = dspy.InputField(
        desc="Current state: Repo structure, issue description, test status"
    )
    desire: str = dspy.InputField(
        desc="Goal: Fix the issue and make all tests pass"
    )
    previous_plan_summary: str = dspy.InputField(
        desc="Summary of the previous plan that was executed"
    )
    test_feedback: str = dspy.InputField(
        desc="Detailed test failure output from pytest execution"
    )
    repair_history: str = dspy.InputField(
        desc="Cumulative history of all previous repair attempts and their failures",
        default="",
    )
    verification_feedback: str = dspy.InputField(
        desc="Structured multi-layer verifier diagnostics",
        default="",
    )
    domain_context: str = dspy.InputField(
        desc="Domain action type constraints and rules",
        default="",
    )
    plan: BDIPlan = dspy.OutputField(
        desc="Corrected plan fixing all test failures, as a SINGLE CONNECTED DAG"
    )

    def __init__(self, *args, **kwargs):
        # Format docstring with prompts at instantiation
        self.__doc__ = self.__doc__.format(
            graph_structure=_GRAPH_STRUCTURE_COMMON,
            reminder=_REMINDER
        )
        super().__init__(*args, **kwargs)
