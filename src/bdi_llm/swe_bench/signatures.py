"""DSPy Signature definitions for SWE-bench plan generation and repair.

Three signatures:
- ``GeneratePlanCodingBaseline`` — minimal Predict-only prompt (no CoT/LogiCoT)
- ``GeneratePlanCoding`` — re-exported from ``coding_planner`` (BDI w/ CoT)
- ``RepairPlanCoding`` — repair signature accepting test feedback + history
"""

from __future__ import annotations

import dspy

# Re-export the BDI version from coding_planner
from ..coding_planner import GeneratePlanCoding  # noqa: F401
from ..planner.prompts import (
    _GRAPH_STRUCTURE_COMMON,
    _REMINDER,
)
from ..schemas import BDIPlan


class GeneratePlanCodingBaseline(dspy.Signature):
    """You are a Software Engineer tasked with fixing a GitHub issue.

    Given a bug report (Beliefs) and a goal (Desire), produce a structured
    plan as a directed acyclic graph of file read/edit/test actions.

    CODING DOMAIN ACTIONS:
      read-file   : {"file": <path>}
      edit-file   : {"file": <path>, "test": <test_id>, "target": <class_or_function_name>}
      run-test    : {"test": <test_id>}
      create-file : {"file": <path>}

    Rules:
    1. read-file BEFORE edit-file.
    2. run-test AFTER edit-file.
    3. Minimise edits; do not break passing tests.
    4. `target` should be the class or function name you intend to modify.

    *** CRITICAL — NEVER EDIT TEST FILES ***
    - You must ONLY edit source code files (e.g. src/module.py, lib/utils.py).
    - NEVER use edit-file on test files (files in tests/ or named test_*.py).
    - The test files define the EXPECTED behavior. Fix the source code to match.
    """

    beliefs: str = dspy.InputField(
        desc="Current state: Repo structure, issue description, test status"
    )
    desire: str = dspy.InputField(
        desc="Goal: Fix the issue and make failing tests pass"
    )
    root_cause_analysis: str = dspy.OutputField(
        desc="What is the exact bug, which file/function, and what change?"
    )
    plan: BDIPlan = dspy.OutputField(
        desc="Execution plan as a DAG of coding actions"
    )


class RepairPlanCoding(dspy.Signature):
    f"""You previously generated a coding plan that FAILED test verification.
    The test runner found specific failures in your plan execution.

    Fix the plan by addressing EACH error reported by the test runner.

    CRITICAL REPAIR RULES:
    1. Read the test failure output CAREFULLY — identify the root cause.
    2. Your repaired plan must address every failing test.
    3. Do NOT remove test steps — add fixes for the failures.
    4. Preserve all passing tests (regression safety).
    5. You may add new read-file/edit-file steps as needed.

{_GRAPH_STRUCTURE_COMMON}

    CODING DOMAIN ACTIONS:
      read-file   : {{"file": <path>}}
      edit-file   : {{"file": <path>, "test": <test_id>, "target": <class_or_function_name>}}
      run-test    : {{"test": <test_id>}}
      create-file : {{"file": <path>}}

    Preconditions:
    - read-file BEFORE edit-file (you need the content)
    - run-test AFTER edit-file (verify the fix)
    - `target` should be the class or function name you intend to modify

{_REMINDER}
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


class RepairCodeChange(dspy.Signature):
    """Your previous code edit caused test failures. You are given:
    1. The original code snippet (before your edit).
    2. A unified diff showing exactly what you changed.
    3. The test failure output.

    DIAGNOSIS PROTOCOL:
    1. Read the test traceback — identify the exact assertion or exception.
    2. Read your previous diff — identify which green (+) line caused it.
    3. Explain the root cause in root_cause_analysis.
    4. Only then generate the corrective search_block and replace_block.

    The search_block must match the CURRENT file content (after your edit).
    """

    file_path: str = dspy.InputField(desc="Path of the file being repaired")
    original_snippet: str = dspy.InputField(
        desc="Original code of the target function/region before any edits"
    )
    previous_diff: str = dspy.InputField(
        desc="Unified diff showing the exact changes you made that caused test failures"
    )
    issue_description: str = dspy.InputField(
        desc="The GitHub issue / bug report"
    )
    test_feedback: str = dspy.InputField(
        desc="Structured test failure output showing what went wrong"
    )
    repair_history: str = dspy.InputField(
        desc="Summary of previous repair attempts and their outcomes",
        default="",
    )

    root_cause_analysis: str = dspy.OutputField(
        desc="Which specific line in your previous diff caused the test failure, and why?"
    )
    search_block: str = dspy.OutputField(
        desc="The exact code block to find in current_content (must match exactly)"
    )
    replace_block: str = dspy.OutputField(
        desc="The replacement code block that fixes the test failures"
    )
