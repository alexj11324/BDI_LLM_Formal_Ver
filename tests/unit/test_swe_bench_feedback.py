"""Unit tests for SWE-bench feedback module."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bdi_llm.swe_bench.feedback import (
    build_test_feedback,
    build_verification_context,
    format_verification_feedback,
)


# ---------------------------------------------------------------------------
# build_test_feedback
# ---------------------------------------------------------------------------


def test_build_test_feedback_all_passed():
    result = build_test_feedback("all passed", 0)
    assert result == "All tests passed."


def test_build_test_feedback_extracts_failed_tests():
    output = (
        "FAILED tests/test_foo.py::test_one - AssertionError\n"
        "FAILED tests/test_bar.py::test_two - TypeError\n"
        "===== 2 failed, 3 passed =====\n"
    )
    result = build_test_feedback(output, 1)
    assert "FAILED TESTS:" in result
    assert "tests/test_foo.py::test_one" in result
    assert "tests/test_bar.py::test_two" in result
    assert "SUMMARY:" in result


def test_build_test_feedback_extracts_errors():
    output = "ERROR tests/test_x.py - ImportError\n===== 1 error =====\n"
    result = build_test_feedback(output, 1)
    assert "ERROR TESTS:" in result
    assert "tests/test_x.py" in result


def test_build_test_feedback_timeout():
    result = build_test_feedback("execution took too long", 124)
    assert "[TIMEOUT]" in result


def test_build_test_feedback_empty_output():
    result = build_test_feedback("", 1)
    assert "RAW TEST OUTPUT" in result


# ---------------------------------------------------------------------------
# build_verification_context
# ---------------------------------------------------------------------------


def test_build_verification_context_all_pass():
    ctx = build_verification_context(
        structural_result={"valid": True, "errors": []},
        test_result={"valid": True, "errors": "", "returncode": 0},
    )
    assert ctx["overall_valid"] is True
    assert ctx["error_summary"] == "All layers passed"


def test_build_verification_context_structural_fail():
    ctx = build_verification_context(
        structural_result={"valid": False, "errors": ["disconnected graph"]},
        test_result={"valid": True, "errors": "", "returncode": 0},
    )
    assert ctx["overall_valid"] is False
    assert "structural" in ctx["error_summary"]


def test_build_verification_context_test_fail():
    ctx = build_verification_context(
        structural_result={"valid": True, "errors": []},
        test_result={"valid": False, "errors": "2 failed", "returncode": 1},
    )
    assert ctx["overall_valid"] is False
    assert "test_execution" in ctx["error_summary"]


# ---------------------------------------------------------------------------
# format_verification_feedback
# ---------------------------------------------------------------------------


def test_format_verification_feedback():
    ctx = build_verification_context(
        structural_result={"valid": True, "errors": []},
        test_result={"valid": False, "errors": "1 failed", "returncode": 1},
    )
    text = format_verification_feedback(ctx)
    assert "FAIL" in text
    assert "structural" in text
    assert "test_execution" in text
