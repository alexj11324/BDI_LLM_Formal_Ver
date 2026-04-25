"""BDI-LLM MCP Server Interface.

This module exposes the BDI-LLM verifier capabilities as MCP (Model Context Protocol) tools.
It provides two main tools:
1. generate_plan: Generate BDI plans from beliefs and desires
2. verify_plan: Verify PDDL plans against domain and problem definitions

The server uses FastMCP for easy MCP tool registration and supports multiple planning domains
(blocksworld, logistics, depots).
"""

import os
import tempfile

from mcp.server.fastmcp import FastMCP

# Imports rely on the project being installed (pip install -e .)
# or PYTHONPATH including the repository root.
from bdi_llm.planner import BDIPlanner
from bdi_llm.symbolic_verifier import IntegratedVerifier

mcp = FastMCP("BDI-LLM Verifier")


def _verify_plan_logic(
    domain_pddl: str,
    problem_pddl: str,
    plan_actions: list[str],
    domain: str = "blocksworld",
) -> tuple[bool, str]:
    """Run symbolic verification and return structured status + message."""
    d_path = None
    p_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pddl", delete=False) as d_file:
            d_file.write(domain_pddl)
            d_path = d_file.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".pddl", delete=False) as p_file:
            p_file.write(problem_pddl)
            p_path = p_file.name

        verifier = IntegratedVerifier(domain=domain)
        is_valid, errors = verifier.symbolic_verifier.verify_plan(
            d_path,
            p_path,
            plan_actions,
            verbose=True,
        )

        if is_valid:
            return True, "Plan is VALID."
        return False, "Plan is INVALID.\nErrors:\n" + "\n".join(errors)

    except Exception as e:
        return False, f"Error during verification: {str(e)}"
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
            params_str = " ".join(str(v) for v in node.params.values()) if node.params else ""
            pddl_actions.append(f"({node.action_type} {params_str})")

        output.append("\nPDDL Actions (for verification):")
        output.append("\n".join(pddl_actions))

        return "\n".join(output)
    except Exception as e:
        return f"Error generating plan: {str(e)}"


@mcp.tool()
def verify_plan(
    domain_pddl: str,
    problem_pddl: str,
    plan_actions: list[str],
    domain: str = "blocksworld",
) -> str:
    """
    Verifies a PDDL plan against a domain and problem definition.

    Args:
        domain_pddl: Content of the PDDL domain file.
        problem_pddl: Content of the PDDL problem file.
        plan_actions: List of PDDL actions (e.g. ["(pick-up a)", "(stack a b)"]).
        domain: Planning domain name ("blocksworld", "logistics", "depots").
    """
    _, message = _verify_plan_logic(domain_pddl, problem_pddl, plan_actions, domain)
    return message


def execute_verified_plan(
    domain_pddl: str,
    problem_pddl: str,
    plan_actions: list[str],
    command_to_execute: str,
    rationale: str,
    domain: str = "blocksworld",
) -> str:
    """
    Legacy compatibility helper.

    This function is intentionally NOT registered as an MCP tool. Older callers
    may still import it directly, but direct shell command execution is disabled
    because PDDL validity alone does not bind a plan to an arbitrary local
    command.

    Args:
        domain_pddl: Content of the PDDL domain file.
        problem_pddl: Content of the PDDL problem file.
        plan_actions: List of PDDL actions representing the logic.
        command_to_execute: Ignored. Arbitrary local command execution is disabled.
        rationale: Explanation of why this command is being executed.
        domain: Planning domain name ("blocksworld", "logistics", "depots").
    """
    is_valid, verification_message = _verify_plan_logic(
        domain_pddl,
        problem_pddl,
        plan_actions,
        domain,
    )

    if not is_valid:
        return (
            "Verification FAILED. Command NOT Executed.\n"
            f"Rationale: {rationale}\n"
            f"Verification Output:\n{verification_message}"
        )

    return (
        "Verification PASSED. Command execution is disabled.\n"
        "The verified PDDL plan was not tied to the requested local command, "
        "so no command was run.\n"
        f"Requested command: {command_to_execute}\n"
        f"Rationale: {rationale}\n"
        f"Verification Output:\n{verification_message}"
    )


if __name__ == "__main__":
    mcp.run()
