
import dspy
from typing import Set, Dict
from .planner import BDIPlanner, _GRAPH_STRUCTURE_COMMON, _STATE_TRACKING_HEADER, _LOGICOT_HEADER, _LOGICOT_PROTOCOL_DETAILED, _REMINDER
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
    3. `edit-file` takes a "test" parameter to indicate WHICH test failure this edit is intended to fix.
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
    __doc__ = """
    You are a Senior Software Engineer.
    Your task is to implementing a specific code change (Edit) as part of a larger plan.
    
    You will be given:
    1. The File Path and its Current Content.
    2. The Goal (Github Issue).
    3. The specific Plan Step description (e.g., "Add null check to function X").
    
    You must return the NEW content of the file.
    """
    file_path: str = dspy.InputField()
    current_content: str = dspy.InputField()
    issue_description: str = dspy.InputField()
    step_description: str = dspy.InputField()
    
    # We use a simple output field for now. In a real system, we might use a diff format.
    new_content: str = dspy.OutputField(desc="The complete new content of the file")


class CodingBDIPlanner(BDIPlanner):
    def __init__(self, auto_repair: bool = True):
        super().__init__(auto_repair=auto_repair, domain="coding")
        
        # Override the signature with our coding-specific one
        self.generate_plan = dspy.ChainOfThought(GeneratePlanCoding)
        
        # Add the code implementation module
        self.implement_change = dspy.ChainOfThought(ImplementCodeChange)
        
        # Define coding-specific constraints
        self._valid_action_types["coding"] = {
            "read-file", "edit-file", "run-test", "create-file"
        }
        
        self._required_params["coding"] = {
            "read-file": {"file"},
            "edit-file": {"file", "test"},
            "run-test": {"test"},
            "create-file": {"file"},
        }
