from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.bdi_llm.symbolic_verifier import PDDLSymbolicVerifier


@dataclass
class ExecutionResult:
    """
    Represents the result of executing a plan step-by-step.
    """
    success: bool
    executed_actions: List[str]
    failed_action: Optional[str]
    failure_reason: Optional[List[str]]


class PlanExecutor:
    """
    Executes a PDDL plan step-by-step using VAL to intercept the exact failure point.
    Instead of building a full PDDL simulator natively, we verify prefixes of the plan:
    [A], then [A, B], then [A, B, C].
    If [A, B] is valid but [A, B, C] fails, C is the failing step.
    """
    def __init__(self, domain_file: str, problem_file: str):
        self.verifier = PDDLSymbolicVerifier()
        self.domain_file = domain_file
        self.problem_file = problem_file
        
    def execute(self, plan_actions: List[str]) -> ExecutionResult:
        """
        Executes actions step-wise until completion or the first failure.
        
        Args:
            plan_actions: List of PDDL action strings (e.g. ['(pick-up a)', ...])
        Returns:
            ExecutionResult containing what worked and exactly what failed.
        """
        executed = []
        for action in plan_actions:
            test_plan = executed + [action]
            is_valid, errors = self.verifier.verify_plan(
                self.domain_file, 
                self.problem_file, 
                test_plan, 
                verbose=False
            )
            
            if is_valid:
                executed.append(action)
            else:
                # VAL caught a failure at this step
                return ExecutionResult(
                    success=False,
                    executed_actions=executed,
                    failed_action=action,
                    failure_reason=errors
                )
                
        # All steps succeeded
        return ExecutionResult(
            success=True,
            executed_actions=executed,
            failed_action=None,
            failure_reason=None
        )
