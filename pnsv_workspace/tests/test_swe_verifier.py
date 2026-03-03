"""Unit tests for the SWE-bench verifier plugin.

Covers:
- Missing repo_snapshot in BeliefState
- Missing required parameters (target_file, search_string, replace_string)
- Search string not found in target file
- Path traversal protection
- File not found in snapshot
- Valid edits with passing and failing pytest
- Dependency cycle detection
- Empty DAG is trivially valid
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest

from src.core.schemas import BeliefState, IntentionDAG, IntentionNode
from src.plugins.swe_verifier import SWEVerifier


@pytest.fixture
def verifier() -> SWEVerifier:
    """Create a fresh SWEVerifier with a short timeout."""
    return SWEVerifier(pytest_timeout=30)


def _make_belief(
    repo_snapshot: Any = None,
) -> BeliefState:
    """Helper: create a BeliefState with an optional repo_snapshot."""
    ctx: Dict[str, Any] = {}
    if repo_snapshot is not None:
        ctx["repo_snapshot"] = repo_snapshot
    return BeliefState(environment_context=ctx)


def _make_dag(
    nodes: List[IntentionNode],
    dag_id: str = "swe-test-dag",
) -> IntentionDAG:
    """Helper: create an IntentionDAG from a list of nodes."""
    return IntentionDAG(dag_id=dag_id, nodes=nodes)


# ---------------------------------------------------------------------------
# Missing / Invalid Repo Snapshot
# ---------------------------------------------------------------------------

class TestRepoSnapshotValidation:
    """Tests for repo_snapshot format validation."""

    def test_missing_repo_snapshot(self, verifier: SWEVerifier) -> None:
        """BeliefState without 'repo_snapshot' should fail."""
        belief = BeliefState()  # no repo_snapshot
        dag = _make_dag([])
        is_valid, trace, hint = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "StateFormatError" in trace or "repo_snapshot" in trace

    def test_non_dict_repo_snapshot(self, verifier: SWEVerifier) -> None:
        """repo_snapshot that is not a dict should fail."""
        belief = _make_belief(repo_snapshot="not-a-dict")
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "target_file": "main.py",
                    "search_string": "old",
                    "replace_string": "new",
                },
            ),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "repo_snapshot" in trace


# ---------------------------------------------------------------------------
# Parameter Validation
# ---------------------------------------------------------------------------

class TestParameterValidation:
    """Tests for required parameter checking on edit nodes."""

    def test_missing_target_file(self, verifier: SWEVerifier) -> None:
        """Node missing 'target_file' should produce MissingParameterError."""
        belief = _make_belief(repo_snapshot={"src/main.py": "print('hi')"})
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "search_string": "hi",
                    "replace_string": "hello",
                },
            ),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "MissingParameterError" in trace
        assert "target_file" in trace

    def test_missing_search_string(self, verifier: SWEVerifier) -> None:
        """Node missing 'search_string' should produce MissingParameterError."""
        belief = _make_belief(repo_snapshot={"src/main.py": "print('hi')"})
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "target_file": "src/main.py",
                    "replace_string": "hello",
                },
            ),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "MissingParameterError" in trace
        assert "search_string" in trace

    def test_missing_all_params(self, verifier: SWEVerifier) -> None:
        """Node with no parameters should list all missing."""
        belief = _make_belief(repo_snapshot={"src/main.py": "code"})
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="file_edit", parameters={}),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "MissingParameterError" in trace


# ---------------------------------------------------------------------------
# Edit Application
# ---------------------------------------------------------------------------

class TestEditApplication:
    """Tests for file-edit application logic."""

    def test_search_string_not_found(self, verifier: SWEVerifier) -> None:
        """Edit with a search_string not present in the file should fail."""
        belief = _make_belief(repo_snapshot={
            "main.py": "def foo():\n    return 42\n",
        })
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "target_file": "main.py",
                    "search_string": "NOT_IN_FILE",
                    "replace_string": "replacement",
                },
            ),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "SearchStringNotFound" in trace

    def test_file_not_in_snapshot(self, verifier: SWEVerifier) -> None:
        """Edit targeting a file not in the snapshot should fail."""
        belief = _make_belief(repo_snapshot={
            "other.py": "x = 1",
        })
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "target_file": "nonexistent.py",
                    "search_string": "x",
                    "replace_string": "y",
                },
            ),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "FileNotFoundError" in trace

    def test_path_traversal_blocked(self, verifier: SWEVerifier) -> None:
        """target_file that escapes sandbox via ../.. should be rejected."""
        belief = _make_belief(repo_snapshot={"main.py": "safe content"})
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "target_file": "../../etc/passwd",
                    "search_string": "root",
                    "replace_string": "hacked",
                },
            ),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "PathTraversal" in trace or "FileNotFound" in trace


# ---------------------------------------------------------------------------
# Sandbox Execution (pytest)
# ---------------------------------------------------------------------------

class TestSandboxExecution:
    """Tests for sandbox pytest execution."""

    def test_valid_edit_with_passing_tests(self, verifier: SWEVerifier) -> None:
        """A correct edit that makes tests pass should be valid."""
        repo_snapshot = {
            "src/__init__.py": "",
            "src/calc.py": "def add(a, b):\n    return a - b\n",
            "tests/__init__.py": "",
            "tests/test_calc.py": (
                "from src.calc import add\n"
                "\n"
                "def test_add():\n"
                "    assert add(2, 3) == 5\n"
            ),
        }
        belief = _make_belief(repo_snapshot=repo_snapshot)
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "target_file": "src/calc.py",
                    "search_string": "return a - b",
                    "replace_string": "return a + b",
                },
            ),
        ])
        is_valid, trace, hint = verifier.verify_transition(belief, dag)
        assert is_valid is True
        assert trace == ""
        assert hint == ""

    def test_valid_edit_with_failing_tests(self, verifier: SWEVerifier) -> None:
        """An edit that doesn't fix the bug should fail verification."""
        repo_snapshot = {
            "src/__init__.py": "",
            "src/calc.py": "def add(a, b):\n    return a - b\n",
            "tests/__init__.py": "",
            "tests/test_calc.py": (
                "from src.calc import add\n"
                "\n"
                "def test_add():\n"
                "    assert add(2, 3) == 5\n"
            ),
        }
        belief = _make_belief(repo_snapshot=repo_snapshot)
        # Edit that doesn't actually fix the bug
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "target_file": "src/calc.py",
                    "search_string": "return a - b",
                    "replace_string": "return a * b",  # Wrong fix!
                },
            ),
        ])
        is_valid, trace, hint = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "PytestFailure" in trace
        assert "test failures" in hint.lower() or "edits" in hint.lower()

    def test_empty_dag_is_valid(self, verifier: SWEVerifier) -> None:
        """An empty DAG (no edits) should pass if tests already pass."""
        repo_snapshot = {
            "src/__init__.py": "",
            "src/calc.py": "def add(a, b):\n    return a + b\n",
            "tests/__init__.py": "",
            "tests/test_calc.py": (
                "from src.calc import add\n"
                "\n"
                "def test_add():\n"
                "    assert add(2, 3) == 5\n"
            ),
        }
        belief = _make_belief(repo_snapshot=repo_snapshot)
        dag = _make_dag([])
        is_valid, _, _ = verifier.verify_transition(belief, dag)
        assert is_valid is True


# ---------------------------------------------------------------------------
# Dependency Cycle
# ---------------------------------------------------------------------------

class TestDependencyCycle:
    """Test circular dependency detection."""

    def test_cycle_detected(self, verifier: SWEVerifier) -> None:
        """Circular dependencies should produce TopologicalSortError."""
        belief = _make_belief(repo_snapshot={"main.py": "code"})
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "target_file": "main.py",
                    "search_string": "c",
                    "replace_string": "d",
                },
                dependencies=["n2"],
            ),
            IntentionNode(
                node_id="n2",
                action_type="file_edit",
                parameters={
                    "target_file": "main.py",
                    "search_string": "o",
                    "replace_string": "0",
                },
                dependencies=["n1"],
            ),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "TopologicalSortError" in trace or "Cycle" in trace


# ---------------------------------------------------------------------------
# Missing Dependency
# ---------------------------------------------------------------------------

class TestMissingDependency:
    """Test that dependencies on non-existent nodes are detected."""

    def test_missing_dependency_node(self, verifier: SWEVerifier) -> None:
        """A node depending on a non-existent node_id should fail verification."""
        belief = _make_belief(repo_snapshot={"main.py": "code"})
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="file_edit",
                parameters={
                    "target_file": "main.py",
                    "search_string": "c",
                    "replace_string": "d",
                },
                dependencies=["ghost_node"],
            ),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "ghost_node" in trace
        assert "does not exist" in trace or "TopologicalSortError" in trace
