"""Convert SWE-bench dataset instances into normalised PlanningTask objects.

Mirrors the pattern established by ``travelplanner/adapter.py``.
"""

from __future__ import annotations

import json
from typing import Any

from ..planning_task import PlanningTask, TaskAdapter


def _parse_test_field(raw: Any) -> list[str]:
    """Parse FAIL_TO_PASS / PASS_TO_PASS into a flat list of test selectors."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


class SWEBenchTaskAdapter(TaskAdapter):
    """Convert a SWE-bench dataset item into a ``PlanningTask``.

    The adapter maps:
    - ``problem_statement`` + repo metadata → ``beliefs``
    - ``FAIL_TO_PASS`` + ``PASS_TO_PASS`` → ``desire``
    - repo snapshot + hints → ``domain_context``
    """

    MAX_SNAPSHOT_FILES = 250

    def __init__(
        self,
        repo_snapshot: str | None = None,
        mentioned_skeletons: str | None = None,
    ) -> None:
        self._repo_snapshot = repo_snapshot or ""
        self._mentioned_skeletons = mentioned_skeletons or ""

    def to_planning_task(self, raw_input: Any) -> PlanningTask:
        if not isinstance(raw_input, dict):
            raise TypeError(f"Unsupported raw_input type: {type(raw_input)}")

        instance_id = raw_input.get("instance_id")
        if not instance_id:
            raise ValueError("SWE-bench sample missing instance_id")

        repo = raw_input.get("repo", "")
        base_commit = raw_input.get("base_commit", "")
        version = raw_input.get("version", "")
        problem_statement = raw_input.get("problem_statement", "")

        fail_to_pass = _parse_test_field(raw_input.get("FAIL_TO_PASS"))
        pass_to_pass = _parse_test_field(raw_input.get("PASS_TO_PASS"))

        beliefs = (
            f"Repository: {repo}\n"
            f"Base commit: {base_commit}\n"
            f"Version: {version}\n"
            f"Known failing tests: {fail_to_pass[:25]}\n"
            f"Regression tests to preserve: {pass_to_pass[:25]}\n"
        )
        if self._repo_snapshot:
            beliefs += f"\nRepository structure:\n{self._repo_snapshot}"
        if self._mentioned_skeletons:
            beliefs += (
                f"\n\nMentioned files skeleton:\n{self._mentioned_skeletons}"
            )

        desire = (
            "Fix the issue and make failing tests pass without breaking "
            "regression tests.\n\n"
            f"Issue:\n{problem_statement}"
        )
        hints = raw_input.get("hints_text", "")
        if hints:
            desire += f"\n\nHints:\n{hints}"

        domain_context = (
            "SWE-bench Verified coding benchmark.\n\n"
            "Available action types: read-file | edit-file | run-test | create-file\n\n"
            "Constraints:\n"
            "1. You MUST read-file before edit-file.\n"
            "2. You MUST run-test AFTER edit-file to verify the fix.\n"
            "3. You must NOT break passing regression tests.\n"
            "4. Minimise the number of file edits.\n"
            "5. CRITICAL: Only edit SOURCE CODE files. NEVER edit test files "
            "(files in tests/ or named test_*.py). The tests define expected "
            "behavior — fix the source code to match them."
        )

        metadata = {
            "instance_id": instance_id,
            "repo": repo,
            "base_commit": base_commit,
            "version": version,
            "FAIL_TO_PASS": fail_to_pass,
            "PASS_TO_PASS": pass_to_pass,
            "problem_statement": problem_statement,
            "hints_text": hints,
        }

        return PlanningTask(
            task_id=str(instance_id),
            domain_name="swe-bench",
            beliefs=beliefs,
            desire=desire,
            domain_context=domain_context,
            metadata=metadata,
        )
