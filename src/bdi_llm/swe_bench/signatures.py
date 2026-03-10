"""DSPy Signature definitions for SWE-bench plan generation and repair.

Three signatures:
- ``GeneratePlanCodingBaseline`` — minimal Predict-only prompt (no CoT/LogiCoT)
- ``GeneratePlanCoding`` — re-exported from ``coding_planner`` (BDI w/ CoT)
- ``RepairPlanCoding`` — repair signature accepting test feedback + history
"""

from __future__ import annotations

import dspy

from ..schemas import BDIPlan
from ..planner.prompts import (
    _GRAPH_STRUCTURE_COMMON,
    _REMINDER,
)

# Re-export the BDI version from coding_planner
from ..coding_planner import GeneratePlanCoding  # noqa: F401


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
      edit-file   : {{"file": <path>, "test": <test_id>}}
      run-test    : {{"test": <test_id>}}
      create-file : {{"file": <path>}}

    Preconditions:
    - read-file BEFORE edit-file (you need the content)
    - run-test AFTER edit-file (verify the fix)

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
    """Your previous code edit did NOT fix the issue — tests are still failing.

    You are given:
    1. The file path and its ORIGINAL content (before any edits).
    2. The CURRENT content (your previous edit that failed tests).
    3. The test failure output explaining exactly what went wrong.
    4. The original issue description.

    Produce an IMPROVED version of the file that fixes the test failures
    without breaking other tests. Return the COMPLETE file content.

    RULES:
    1. Read the test error output CAREFULLY — identify the root cause.
    2. Your fix must address the specific assertion/error, not just the symptom.
    3. Preserve all existing functionality — only change what is needed.
    4. Do NOT add unrelated refactoring or style changes.
    """

    file_path: str = dspy.InputField(desc="Path of the file being repaired")
    original_content: str = dspy.InputField(
        desc="File content at base commit (before any edits)"
    )
    current_content: str = dspy.InputField(
        desc="File content after your previous edit (which failed tests)"
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

    new_content: str = dspy.OutputField(
        desc="The complete improved file content that fixes the test failures"
    )
