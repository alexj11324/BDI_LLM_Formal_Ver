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


def build_test_feedback(
    test_output: str,
    test_returncode: int,
    *,
    max_chars: int = 3000,
) -> str:
    """Extract structured failure information from pytest output.

    Args:
        test_output: Raw stdout+stderr from pytest execution.
        test_returncode: Process return code (0=pass, else fail).
        max_chars: Maximum characters to include from raw output.

    Returns:
        Human-readable test failure summary for the repair prompt.
    """
    if test_returncode == 0:
        return "All tests passed."

    parts: list[str] = []

    # Extract FAILED lines (pytest style)
    failed_tests = re.findall(
        r"^FAILED\s+(.+)$",
        test_output,
        re.MULTILINE,
    )
    if failed_tests:
        parts.append("FAILED TESTS:")
        for test in failed_tests[:20]:
            parts.append(f"  - {test.strip()}")
        parts.append("")

    # Extract Django-style FAIL/ERROR lines:
    #   FAIL: test_method (tests.module.TestClass)
    #   ERROR: test_method (tests.module.TestClass)
    django_failures = re.findall(
        r"^(?:FAIL|ERROR):\s+(.+)$",
        test_output,
        re.MULTILINE,
    )
    if django_failures:
        parts.append("DJANGO FAILURES:")
        for test in django_failures[:20]:
            parts.append(f"  - {test.strip()}")
        parts.append("")

    # Extract ERROR lines (pytest style)
    error_tests = re.findall(
        r"^ERROR\s+(.+)$",
        test_output,
        re.MULTILINE,
    )
    if error_tests:
        parts.append("ERROR TESTS:")
        for test in error_tests[:10]:
            parts.append(f"  - {test.strip()}")
        parts.append("")

    # Detect environment errors (ImportError, ModuleNotFoundError)
    import_errors = re.findall(
        r"(?:ImportError|ModuleNotFoundError):\s*(.+?)$",
        test_output,
        re.MULTILINE,
    )
    if import_errors:
        parts.append("IMPORT ERRORS (likely environment issue, not code bug):")
        for err in import_errors[:5]:
            parts.append(f"  - {err.strip()}")
        parts.append("")

    # Extract assertion errors
    assertion_errors = re.findall(
        r"(AssertionError:.*?)$",
        test_output,
        re.MULTILINE,
    )
    if assertion_errors:
        parts.append("ASSERTION ERRORS:")
        for err in assertion_errors[:10]:
            parts.append(f"  - {err.strip()}")
        parts.append("")

    # Extract traceback snippets (last N lines before FAILED/ERROR)
    short_sections = re.findall(
        r"_{3,}\s+(.+?)\s+_{3,}\n([\s\S]*?)(?=\n_{3,}|\nFAILED|\nERROR|\Z)",
        test_output,
    )
    if short_sections:
        parts.append("FAILURE DETAILS:")
        for header, body in short_sections[:5]:
            trimmed = body.strip()[-500:]
            parts.append(f"  [{header.strip()}]")
            parts.append(f"  {trimmed}")
            parts.append("")

    # Django-style traceback sections: "=" dividers with test names
    django_sections = re.findall(
        r"={50,}\n(FAIL|ERROR):\s+(.+?)\n-{50,}\n([\s\S]*?)(?=\n={50,}|\Z)",
        test_output,
    )
    if django_sections and not short_sections:
        parts.append("FAILURE DETAILS:")
        for kind, header, body in django_sections[:5]:
            trimmed = body.strip()[-500:]
            parts.append(f"  [{kind}: {header.strip()}]")
            parts.append(f"  {trimmed}")
            parts.append("")

    # Add summary line from pytest
    summary_match = re.search(
        r"=+\s+([\d]+ (?:failed|error|passed).*?)\s+=+",
        test_output,
    )
    if summary_match:
        parts.append(f"SUMMARY: {summary_match.group(1)}")

    # Django-style summary: "Ran X tests... FAILED (failures=N, errors=M)"
    django_summary = re.search(
        r"Ran\s+(\d+)\s+tests?.*\n(OK|FAILED\s*\(.*?\))",
        test_output,
    )
    if django_summary and not summary_match:
        parts.append(f"SUMMARY: {django_summary.group(0).strip()}")

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
    """
    parts: list[str] = [f"Overall: {'PASS' if context.get('overall_valid') else 'FAIL'}"]
    parts.append(context.get("error_summary", ""))
    parts.append("")

    layers = context.get("layers", {})
    for layer_name, layer_data in layers.items():
        status = "✓ PASS" if layer_data.get("valid") else "✗ FAIL"
        parts.append(f"[{layer_name}] {status}")
        errors = layer_data.get("errors", [])
        if isinstance(errors, str) and errors:
            # Truncate long test output
            parts.append(f"  {errors[:500]}")
        elif isinstance(errors, list):
            for err in errors[:10]:
                parts.append(f"  - {err}")
        parts.append("")

    return "\n".join(parts)
