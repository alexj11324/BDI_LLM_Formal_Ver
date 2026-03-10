"""Feedback construction for SWE-bench verification layers.

Provides utilities to extract structured test failure information from
pytest output and build multi-layer verification context for the repair loop.

Mirrors:
- PlanBench's ``IntegratedVerifier.build_planner_feedback``
- TravelPlanner's ``build_evaluator_feedback``
"""

from __future__ import annotations

import re
from typing import Any

# Feedback extraction constants
MAX_FEEDBACK_CHARS = 3000  # Maximum characters from raw pytest output
MAX_FAILED_TESTS = 20  # Maximum number of FAILED test lines to include
MAX_ERROR_TESTS = 10  # Maximum number of ERROR test lines to include
MAX_ASSERTION_ERRORS = 10  # Maximum number of AssertionError lines
MAX_FAILURE_DETAILS = 5  # Maximum number of traceback sections
TRACEBACK_TAIL_CHARS = 500  # Characters from end of each traceback section
MAX_VERIFICATION_ERROR_CHARS = 500  # Chars from test errors in verification feedback


def build_test_feedback(
    test_output: str,
    test_returncode: int,
    *,
    max_chars: int = MAX_FEEDBACK_CHARS,
) -> str:
    """Extract structured failure information from pytest output.

    Note:
        This function is pytest-specific. If other test frameworks are used,
        the extraction patterns may need adaptation.

    Args:
        test_output: Raw stdout+stderr from pytest execution.
        test_returncode: Process return code (0=pass, else fail).
        max_chars: Maximum characters to include from raw output.

    Returns:
        Human-readable test failure summary for the repair prompt.

    Examples:
        >>> build_test_feedback("all tests passed", 0)
        'All tests passed.'

        >>> output = "FAILED tests/foo.py::test_x - AssertionError"
        >>> feedback = build_test_feedback(output, 1)
        >>> "FAILED TESTS:" in feedback
        True
    """
    if test_returncode == 0:
        return "All tests passed."

    parts: list[str] = []

    # Extract FAILED lines (e.g., "FAILED tests/foo.py::test_x - AssertionError")
    failed_tests = re.findall(
        r"^FAILED\s+(.+)$",
        test_output,
        re.MULTILINE,
    )
    if failed_tests:
        parts.append("FAILED TESTS:")
        for test in failed_tests[:MAX_FAILED_TESTS]:
            parts.append(f"  - {test.strip()}")
        parts.append("")

    # Extract ERROR lines (e.g., "ERROR tests/bar.py::test_y - ImportError")
    error_tests = re.findall(
        r"^ERROR\s+(.+)$",
        test_output,
        re.MULTILINE,
    )
    if error_tests:
        parts.append("ERROR TESTS:")
        for test in error_tests[:MAX_ERROR_TESTS]:
            parts.append(f"  - {test.strip()}")
        parts.append("")

    # Extract assertion errors
    assertion_errors = re.findall(
        r"(AssertionError:.*?)$",
        test_output,
        re.MULTILINE,
    )
    if assertion_errors:
        parts.append("ASSERTION ERRORS:")
        for err in assertion_errors[:MAX_ASSERTION_ERRORS]:
            parts.append(f"  - {err.strip()}")
        parts.append("")

    # Extract traceback snippets (sections between underscores before FAILED/ERROR)
    # Pattern: ___ header ___ followed by body text
    short_sections = re.findall(
        r"_{3,}\s+(.+?)\s+_{3,}\n([\s\S]*?)(?=\n_{3,}|\nFAILED|\nERROR|\Z)",
        test_output,
    )
    if short_sections:
        parts.append("FAILURE DETAILS:")
        for header, body in short_sections[:MAX_FAILURE_DETAILS]:
            trimmed = body.strip()[-TRACEBACK_TAIL_CHARS:]
            parts.append(f"  [{header.strip()}]")
            parts.append(f"  {trimmed}")
            parts.append("")

    # Add summary line from pytest (e.g., "=== 2 failed, 3 passed ===")
    summary_match = re.search(
        r"=+\s+([\d]+ (?:failed|error|passed).*?)\s+=+",
        test_output,
    )
    if summary_match:
        parts.append(f"SUMMARY: {summary_match.group(1)}")

    # If nothing was extracted, include raw tail
    if not parts:
        parts.append("RAW TEST OUTPUT (tail):")
        parts.append(test_output[-max_chars:])

    # Timeout special case
    if test_returncode == 124:
        parts.insert(0, "[TIMEOUT] Test execution timed out.\n")

    return "\n".join(parts)


def build_verification_context(
    structural_result: dict[str, Any],
    test_result: dict[str, Any],
) -> dict[str, Any]:
    """Build structured multi-layer verification context.

    Mirrors PlanBench's ``verification_context`` dict used in
    ``IntegratedVerifier.build_planner_feedback``.

    Args:
        structural_result: {"valid": bool, "errors": list[str]}
        test_result: {"valid": bool, "errors": str, "returncode": int}

    Returns:
        Structured verification context dict.
    """
    context: dict[str, Any] = {
        "layers": {
            "structural": {
                "valid": structural_result.get("valid", False),
                "errors": structural_result.get("errors", []),
            },
            "test_execution": {
                "valid": test_result.get("valid", False),
                "errors": test_result.get("errors", ""),
                "returncode": test_result.get("returncode", -1),
            },
        },
        "overall_valid": (
            structural_result.get("valid", False)
            and test_result.get("valid", False)
        ),
    }

    failed_layers = [
        name
        for name, layer in context["layers"].items()
        if not layer.get("valid", False)
    ]
    context["error_summary"] = (
        f"Failed layers: {', '.join(failed_layers)}"
        if failed_layers
        else "All layers passed"
    )

    return context


def format_verification_feedback(context: dict[str, Any]) -> str:
    """Format verification context into a human-readable string for repair prompts.

    Mirrors ``BDIPlanner._format_verification_feedback``.

    Args:
        context: Verification context dict with keys:
            - overall_valid: bool
            - error_summary: str
            - layers: dict[str, dict] with nested valid/errors

    Returns:
        Formatted multi-line string with layer-by-layer status.
    """
    parts: list[str] = [f"Overall: {'PASS' if context.get('overall_valid') else 'FAIL'}"]
    parts.append(context.get("error_summary", ""))
    parts.append("")

    layers = context.get("layers", {})
    for layer_name, layer_data in layers.items():
        status = "[PASS]" if layer_data.get("valid") else "[FAIL]"
        parts.append(f"[{layer_name}] {status}")
        errors = layer_data.get("errors", [])
        if isinstance(errors, str) and errors:
            # Truncate long test output
            parts.append(f"  {errors[:MAX_VERIFICATION_ERROR_CHARS]}")
        elif isinstance(errors, list):
            for err in errors[:MAX_ERROR_TESTS]:
                parts.append(f"  - {err}")
        parts.append("")

    return "\n".join(parts)
