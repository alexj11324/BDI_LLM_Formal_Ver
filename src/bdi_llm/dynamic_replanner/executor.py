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
    
    Uses prefix verification with check_goal=False for intermediate steps:
    - Prefix [A]: check_goal=False → only checks if action A's preconditions are met
    - Prefix [A, B]: check_goal=False → checks if B is executable after A
    - Full plan [A, B, ... Z]: check_goal=True → final goal check
    
    This distinguishes between:
    - Action execution failure (precondition violated) → triggers replanning
    - Goal not yet satisfied (normal for partial plans) → not a failure
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
        if not plan_actions:
            return ExecutionResult(
                success=False,
                executed_actions=[],
                failed_action=None,
                failure_reason=["Empty plan - no actions to execute"],
            )

        executed = []
        total = len(plan_actions)

        for i, action in enumerate(plan_actions):
            is_last_step = (i == total - 1)
            test_plan = executed + [action]

            # For intermediate steps: only check preconditions (ignore goal)
            # For the final step: also check goal satisfaction
            is_valid, errors = self.verifier.verify_plan(
                self.domain_file, 
                self.problem_file, 
                test_plan, 
                verbose=False,
                check_goal=is_last_step,
            )
            
            if is_valid:
                executed.append(action)
            else:
                # VAL caught a real failure at this step (precondition violation)
                return ExecutionResult(
                    success=False,
                    executed_actions=executed,
                    failed_action=action,
                    failure_reason=errors,
                )
                
        # All steps succeeded AND goal is satisfied (check_goal=True on last step)
        return ExecutionResult(
            success=True,
            executed_actions=executed,
            failed_action=None,
            failure_reason=None,
        )
