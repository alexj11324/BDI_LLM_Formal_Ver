#!/usr/bin/env python3
"""
VAL Runner — Low-level interface to the VAL (Validating Action Language) executable.

Extracted from symbolic_verifier.py to isolate subprocess management, temporary file
handling, and raw VAL output parsing from the higher-level verification logic.

Author: BDI-LLM Research
Date: 2026-03-05
"""

import os
import re
import subprocess
import tempfile

# ---------------------------------------------------------------------------
# Compiled regex patterns shared by all extraction helpers
# ---------------------------------------------------------------------------

_RE_PRECOND_VERBOSE = re.compile(
    r"Plan failed because of unsatisfied precondition in:\s*\n\s*(\(.+?\))",
    re.DOTALL,
)
_RE_REPAIR_ADVICE = re.compile(
    r"Plan Repair Advice:\s*\n(.*?)(?:\n\s*\n|\nFailed plans:|\Z)",
    re.DOTALL,
)
_RE_PRECOND_LEGACY = re.compile(r"Precondition not satisfied: (.+)")
_RE_INVALID_ACTION = re.compile(r"Invalid action: (.+)")
_RE_TYPE_ERROR = re.compile(r"Type error: (.+)")


# ---------------------------------------------------------------------------
# Temporary plan-file helpers
# ---------------------------------------------------------------------------


def create_plan_file(actions: list[str]) -> str:
    """Create a temporary PDDL plan file and return its path.

    Each action is formatted to be surrounded by parentheses if necessary.
    The caller is responsible for deleting the file after use.
    """

    def _formatted(action_list):
        for action in action_list:
            action_str = action.strip()
            if not action_str.startswith("("):
                action_str = f"({action_str})"
            yield f"{action_str}\n"

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".pddl",
        delete=False,
        prefix="bdi_plan_",
    ) as f:
        f.writelines(_formatted(actions))
        return f.name


# ---------------------------------------------------------------------------
# VAL execution
# ---------------------------------------------------------------------------


def run_val(
    val_path: str,
    domain_file: str,
    problem_file: str,
    plan_actions: list[str],
    *,
    check_goal: bool = True,
    verbose: bool = False,
    timeout: int = 30,
) -> tuple[bool, list[str]]:
    """Run the VAL validator on a set of PDDL actions and return ``(is_valid, errors)``.

    This function handles:
    * creating and cleaning up the temporary plan file
    * spawning the VAL subprocess with ``-v`` for verbose output
    * parsing the raw output into a structured ``(bool, list[str])`` result

    Args:
        val_path: Absolute path to the VAL ``validate`` executable.
        domain_file: Path to the PDDL domain file.
        problem_file: Path to the PDDL problem file.
        plan_actions: List of PDDL action strings, e.g. ``["(pick-up a)", "(stack a b)"]``.
        check_goal: When *False* (prefix verification), treat
            "executed but goal not satisfied" as success.
        verbose: If *True*, append the full VAL output to the error list.
        timeout: Maximum seconds to wait for VAL.

    Returns:
        ``(is_valid, error_messages)``
    """
    if not plan_actions:
        return False, ["Empty plan - no actions to verify"]

    plan_file = create_plan_file(plan_actions)

    try:
        result = subprocess.run(
            [val_path, "-v", domain_file, problem_file, plan_file],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr

        is_valid, errors = parse_val_output(output, verbose)

        # When check_goal=False (prefix verification), treat
        # "executed but goal not satisfied" as success.
        if not check_goal and not is_valid:
            goal_only_errors = all(
                "goal not satisfied" in e.lower() or "plan executed but goal" in e.lower() for e in errors
            )
            if goal_only_errors and "Plan executed successfully" in output:
                return True, []

        return is_valid, errors

    except subprocess.TimeoutExpired:
        return False, [f"VAL validation timeout (>{timeout}s)"]

    except FileNotFoundError:
        return False, [f"VAL executable not found: {val_path}"]

    except OSError as e:
        if e.errno == 8:
            return False, [f"VAL executable incompatible with current OS (Exec format error): {val_path}"]
        return False, [f"VAL execution error (OSError): {str(e)}"]

    except Exception as e:
        return False, [f"VAL execution error: {str(e)}"]

    finally:
        if os.path.exists(plan_file):
            os.unlink(plan_file)


# ---------------------------------------------------------------------------
# VAL output parsing
# ---------------------------------------------------------------------------


def parse_val_output(output: str, verbose: bool) -> tuple[bool, list[str]]:
    """Parse VAL validator output (with ``-v`` verbose flag).

    VAL ``-v`` outputs patterns like:

    * ``"Plan executed successfully - checking goal"`` + no ``"Goal not satisfied"`` → Valid
    * ``"Plan failed because of unsatisfied precondition in:"`` → Precondition failure
    * ``"Goal not satisfied"`` / ``"Plan invalid"`` → Goal not achieved
    * ``"Error in type-checking!"`` → Type error in action parameters
    * ``"Bad plan"`` / ``"Bad problem file!"`` → Structural PDDL error
    """
    errors: list[str] = []

    if "Plan executed successfully" in output and "Goal not satisfied" not in output and "Plan invalid" not in output:
        return True, []

    if "Goal not satisfied" in output or "Plan invalid" in output:
        errors = extract_val_errors(output)
        if verbose:
            errors.append(f"\nFull VAL output:\n{output}")
        return False, errors

    if "Plan failed" in output or "Bad plan" in output:
        errors = extract_val_errors(output)
        if verbose:
            errors.append(f"\nFull VAL output:\n{output}")
        return False, errors

    if "Error in type-checking" in output or "Bad problem file" in output:
        errors = extract_val_errors(output)
        if verbose:
            errors.append(f"\nFull VAL output:\n{output}")
        return False, errors

    # Unknown output format
    if verbose:
        errors.append(f"VAL output unclear:\n{output}")
    else:
        errors.append("VAL validation result unclear (enable verbose for details)")
    return False, errors


def extract_val_errors(output: str) -> list[str]:
    """Extract specific error messages from VAL ``-v`` verbose output.

    With the ``-v`` flag, VAL provides:
    * Which action failed and at which step
    * Unsatisfied preconditions with specific predicates
    * Plan Repair Advice with concrete fixes
    """
    errors: list[str] = []

    # Pattern 1 – unsatisfied precondition (verbose)
    precond_verbose = _RE_PRECOND_VERBOSE.search(output)
    if precond_verbose:
        failed_action = precond_verbose.group(1).strip()
        errors.append(f"Unsatisfied precondition in action: {failed_action}")

    # Pattern 2 – Plan Repair Advice section
    repair_advice = _RE_REPAIR_ADVICE.search(output)
    if repair_advice:
        advice_text = repair_advice.group(1).strip()
        errors.append(f"VAL Repair Advice: {advice_text}")

    # Pattern 3 – Goal not satisfied
    if "Goal not satisfied" in output:
        errors.append("Plan executed but goal not satisfied")

    # Pattern 4 – legacy precondition format
    for match in _RE_PRECOND_LEGACY.finditer(output):
        errors.append(f"Precondition violation: {match.group(1)}")

    # Pattern 5 – type-checking errors
    if "Error in type-checking" in output:
        errors.append("Type-checking error: action parameters have invalid types")

    # Pattern 6 – invalid action parameters
    for match in _RE_INVALID_ACTION.finditer(output):
        errors.append(f"Invalid action: {match.group(1)}")

    # Pattern 7 – type errors
    for match in _RE_TYPE_ERROR.finditer(output):
        errors.append(f"Type error: {match.group(1)}")

    # Fallback – generic message if nothing specific was extracted
    if not errors:
        lines = output.split("\n")
        for line in lines:
            if "error" in line.lower() or "fail" in line.lower():
                errors.append(line.strip())
                break
        if not errors:
            errors.append("Plan validation failed (reason unclear)")

    return errors
