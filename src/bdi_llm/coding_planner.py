"""Coding BDI Planner for software engineering tasks.

Provides a specialized BDI planner for code modification tasks:
- ``CodingBDIPlanner`` — BDI planner with coding-specific action types
- ``GeneratePlanCoding`` — DSPy signature for coding plan generation
- ``ImplementCodeChange`` — DSPy signature for file editing

Coding domain action types:
- read-file: Read file contents
- edit-file: Modify file contents
- run-test: Execute tests
- create-file: Create new files
"""

from __future__ import annotations

import dspy

from .planner import BDIPlanner
from .planner.domain_spec import DomainSpec
from .planner.prompts import (
    _GRAPH_STRUCTURE_COMMON,
    _LOGICOT_HEADER,
    _LOGICOT_PROTOCOL_DETAILED,
    _REMINDER,
    _STATE_TRACKING_HEADER,
)
from .schemas import BDIPlan


class GeneratePlanCoding(dspy.Signature):
    __doc__ = f"""
    You are a Senior Software Engineer BDI Agent.
    Given a GitHub Issue (bug report) and Repository Context,
    generate a formal Intention (Plan) to fix the bug.

    Your plan must be a Directed Acyclic Graph (DAG) of technical actions.

{_GRAPH_STRUCTURE_COMMON}

    CODING DOMAIN ACTIONS:

    action_type must be one of:
      read-file | edit-file | run-test | create-file

    params:
      read-file   : {{"file": <path>}}
      edit-file   : {{"file": <path>, "test": <test_id>}}
      run-test    : {{"test": <test_id>}}
      create-file : {{"file": <path>}}

    PRECONDITIONS & LOGIC:
    1. You MUST `read-file` before you can `edit-file` (you need to know what to change).
    2. You MUST `run-test` AFTER `edit-file` to verify the fix.
    3. `edit-file` takes a "test" parameter to indicate WHICH test failure
       this edit is intended to fix.
    4. If a test is failing, you must edit a file to fix it.

    EXAMPLE PLAN:
    Nodes:
      n1: read-file(src/utils.py)
      n2: edit-file(src/utils.py, test_id="test_utils.py::test_sort")
      n3: run-test(test_utils.py::test_sort)
    Edges:
      n1 -> n2 -> n3

{_STATE_TRACKING_HEADER}

    **CODING State Table Format:**
    ```
    | File/Test | Status | Known Content? |
    |-----------|--------|----------------|
    | src/main.py | exists | no |
    | test_api.py | failing | yes |
    ```

{_LOGICOT_HEADER}

{_LOGICOT_PROTOCOL_DETAILED}

{_REMINDER}
    """
    beliefs: str = dspy.InputField(desc="Current state: Repo structure, filed issues, test status")
    desire: str = dspy.InputField(desc="The goal: Fix the issue and pass tests")
    plan: BDIPlan = dspy.OutputField(desc="Execution plan as a DAG")


class ImplementCodeChange(dspy.Signature):
    """You are a Senior Software Engineer implementing a specific code change.

    You will be given:
    1. The File Path and its Current Content.
    2. The Goal (GitHub Issue).
    3. The specific Plan Step description (e.g., "Add null check to function X").

    You must return the NEW content of the file with the changes applied.

    Output Format:
    - Return complete file content (not a diff/patch)
    - Preserve existing code style and formatting
    - Ensure all imports and dependencies are maintained
    """
    file_path: str = dspy.InputField(desc="Path to the file being edited")
    current_content: str = dspy.InputField(desc="Current content of the file")
    issue_description: str = dspy.InputField(desc="GitHub issue description")
    step_description: str = dspy.InputField(desc="Specific change to implement")
    new_content: str = dspy.OutputField(desc="The complete new content of the file")


class CodingBDIPlanner(BDIPlanner):
    """BDI Planner specialized for coding/software engineering tasks.

    Uses a coding-specific domain spec with action types:
    - read-file, edit-file, run-test, create-file

    Provides both BDI (with CoT) and baseline (without CoT) generation methods.
    """

    def __init__(self, auto_repair: bool = True) -> None:
        """Initialize the coding planner.

        Args:
            auto_repair: Whether to enable automatic repair on verification failures.
        """
        coding_domain_spec = DomainSpec(
            name="coding",
            valid_action_types=frozenset({"read-file", "edit-file", "run-test", "create-file"}),
            required_params={
                "read-file": frozenset({"file"}),
                "edit-file": frozenset({"file", "test"}),
                "run-test": frozenset({"test"}),
                "create-file": frozenset({"file"}),
            },
            signature_class=GeneratePlanCoding,
        )
        super().__init__(auto_repair=auto_repair, domain_spec=coding_domain_spec)

        self._generate_program = dspy.ChainOfThought(GeneratePlanCoding)
        self._baseline_program = dspy.Predict(GeneratePlanCoding)
        self.implement_change = dspy.ChainOfThought(ImplementCodeChange)

    def generate_plan_baseline(self, beliefs: str, desire: str) -> BDIPlan:
        """Generate plan without CoT reasoning (baseline mode).

        Args:
            beliefs: Current state (repo structure, filed issues, test status).
            desire: The goal (fix the issue and pass tests).

        Returns:
            BDIPlan without structural verification.

        Raises:
            ValueError: If LLM returns no parseable plan.
        """
        pred = self._baseline_program(beliefs=beliefs, desire=desire)
        plan = pred.plan
        if plan is None:
            raise ValueError("LLM returned no parseable plan (baseline)")
        return plan
