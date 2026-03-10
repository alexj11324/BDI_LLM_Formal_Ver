"""Unit tests for SWE-bench TaskAdapter."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bdi_llm.swe_bench.adapter import SWEBenchTaskAdapter, _parse_test_field


# ---------------------------------------------------------------------------
# _parse_test_field
# ---------------------------------------------------------------------------


def test_parse_test_field_none():
    assert _parse_test_field(None) == []


def test_parse_test_field_empty_string():
    assert _parse_test_field("") == []


def test_parse_test_field_json_list():
    raw = '["tests/foo.py::test_one", "tests/bar.py::test_two"]'
    result = _parse_test_field(raw)
    assert result == ["tests/foo.py::test_one", "tests/bar.py::test_two"]


def test_parse_test_field_python_list():
    raw = ["tests/a.py::test_x", "tests/b.py::test_y"]
    result = _parse_test_field(raw)
    assert result == ["tests/a.py::test_x", "tests/b.py::test_y"]


def test_parse_test_field_multiline_string():
    raw = "tests/a.py::test_x\ntests/b.py::test_y\n"
    result = _parse_test_field(raw)
    assert result == ["tests/a.py::test_x", "tests/b.py::test_y"]


# ---------------------------------------------------------------------------
# SWEBenchTaskAdapter
# ---------------------------------------------------------------------------


def test_adapter_basic():
    adapter = SWEBenchTaskAdapter()
    instance = {
        "instance_id": "django__django-16379",
        "repo": "django/django",
        "base_commit": "abc123",
        "version": "4.2",
        "problem_statement": "Bug in form validation",
        "FAIL_TO_PASS": '["tests/forms.py::test_validate"]',
        "PASS_TO_PASS": '["tests/forms.py::test_basic"]',
        "hints_text": "Check the validate method",
    }

    task = adapter.to_planning_task(instance)

    assert task.task_id == "django__django-16379"
    assert task.domain_name == "swe-bench"
    assert "django/django" in task.beliefs
    assert "Bug in form validation" in task.desire
    assert "Check the validate method" in task.desire
    assert task.domain_context is not None
    assert "read-file" in task.domain_context
    assert task.metadata["instance_id"] == "django__django-16379"
    assert task.metadata["FAIL_TO_PASS"] == ["tests/forms.py::test_validate"]


def test_adapter_with_repo_snapshot():
    adapter = SWEBenchTaskAdapter(repo_snapshot="src/main.py\ntests/test_main.py")
    instance = {
        "instance_id": "test-123",
        "repo": "org/repo",
        "base_commit": "xyz",
        "version": "1.0",
        "problem_statement": "Fix bug",
        "FAIL_TO_PASS": "[]",
        "PASS_TO_PASS": "[]",
    }

    task = adapter.to_planning_task(instance)

    assert "src/main.py" in task.beliefs
    assert "tests/test_main.py" in task.beliefs


def test_adapter_missing_instance_id():
    adapter = SWEBenchTaskAdapter()
    try:
        adapter.to_planning_task({"repo": "a/b"})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "instance_id" in str(e)


def test_adapter_wrong_type():
    adapter = SWEBenchTaskAdapter()
    try:
        adapter.to_planning_task("not a dict")
        assert False, "Should have raised TypeError"
    except TypeError:
        pass
