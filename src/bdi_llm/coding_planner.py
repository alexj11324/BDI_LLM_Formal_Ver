

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
      edit-file   : {{"file": <path>, "test": <test_id>, "target": <class_or_function_name>}}
      run-test    : {{"test": <test_id>}}
      create-file : {{"file": <path>}}

    PRECONDITIONS & LOGIC:
    1. You MUST `read-file` before you can `edit-file` (you need to know what to change).
    2. You MUST `run-test` AFTER `edit-file` to verify the fix.
    3. `edit-file` takes a "test" parameter to indicate WHICH test failure
       this edit is intended to fix.
    4. If a test is failing, you must edit a file to fix it.
    5. `target` should be the class or function name you intend to modify.

    EXAMPLE PLAN:
    Nodes:
      n1: read-file(src/utils.py)
      n2: edit-file(src/utils.py, test_id="test_utils.py::test_sort", target="sort_items")
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
    __doc__ = """
    You are a Senior Software Engineer implementing a targeted code edit.

    You will be given:
    1. The File Path and its Current Content.
    2. The Goal (Github Issue).
    3. The specific Plan Step description.

    You must return a SEARCH/REPLACE edit. The search_block must match the
    current file content EXACTLY (including whitespace). The replace_block
    is what it should be changed to. Only change the minimum necessary code.

    RULES:
    1. Copy the EXACT code from current_content for search_block — every
       character, space, and newline must match.
    2. Include enough context (3-5 surrounding lines) to make the match unique.
    3. Keep replace_block minimal — only change what is needed for the fix.
    4. Do NOT rewrite the entire file. Do NOT add unrelated changes.
    """
    file_path: str = dspy.InputField()
    current_content: str = dspy.InputField()
    issue_description: str = dspy.InputField()
    step_description: str = dspy.InputField()

    search_block: str = dspy.OutputField(
        desc="The exact code block to find in the file (must match current_content exactly)"
    )
    replace_block: str = dspy.OutputField(
        desc="The replacement code block"
    )


class CodingBDIPlanner(BDIPlanner):
    def __init__(self, auto_repair: bool = True):
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
        """Generate plan without CoT reasoning (baseline mode)."""
        pred = self._baseline_program(beliefs=beliefs, desire=desire)
        plan = pred.plan
        if plan is None:
            raise ValueError("LLM returned no parseable plan (baseline)")
        return plan
