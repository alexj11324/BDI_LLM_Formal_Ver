from mcp.server.fastmcp import FastMCP
import sys
import subprocess
import os
import tempfile
import shlex
from typing import List, Optional

# Add src to python path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.symbolic_verifier import IntegratedVerifier
from src.bdi_llm.config import Config

mcp = FastMCP("BDI-LLM Verifier")

def _verify_plan_logic(domain_pddl: str, problem_pddl: str, plan_actions: List[str]) -> str:
    """Helper function for verification logic."""
    d_path = None
    p_path = None
    try:
        # Create temp files for domain and problem
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pddl', delete=False) as d_file:
            d_file.write(domain_pddl)
            d_path = d_file.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.pddl', delete=False) as p_file:
            p_file.write(problem_pddl)
            p_path = p_file.name

        # We assume domain is blocksworld by default for now as we don't parse PDDL domain name easily
        verifier = IntegratedVerifier(domain="blocksworld")

        is_valid, errors = verifier.symbolic_verifier.verify_plan(d_path, p_path, plan_actions, verbose=True)

        if is_valid:
            return "Plan is VALID."
        else:
            return "Plan is INVALID.\nErrors:\n" + "\n".join(errors)

    except Exception as e:
        return f"Error during verification: {str(e)}"
    finally:
        if d_path and os.path.exists(d_path):
            os.unlink(d_path)
        if p_path and os.path.exists(p_path):
            os.unlink(p_path)

@mcp.tool()
def generate_plan(beliefs: str, desire: str, domain: str = "blocksworld") -> str:
    """
    Generates a BDI plan based on beliefs and desire for a specific domain.

    Args:
        beliefs: Current state of the world.
        desire: The goal to achieve.
        domain: Planning domain ("blocksworld", "logistics", "depots").
    """
    try:
        planner = BDIPlanner(domain=domain)
        prediction = planner(beliefs=beliefs, desire=desire)
        plan = prediction.plan

        output = [f"Plan Generated for goal: {plan.goal_description}"]
        output.append("Actions:")
        for node in plan.nodes:
            output.append(f"- [{node.id}] {node.action_type}: {node.description}")
            if node.params:
                output.append(f"  Params: {node.params}")

        # Format actions as PDDL-like for convenience
        pddl_actions = []
        for node in plan.nodes:
            params_str = " ".join(node.params.values()) if node.params else ""
            pddl_actions.append(f"({node.action_type} {params_str})")

        output.append("\nPDDL Actions (for verification):")
        output.append("\n".join(pddl_actions))

        return "\n".join(output)
    except Exception as e:
        return f"Error generating plan: {str(e)}"

@mcp.tool()
def verify_plan(domain_pddl: str, problem_pddl: str, plan_actions: List[str]) -> str:
    """
    Verifies a PDDL plan against a domain and problem definition.

    Args:
        domain_pddl: Content of the PDDL domain file.
        problem_pddl: Content of the PDDL problem file.
        plan_actions: List of PDDL actions (e.g. ["(pick-up a)", "(stack a b)"]).
    """
    return _verify_plan_logic(domain_pddl, problem_pddl, plan_actions)

def _execute_command(command: str) -> subprocess.CompletedProcess:
    """Executes a command securely."""
    # sourcery skip: avoid-subprocess
    args = shlex.split(command)
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True
    )

@mcp.tool()
def execute_verified_plan(
    domain_pddl: str,
    problem_pddl: str,
    plan_actions: List[str],
    command_to_execute: str,
    rationale: str
) -> str:
    """
    Verifies a PDDL plan and, if valid, executes a shell command.
    The "Trojan Horse" pattern: Execution is gated by formal verification.

    Args:
        domain_pddl: Content of the PDDL domain file.
        problem_pddl: Content of the PDDL problem file.
        plan_actions: List of PDDL actions representing the logic.
        command_to_execute: The actual shell command to run if verification passes.
        rationale: Explanation of why this command is being executed.
    """
    verification_result = _verify_plan_logic(domain_pddl, problem_pddl, plan_actions)

    if "Plan is VALID" in verification_result:
        # Proceed with execution
        try:
            # Execute command
            # Security warning: executing arbitrary commands.
            # In a real environment this should be sandboxed or restricted.
            result = _execute_command(command_to_execute)
            return f"Verification PASSED. Command Executed Successfully.\nOutput:\n{result.stdout}\nRationale: {rationale}"
        except subprocess.CalledProcessError as e:
            return f"Verification PASSED, but Command Execution Failed.\nError:\n{e.stderr}"
        except Exception as e:
            return f"Verification PASSED, but Command Execution Error: {str(e)}"
    else:
        return f"Verification FAILED. Command NOT Executed.\nRationale: {rationale}\nVerification Output:\n{verification_result}"

if __name__ == "__main__":
    mcp.run()
