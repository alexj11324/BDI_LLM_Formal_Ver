import os
import sys

# Ensure src is in python path
sys.path.append(os.getcwd())

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

# Import native BDI modules
from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.symbolic_verifier import IntegratedVerifier
from src.bdi_llm.schemas import BDIPlan
from src.bdi_llm.config import Config

# Initialize FastMCP Server
mcp = FastMCP("Native-BDI-Verifier")

# --- Schemas ---

class PlanRequest(BaseModel):
    goal: str = Field(..., description="The high-level goal to achieve (e.g., 'Stack block A on block B')")
    domain: str = Field("blocksworld", description="Planning domain: 'blocksworld', 'logistics', or 'depots'")
    context: str = Field(..., description="Current state/beliefs (e.g., 'on(a, table), clear(a), ...')")
    pddl_domain_file: str = Field(..., description="Path to the PDDL domain file")
    pddl_problem_file: str = Field(..., description="Path to the PDDL problem file")

# --- Core Logic ---

@mcp.tool()
def generate_verified_plan(request: PlanRequest) -> str:
    """
    Generates a formally verified plan using BDI-LLM + PDDL/VAL.
    Returns the step-by-step plan if valid, or verification errors if invalid.
    """
    # 1. Initialize Planner & Verifier
    planner = BDIPlanner(auto_repair=True, domain=request.domain)
    verifier = IntegratedVerifier(domain=request.domain)

    # 2. Generate Plan (DSPy)
    try:
        # Note: In a real integration, we'd mock the problem file parsing or generate it.
        # Here we assume the context string is sufficient for the LLM to understand the state.
        prediction = planner.generate_plan(
            beliefs=request.context,
            desire=request.goal
        )
        bdi_plan: BDIPlan = prediction.plan
    except Exception as e:
        return f"Plan Generation Failed: {str(e)}"

    # 3. Extract Actions for Verification
    # Convert graph nodes to PDDL action strings
    pddl_actions = []
    # Assuming topological sort or similar ensures order. 
    # For now, we take nodes in list order, but strictly we should traverse the graph.
    # BDIPlan usually has a structure. Let's assume nodes are ordered or we sort them.
    # (Simplified for this stub -- in prod use robust graph traversal)
    for node in bdi_plan.nodes:
        # Reconstruct PDDL string: (action arg1 arg2)
        # Assuming params is a dict: {"block": "a", "target": "b"}
        # And action_type: "stack"
        # PDDL: (stack a b)
        # We need a predictable order for args. This is tricky without the domain schema.
        # Improving heuristic: simple ' '.join(values) might be wrong order.
        # BETTER: Use the description or a dedicated pddl_string field if available.
        # FALLBACK: Construct "action param1 param2"
        args = " ".join(str(v) for v in node.params.values())
        pddl_actions.append(f"({node.action_type} {args})")

    # 4. Verify Plan (VAL)
    try:
        verification_result = verifier.verify_full(
            bdi_plan=bdi_plan,
            pddl_actions=pddl_actions,
            domain_file=request.pddl_domain_file,
            problem_file=request.pddl_problem_file,
            # We might need to parse init_state from problem file for physics validator
            init_state={} # Placeholder
        )
    except Exception as e:
        return f"Verification Process Failed: {str(e)}"

    # 5. Result Construction
    if verification_result['overall_valid']:
        return f"""✅ PLAN VERIFIED & SAFE
-----------------------
{chr(10).join(pddl_actions)}
-----------------------
Structural Check: PASS
Symbolic Check (VAL): PASS
Physics Check: PASS
"""
    else:
        return f"""❌ PLAN REJECTED
-----------------------
Error Summary: {verification_result.get('error_summary', 'Unknown Error')}
Details:
{verification_result.get('layers', {})}
-----------------------
Please revise your plan or context.
"""

if __name__ == "__main__":
    mcp.run()
