from mcp.server.fastmcp import FastMCP
from typing import List
from pydantic import BaseModel, Field
from .constraints import ConstraintEngine, PlanStep
from .sandbox import Sandbox

# Initialize FastMCP
mcp = FastMCP("BDI-Verifier")

class PlanStepModel(BaseModel):
    action: str = Field(..., description="Action type: EXECUTE, DELETE, READ, WRITE")
    target: str = Field(..., description="Target file path or command string")

class PlanInput(BaseModel):
    steps: List[PlanStepModel] = Field(..., description="List of steps to execute")
    rationale: str = Field(..., description="Reasoning for this plan")

@mcp.tool()
def apply_verified_changes(plan: PlanInput) -> str:
    """
    The ONLY allowed way to modify code. Takes a plan, verifies it against BDI invariants, and executes if safe.
    """
    
    # 1. Convert to internal objects
    internal_steps = [PlanStep(s.action, s.target) for s in plan.steps]
    
    # 2. Verification (BDI Layer)
    verifier = ConstraintEngine()
    error = verifier.verify_plan(internal_steps)
    
    if error:
        # RETURN failure message to the LLM (Back-prompting)
        return f"PLAN REJECTED by Formal Verification:\n{error}\n\nPlease revise your plan to satisfy the constraints."
    
    # 3. Execution (Sandbox Layer)
    sandbox = Sandbox()
    try:
        sandbox.execute_plan(internal_steps)
        return "Plan executed successfully."
    except Exception as e:
        return f"Plan verification passed, but execution failed: {str(e)}"

if __name__ == "__main__":
    mcp.run()
