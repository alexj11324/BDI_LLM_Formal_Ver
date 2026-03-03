"""SWE-bench domain verifier for code edits with pytest sandbox validation.

This plugin implements a verifier that validates LLM-generated code-edit
IntentionDAGs by:

1. Copying a source repository snapshot into a temporary sandbox directory.
2. Applying the proposed file edits (search-and-replace operations) from
   each IntentionNode in topological order.
3. Running ``pytest`` inside the sandbox to check whether the edits pass
   the existing test suite.

Each IntentionNode is expected to have the following ``parameters``:

* ``target_file`` (str) – Relative path to the file to edit.
* ``search_string`` (str) – The exact substring to find in the target file.
* ``replace_string`` (str) – The replacement text.

The source repository snapshot is expected to be stored in
``BeliefState.environment_context['repo_snapshot']`` as a ``Dict[str, str]``
mapping **relative file paths** to their text content.

Design notes
------------
* This module imports ``subprocess`` and ``tempfile`` – both are part of the
  Python standard library and required for sandbox execution.
* ``pytest`` is invoked as an **external process** inside the sandbox, NOT
  imported into the engine process.  This keeps the "zero domain leakage"
  rule intact for the core engine.
* All temporary directories are cleaned up automatically via context managers.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from src.core.schemas import BeliefState, IntentionDAG, IntentionNode
from src.core.verification_bus import BaseDomainVerifier


# ---------------------------------------------------------------------------
# Topological Sort Helper (identical logic to planbench_verifier)
# ---------------------------------------------------------------------------

def _topological_sort(nodes: List[IntentionNode]) -> List[IntentionNode]:
    """Return nodes in topological (dependency-respecting) order.

    Uses Kahn's algorithm.  Raises ``ValueError`` if a cycle is detected.

    Parameters
    ----------
    nodes : List[IntentionNode]
        The DAG nodes with inter-node dependencies.

    Returns
    -------
    List[IntentionNode]
        Nodes ordered so that every node appears after all of its
        dependencies.

    Raises
    ------
    ValueError
        If the dependency graph contains a cycle.
    """
    node_map: Dict[str, IntentionNode] = {n.node_id: n for n in nodes}
    in_degree: Dict[str, int] = {n.node_id: 0 for n in nodes}

    for node in nodes:
        for dep_id in node.dependencies:
            if dep_id not in node_map:
                raise ValueError(
                    f"Node '{node.node_id}' depends on '{dep_id}' "
                    f"which does not exist in the DAG."
                )
            in_degree[node.node_id] += 1

    queue: deque[str] = deque(
        nid for nid, deg in in_degree.items() if deg == 0
    )
    sorted_ids: List[str] = []

    while queue:
        current_id = queue.popleft()
        sorted_ids.append(current_id)
        for node in nodes:
            if current_id in node.dependencies:
                in_degree[node.node_id] -= 1
                if in_degree[node.node_id] == 0:
                    queue.append(node.node_id)

    if len(sorted_ids) != len(nodes):
        raise ValueError(
            "Cycle detected in IntentionDAG.  Sorted "
            f"{len(sorted_ids)} of {len(nodes)} nodes."
        )

    return [node_map[nid] for nid in sorted_ids]


# ---------------------------------------------------------------------------
# Test Failure Parser
# ---------------------------------------------------------------------------

def _extract_test_failures(stderr: str, stdout: str) -> List[str]:
    """Extract individual test failure summaries from pytest output.

    Parameters
    ----------
    stderr : str
        The standard error output from pytest.
    stdout : str
        The standard output from pytest.

    Returns
    -------
    List[str]
        A list of human-readable failure descriptions.
    """
    combined = stdout + "\n" + stderr
    failures: List[str] = []

    # Match pytest's "FAILED tests/test_foo.py::test_bar - AssertionError:..."
    failed_pattern = re.compile(r"FAILED\s+(\S+)\s*-?\s*(.*)")
    for match in failed_pattern.finditer(combined):
        test_name = match.group(1).strip()
        reason = match.group(2).strip() if match.group(2) else "unknown reason"
        failures.append(f"{test_name}: {reason}")

    # Match pytest's "ERROR tests/test_foo.py - ..."
    error_pattern = re.compile(r"ERROR\s+(\S+)\s*-?\s*(.*)")
    for match in error_pattern.finditer(combined):
        test_name = match.group(1).strip()
        reason = match.group(2).strip() if match.group(2) else "unknown error"
        failures.append(f"{test_name}: {reason}")

    # Fallback: if no structured failures found, capture the short summary
    if not failures:
        summary_pattern = re.compile(r"=+\s*(.*(?:failed|error).*)\s*=+", re.IGNORECASE)
        for match in summary_pattern.finditer(combined):
            failures.append(match.group(1).strip())

    return failures


# ---------------------------------------------------------------------------
# SWE-bench Verifier
# ---------------------------------------------------------------------------

class SWEVerifier(BaseDomainVerifier):
    """Sandbox-based verifier for SWE-bench code-edit IntentionDAGs.

    This verifier creates a temporary copy of the source repository, applies
    the proposed file edits from the IntentionDAG, runs ``pytest`` to validate
    the changes, and reports structured error traces on failure.

    The repository snapshot is expected in
    ``current_belief.environment_context['repo_snapshot']`` as a
    ``Dict[str, str]`` mapping relative file paths to file contents.

    Parameters
    ----------
    pytest_timeout : int, optional
        Maximum seconds to wait for ``pytest`` to complete.  Defaults to 60.
    pytest_args : List[str] | None, optional
        Additional arguments to pass to ``pytest`` beyond the default
        ``["tests/"]``.  For example ``["-x", "--tb=short"]``.
    python_executable : str | None, optional
        Path to the Python interpreter in the sandbox.  When ``None``,
        the verifier uses the Python from the current virtual environment
        or falls back to ``"python3"``.
    """

    def __init__(
        self,
        *,
        pytest_timeout: int = 60,
        pytest_args: Optional[List[str]] = None,
        python_executable: Optional[str] = None,
    ) -> None:
        self.pytest_timeout: int = pytest_timeout
        self.pytest_args: List[str] = pytest_args or []
        self.python_executable: str = python_executable or _resolve_python()

    def verify_transition(
        self,
        current_belief: BeliefState,
        intention_dag: IntentionDAG,
    ) -> Tuple[bool, str, str]:
        """Validate a code-edit DAG by running pytest in a temporary sandbox.

        Parameters
        ----------
        current_belief : BeliefState
            A deep copy of the agent's belief state.  Must contain
            ``environment_context['repo_snapshot']`` as a ``Dict[str, str]``.
        intention_dag : IntentionDAG
            The candidate plan whose nodes encode file edits.

        Returns
        -------
        Tuple[bool, str, str]
            ``(is_valid, formal_error_trace, dspy_correction_hint)``.
        """
        # ── 1. Validate repo snapshot ──
        repo_snapshot: Any = current_belief.environment_context.get(
            "repo_snapshot"
        )
        if not isinstance(repo_snapshot, dict):
            return (
                False,
                "StateFormatError: 'repo_snapshot' must be a Dict[str, str] "
                "mapping relative file paths to their text content.",
                "Ensure environment_context['repo_snapshot'] is a dictionary "
                "like {'src/main.py': 'print(\"hello\")', 'tests/test_main.py': '...'}.",
            )

        # ── 2. Topologically sort DAG nodes ──
        try:
            sorted_nodes = _topological_sort(intention_dag.nodes)
        except ValueError as exc:
            return (
                False,
                f"TopologicalSortError: {exc}",
                "Your plan contains a dependency cycle.  Ensure that node "
                "dependencies form a valid DAG with no circular references.",
            )

        # ── 3. Create sandbox and apply edits ──
        with tempfile.TemporaryDirectory(prefix="swe_sandbox_") as sandbox_dir:
            # Materialise the repo snapshot into the sandbox.
            _materialise_repo(repo_snapshot, sandbox_dir)

            # Apply each node's edit in topological order.
            for node in sorted_nodes:
                result = self._apply_edit(node, sandbox_dir)
                if result is not None:
                    return result  # Early return on edit failure.

            # ── 4. Run pytest in the sandbox ──
            return self._run_pytest(sandbox_dir, sorted_nodes)

    # ------------------------------------------------------------------
    # Edit Application
    # ------------------------------------------------------------------

    def _apply_edit(
        self,
        node: IntentionNode,
        sandbox_dir: str,
    ) -> Optional[Tuple[bool, str, str]]:
        """Apply a single file-edit IntentionNode to the sandbox.

        Returns ``None`` on success, or a failure 3-tuple on error.

        Parameters
        ----------
        node : IntentionNode
            An IntentionNode whose ``action_type`` is expected to be
            ``"file_edit"`` (or similar) and whose ``parameters`` contain
            ``target_file``, ``search_string``, and ``replace_string``.
        sandbox_dir : str
            Absolute path to the temporary sandbox directory.
        """
        params = node.parameters

        # Validate required parameters.
        required = ["target_file", "search_string", "replace_string"]
        missing = [p for p in required if p not in params]
        if missing:
            return (
                False,
                f"MissingParameterError: Node '{node.node_id}' is missing "
                f"required parameters: {missing}.",
                f"Each file-edit node must have 'target_file', "
                f"'search_string', and 'replace_string' in its parameters.  "
                f"You are missing: {missing}.",
            )

        target_file: str = params["target_file"]
        search_string: str = params["search_string"]
        replace_string: str = params["replace_string"]

        # Resolve absolute path inside the sandbox (prevent path traversal).
        abs_path = os.path.normpath(os.path.join(sandbox_dir, target_file))
        if not abs_path.startswith(os.path.normpath(sandbox_dir)):
            return (
                False,
                f"PathTraversalError: Node '{node.node_id}' target_file "
                f"'{target_file}' escapes the sandbox directory.",
                f"The target_file '{target_file}' resolves outside the "
                f"sandbox.  Use a relative path within the repository.",
            )

        # Check the file exists.
        if not os.path.isfile(abs_path):
            return (
                False,
                f"FileNotFoundError: Node '{node.node_id}' target_file "
                f"'{target_file}' does not exist in the repository snapshot.",
                f"File '{target_file}' was not found in the repository.  "
                f"Check the file path and ensure it exists in the snapshot.",
            )

        # Read, search-and-replace, write.
        try:
            content = _read_text(abs_path)
        except Exception as exc:
            return (
                False,
                f"FileReadError: Could not read '{target_file}' at node "
                f"'{node.node_id}': {exc}",
                f"Failed to read '{target_file}'.  Ensure the file is a "
                f"valid text file.",
            )

        if search_string not in content:
            return (
                False,
                f"SearchStringNotFound: Node '{node.node_id}' search_string "
                f"not found in '{target_file}'.  "
                f"Search string (first 100 chars): {search_string[:100]!r}",
                f"The search_string you provided was not found in "
                f"'{target_file}'.  Verify the exact content of the file and "
                f"adjust your search_string to match.",
            )

        # Apply the edit (replace first occurrence only).
        new_content = content.replace(search_string, replace_string, 1)

        try:
            _write_text(abs_path, new_content)
        except Exception as exc:
            return (
                False,
                f"FileWriteError: Could not write '{target_file}' at node "
                f"'{node.node_id}': {exc}",
                f"Failed to write to '{target_file}'.  Check file permissions.",
            )

        return None  # Success.

    # ------------------------------------------------------------------
    # Pytest Execution
    # ------------------------------------------------------------------

    def _run_pytest(
        self,
        sandbox_dir: str,
        applied_nodes: List[IntentionNode],
    ) -> Tuple[bool, str, str]:
        """Execute ``pytest`` inside the sandbox and interpret results.

        Parameters
        ----------
        sandbox_dir : str
            Absolute path to the sandbox directory.
        applied_nodes : List[IntentionNode]
            The nodes that were applied (for context in error hints).

        Returns
        -------
        Tuple[bool, str, str]
            ``(is_valid, formal_error_trace, dspy_correction_hint)``.
        """
        # Build the pytest command.
        cmd: List[str] = [
            self.python_executable, "-m", "pytest", "tests/",
            "--tb=short", "-q",
        ] + self.pytest_args

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=sandbox_dir,
                timeout=self.pytest_timeout,
            )
        except subprocess.TimeoutExpired:
            return (
                False,
                f"PytestTimeoutError: pytest exceeded the {self.pytest_timeout}s "
                f"timeout in the sandbox.",
                "The test suite took too long to execute.  Consider simplifying "
                "your edits or ensure the tests do not enter infinite loops.",
            )
        except FileNotFoundError:
            return (
                False,
                f"PytestNotFoundError: Could not find Python executable "
                f"'{self.python_executable}' to run pytest.",
                "The Python interpreter or pytest is not available in the "
                "sandbox.  Check the python_executable configuration.",
            )
        except Exception as exc:
            return (
                False,
                f"PytestExecutionError: subprocess.run failed: {exc}",
                "An unexpected error occurred while running pytest.  "
                "Check the sandbox configuration.",
            )

        # ── Interpret results ──
        if result.returncode == 0:
            # All tests passed.
            return (True, "", "")

        # Tests failed – build structured error output.
        stderr_output = result.stderr.strip()
        stdout_output = result.stdout.strip()

        # Extract individual test failures.
        failures = _extract_test_failures(stderr_output, stdout_output)

        # Build the formal error trace.
        formal_trace_parts: List[str] = [
            f"PytestFailure: {len(failures)} test(s) failed "
            f"(exit code {result.returncode})."
        ]
        if stderr_output:
            # Truncate stderr to keep the trace manageable.
            truncated_stderr = stderr_output[:2000]
            formal_trace_parts.append(f"stderr:\n{truncated_stderr}")
        if stdout_output:
            truncated_stdout = stdout_output[:2000]
            formal_trace_parts.append(f"stdout:\n{truncated_stdout}")

        formal_error_trace = "\n\n".join(formal_trace_parts)

        # Build the correction hint.
        edited_files = sorted(set(
            n.parameters.get("target_file", "?") for n in applied_nodes
        ))

        hint_parts: List[str] = [
            "Your proposed code edits caused test failures.",
            f"Files edited: {edited_files}.",
        ]
        if failures:
            hint_parts.append("Specific failures:")
            for i, failure in enumerate(failures[:10], 1):  # Cap at 10.
                hint_parts.append(f"  {i}. {failure}")
        hint_parts.append(
            "Review the error messages above and adjust your edits "
            "to fix the failing tests."
        )

        dspy_correction_hint = "\n".join(hint_parts)

        return (False, formal_error_trace, dspy_correction_hint)


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def _resolve_python() -> str:
    """Resolve the path to a Python 3 interpreter.

    Prefers the interpreter from the current virtual environment (``sys``
    module), falling back to ``"python3"`` on the system PATH.

    Returns
    -------
    str
        Absolute or relative path to a Python interpreter.
    """
    import sys

    return sys.executable or "python3"


def _materialise_repo(
    repo_snapshot: Dict[str, str],
    sandbox_dir: str,
) -> None:
    """Write a repository snapshot into a directory on disk.

    Creates all necessary parent directories for each file.

    Parameters
    ----------
    repo_snapshot : Dict[str, str]
        Mapping of relative file paths to their text content.
    sandbox_dir : str
        Absolute path to the target directory.
    """
    for rel_path, content in repo_snapshot.items():
        abs_path = os.path.normpath(os.path.join(sandbox_dir, rel_path))
        # Safety check: prevent path traversal.
        if not abs_path.startswith(os.path.normpath(sandbox_dir)):
            continue
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        _write_text(abs_path, content)


def _read_text(path: str) -> str:
    """Read a text file and return its contents.

    Parameters
    ----------
    path : str
        Absolute path to the file.

    Returns
    -------
    str
        The file content as a string.
    """
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text(path: str, content: str) -> None:
    """Write text content to a file, creating parent directories if needed.

    Parameters
    ----------
    path : str
        Absolute path to the file.
    content : str
        The text content to write.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
