"""SWE-bench evaluation runner with baseline / BDI / BDI-repair modes.

Mirrors ``travelplanner/runner.py``:
- ``evaluate_sample()`` — runs one instance through the full BDI loop
- ``run_batch()`` — parallel batch execution with checkpoint/resume
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .adapter import SWEBenchTaskAdapter
from .engine import SWEBenchGenerator
from .feedback import build_test_feedback

logger = logging.getLogger(__name__)


def _restore_test_files(instance_dir: Path, base_commit: str) -> None:
    """Restore all test files to base_commit state before re-applying test_patch."""
    all_changed = _changed_files(instance_dir)
    test_files = [
        f for f in all_changed
        if "/tests/" in f or Path(f).name.startswith("test_")
    ]
    for rel_path in test_files:
        try:
            subprocess.run(
                ["git", "checkout", base_commit, "--", rel_path],
                cwd=instance_dir,
                capture_output=True,
                check=True,
                timeout=30,
            )
        except Exception:
            pass


def _apply_test_patch(instance_dir: Path, test_patch: str) -> bool:
    """Apply the SWE-bench test_patch that adds/modifies failing test cases.

    Without this patch, FAIL_TO_PASS test IDs may not exist, causing
    'no tests ran' errors.
    """
    if not test_patch or not test_patch.strip():
        return True
    proc = subprocess.run(
        ["git", "apply", "-"],
        input=test_patch,
        cwd=instance_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        logger.warning(
            f"test_patch apply failed (rc={proc.returncode}): {proc.stderr[:200]}"
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _reset_to_base_commit(instance_dir: Path, base_commit: str) -> None:
    """Reset the working tree to a clean state at base_commit."""
    subprocess.run(
        ["git", "reset", "--hard", base_commit],
        cwd=instance_dir,
        capture_output=True,
        check=True,
        timeout=60,
    )
    subprocess.run(
        ["git", "clean", "-fd", "-e", ".swebench_env"],
        cwd=instance_dir,
        capture_output=True,
        check=True,
        timeout=60,
    )


def _git_show_file(instance_dir: Path, ref: str, rel_path: str) -> str:
    """Read a file's content at a given git ref (e.g. HEAD, base_commit)."""
    proc = subprocess.run(
        ["git", "show", f"{ref}:{rel_path}"],
        cwd=instance_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        return ""  # file didn't exist at that ref (newly created)
    return proc.stdout or ""


def _changed_files(instance_dir: Path, source_only: bool = False) -> List[str]:
    """Get list of files modified relative to HEAD.

    Args:
        source_only: If True, filter to .py source files only, excluding
                     test files (which are managed by test_patch, not the LLM).
    """
    proc = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=instance_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    files = [l.strip() for l in (proc.stdout or "").splitlines() if l.strip()]
    if source_only:
        files = [
            f for f in files
            if f.endswith(".py")
            and "/tests/" not in f
            and not Path(f).name.startswith("test_")
        ]
    return files


def _restore_non_source_files(instance_dir: Path, base_commit: str) -> List[str]:
    """Restore any non-.py files that were accidentally modified."""
    all_changed = _changed_files(instance_dir)
    non_source = [f for f in all_changed if not f.endswith(".py")]
    for rel_path in non_source:
        try:
            subprocess.run(
                ["git", "checkout", base_commit, "--", rel_path],
                cwd=instance_dir,
                capture_output=True,
                check=True,
                timeout=30,
            )
        except Exception:
            pass
    return non_source


def _repo_snapshot(instance_dir: Path, max_depth: int = 3) -> str:
    """Create a tree-style directory listing (depth-limited) for planner beliefs.

    Instead of a flat ``git ls-files`` dump that wastes tokens on thousands of
    irrelevant paths, this produces a compact indented tree capped at *max_depth*
    levels.  The planner can still identify which directories contain source vs
    test code.
    """
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=instance_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        files = [
            line.strip()
            for line in (proc.stdout or "").splitlines()
            if line.strip()
        ]
        if not files:
            return ""

        # Build a nested dict representing the directory tree
        tree: dict = {}
        for f in files:
            parts = f.split("/")
            node = tree
            for part in parts:
                node = node.setdefault(part, {})

        # Render tree with depth limit
        lines_out: list[str] = []

        def _render(subtree: dict, indent: int, depth: int) -> None:
            if depth > max_depth:
                if subtree:
                    lines_out.append("  " * indent + "...")
                return
            for name in sorted(subtree):
                children = subtree[name]
                if children:  # directory
                    child_count = sum(
                        1 for _ in _iter_leaves(children)
                    )
                    lines_out.append(
                        "  " * indent + f"{name}/  ({child_count} files)"
                    )
                    _render(children, indent + 1, depth + 1)
                else:  # file leaf
                    lines_out.append("  " * indent + name)

        def _iter_leaves(subtree: dict):
            for v in subtree.values():
                if v:
                    yield from _iter_leaves(v)
                else:
                    yield 1

        _render(tree, 0, 1)
        return "\n".join(lines_out)
    except Exception:
        pass
    return ""


def _extract_mentioned_files(problem_statement: str) -> list[str]:
    """Extract .py file paths mentioned in the problem statement."""
    # Match patterns like `astropy/io/fits/card.py`, `some/module.py`
    pattern = r'[\w./]+\.py'
    candidates = re.findall(pattern, problem_statement)
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        # Normalise: strip leading ./
        c = c.lstrip("./ ")
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _mentioned_file_skeletons(
    instance_dir: Path,
    problem_statement: str,
    max_files: int = 5,
    max_total_chars: int = 3000,
) -> str:
    """Generate AST skeletons for Python files mentioned in the issue.

    Returns a block of text like::

        --- astropy/io/fits/card.py ---
        class Card:
            ...
    """
    from .ast_viewport import file_skeleton

    mentioned = _extract_mentioned_files(problem_statement)
    parts: list[str] = []
    total_chars = 0

    for rel_path in mentioned[:max_files]:
        abs_path = instance_dir / rel_path
        if not abs_path.exists():
            continue
        try:
            source = abs_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        skeleton = file_skeleton(source)
        if not skeleton.strip():
            continue
        block = f"--- {rel_path} ---\n{skeleton}"
        if total_chars + len(block) > max_total_chars:
            break
        parts.append(block)
        total_chars += len(block)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------


def evaluate_sample(
    instance: Dict[str, Any],
    *,
    mode: str,
    harness: Any,
    max_repair_attempts: int = 3,
    test_timeout: int = 600,
    max_plan_steps: int = 40,
    setup_timeout: int = 900,
    keep_workspace: bool = True,
) -> Dict[str, Any]:
    """Run one SWE-bench instance through the full BDI evaluation loop.

    Args:
        instance: SWE-bench dataset item.
        mode: One of ``"baseline"``, ``"bdi"``, ``"bdi-repair"``.
        harness: ``LocalSWEBenchHarness`` instance.
        max_repair_attempts: Max repair iterations (default 3).
        test_timeout: Timeout per test run in seconds.
        max_plan_steps: Maximum plan nodes to execute.
        setup_timeout: Timeout for repo clone/setup.
        keep_workspace: Whether to keep workspace after execution.

    Returns:
        Result dict with status, pass metrics, repair stats.
    """
    instance_id = instance.get("instance_id", "unknown")
    start = time.time()

    result: Dict[str, Any] = {
        "instance_id": instance_id,
        "repo": instance.get("repo"),
        "mode": mode,
        "status": "error",
        "tests_passed": False,
        "one_shot": False,
        "repair_attempts": 0,
        "repair_success": False,
        "changed_files": [],
        "plan_steps_total": 0,
        "durations_sec": {},
        "error": None,
    }

    # ------------------------------------------------------------------
    # Step 0: Setup repo + env
    # ------------------------------------------------------------------
    repo_dir: Optional[Path] = None
    try:
        setup_start = time.time()
        repo_dir = harness.setup_repo(instance, cleanup_existing=True, clone_timeout=setup_timeout)
        result["durations_sec"]["setup"] = round(time.time() - setup_start, 3)
    except Exception as exc:
        result["status"] = "setup_error"
        result["error"] = str(exc)
        result["durations_sec"]["total"] = round(time.time() - start, 3)
        return result

    env_start = time.time()
    env_info = harness._prepare_python_environment(
        instance=instance,
        instance_dir=repo_dir,
        timeout=setup_timeout,
    )
    result["durations_sec"]["env_setup"] = round(time.time() - env_start, 3)

    if not env_info.get("ok"):
        result["status"] = "setup_error"
        result["error"] = str(env_info.get("error", "python_environment_setup_failed"))
        result["durations_sec"]["total"] = round(time.time() - start, 3)
        return result

    python_executable = str(env_info.get("python_executable") or "python3")

    # ------------------------------------------------------------------
    # Step 0b: Apply test_patch (adds failing test cases from SWE-bench)
    # ------------------------------------------------------------------
    test_patch = instance.get("test_patch", "")
    if test_patch:
        if not _apply_test_patch(repo_dir, test_patch):
            result["status"] = "setup_error"
            result["error"] = "Failed to apply test_patch"
            logger.error(f"[{instance_id}] test_patch apply failed")
            return result

    # ------------------------------------------------------------------
    # Step 0c: Extract FAIL_TO_PASS test source code for TDD-style editing
    # ------------------------------------------------------------------
    from .ast_viewport import extract_test_function

    fail_to_pass_raw = instance.get("FAIL_TO_PASS", [])
    if isinstance(fail_to_pass_raw, str):
        try:
            fail_to_pass_raw = json.loads(fail_to_pass_raw)
        except (json.JSONDecodeError, ValueError):
            fail_to_pass_raw = []
    test_sources: List[str] = []
    for test_id in (fail_to_pass_raw or [])[:5]:
        test_file = str(test_id).split("::")[0]
        test_path = repo_dir / test_file
        if test_path.exists():
            try:
                source = test_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            func_name = str(test_id).split("::")[-1]
            func_source = extract_test_function(source, func_name)
            if func_source:
                test_sources.append(f"# {test_id}\n{func_source}")
    failing_test_code = "\n\n".join(test_sources)

    # ------------------------------------------------------------------
    # Step 1: Build PlanningTask
    # ------------------------------------------------------------------
    snapshot = _repo_snapshot(repo_dir)
    problem_stmt = instance.get("problem_statement", "") or ""
    mentioned_skeletons = _mentioned_file_skeletons(repo_dir, problem_stmt)
    adapter = SWEBenchTaskAdapter(
        repo_snapshot=snapshot,
        mentioned_skeletons=mentioned_skeletons,
    )
    task = adapter.to_planning_task(instance)

    # ------------------------------------------------------------------
    # Step 2: Generate Plan
    # ------------------------------------------------------------------
    engine = SWEBenchGenerator()
    plan_start = time.time()

    try:
        if mode == "baseline":
            gen_result = engine.generate_baseline(
                task.beliefs, task.desire, task.domain_context or ""
            )
        else:
            gen_result = engine.generate_bdi(
                task.beliefs, task.desire, task.domain_context or ""
            )
    except Exception as exc:
        result["status"] = "planning_error"
        result["error"] = str(exc)
        result["durations_sec"]["planning"] = round(time.time() - plan_start, 3)
        result["durations_sec"]["total"] = round(time.time() - start, 3)
        return result

    result["durations_sec"]["planning"] = round(time.time() - plan_start, 3)
    plan = gen_result.plan
    planning_reasoning = gen_result.reasoning or ""
    result["plan_steps_total"] = len(plan.nodes)
    result["structural_valid"] = gen_result.structural_valid
    result["structural_errors"] = gen_result.structural_errors

    # ------------------------------------------------------------------
    # Step 3: Execute + Test (Domain Layer)
    # ------------------------------------------------------------------
    issue_desc = (
        (instance.get("problem_statement", "") or "")
        + (f"\n\nHints:\n{instance.get('hints_text', '')}" if instance.get("hints_text") else "")
    )
    test_command = harness.build_test_command(instance, python_executable=python_executable)
    auto_installed: List[str] = []

    exec_start = time.time()
    execution = harness.execute_plan(
        plan=plan,
        instance=instance,
        instance_dir=repo_dir,
        issue_desc=issue_desc,
        default_test_command=test_command,
        python_executable=python_executable,
        test_timeout=test_timeout,
        max_steps=max_plan_steps,
        auto_installed_packages=auto_installed,
        planning_reasoning=planning_reasoning,
        failing_test_code=failing_test_code,
    )
    result["durations_sec"]["execution"] = round(time.time() - exec_start, 3)
    result["plan_steps_executed"] = execution["executed_steps"]

    # Restore any non-source files that the plan may have corrupted
    base_commit = instance.get("base_commit", "HEAD")
    restored = _restore_non_source_files(repo_dir, base_commit)
    if restored:
        result["restored_files"] = restored

    # Final test
    test_ok, test_output, returncode, _ = harness.run_tests_with_dependency_fix(
        instance_dir=repo_dir,
        command=test_command,
        auto_installed_packages=auto_installed,
        python_executable=python_executable,
        timeout=test_timeout,
    )
    result["one_shot"] = test_ok
    result["tests_passed"] = test_ok
    result["final_test_output_tail"] = (test_output or "")[-4000:]

    # ------------------------------------------------------------------
    # Step 4: Patch-level Repair Loop (BDI-repair mode only)
    #
    # Instead of regenerating the *plan* (which is usually correct),
    # we repair the *code changes* directly — feeding test errors back
    # to improve each changed file. This mirrors TravelPlanner's
    # review.py → repair_patch() pattern.
    # ------------------------------------------------------------------
    if mode == "bdi-repair" and not test_ok:
        seen_signatures: set[str] = set()
        repair_history_parts: List[str] = []

        for attempt in range(1, max_repair_attempts + 1):
            # Build feedback from test failures
            test_fb = build_test_feedback(test_output, returncode)

            # Early exit: repeated error signature
            err_sig = engine._compute_error_signature(test_fb)
            if err_sig in seen_signatures:
                logger.info(
                    f"[{instance_id}] Patch repair {attempt}: "
                    f"repeated error signature, stopping"
                )
                break
            seen_signatures.add(err_sig)

            # Only repair .py source files (skip config files)
            modified_files = _changed_files(repo_dir, source_only=True)
            if not modified_files:
                logger.info(f"[{instance_id}] No source files changed, nothing to repair")
                break

            repair_history = "\n".join(repair_history_parts)
            repair_start = time.time()
            any_file_changed = False

            for rel_path in modified_files:
                original = _git_show_file(repo_dir, base_commit, rel_path)
                current = (repo_dir / rel_path).read_text(
                    encoding="utf-8", errors="ignore"
                )

                # Compute unified diff for the repair model
                diff_lines = difflib.unified_diff(
                    original.splitlines(keepends=True),
                    current.splitlines(keepends=True),
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                    n=3,
                )
                diff_text = "".join(diff_lines)

                try:
                    patch_result = engine.repair_patch(
                        file_path=rel_path,
                        original_content=original,
                        current_content=current,
                        issue_description=issue_desc,
                        test_feedback=test_fb,
                        repair_history=repair_history,
                        diff_text=diff_text,
                    )
                except Exception as exc:
                    logger.warning(
                        f"[{instance_id}] Patch repair failed for {rel_path}: {exc}"
                    )
                    continue

                if patch_result.changed:
                    (repo_dir / rel_path).write_text(
                        patch_result.new_content, encoding="utf-8"
                    )
                    any_file_changed = True

            result["durations_sec"][f"patch_repair_{attempt}"] = round(
                time.time() - repair_start, 3
            )
            result["repair_attempts"] = attempt

            if not any_file_changed:
                logger.info(
                    f"[{instance_id}] Patch repair {attempt}: "
                    f"LLM returned identical content, stopping"
                )
                break

            # Record history for next iteration
            repair_history_parts.append(
                f"=== Patch Repair {attempt} ===\n"
                f"Files repaired: {modified_files}\n"
                f"Test errors:\n{test_fb}\n"
            )

            # Re-test with the patched files (no repo reset, no re-execution)
            auto_installed_repair: List[str] = []
            test_ok, test_output, returncode, _ = harness.run_tests_with_dependency_fix(
                instance_dir=repo_dir,
                command=test_command,
                auto_installed_packages=auto_installed_repair,
                python_executable=python_executable,
                timeout=test_timeout,
            )

            result["final_test_output_tail"] = (test_output or "")[-4000:]

            if test_ok:
                result["repair_success"] = True
                result["tests_passed"] = True
                logger.info(
                    f"[{instance_id}] Patch repair succeeded on attempt {attempt}"
                )
                break

    # ------------------------------------------------------------------
    # Step 5: Collect final results
    # ------------------------------------------------------------------
    if result["tests_passed"]:
        result["status"] = "passed"
    else:
        result["status"] = "failed_tests"

    try:
        diff_proc = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        result["changed_files"] = [
            l.strip() for l in (diff_proc.stdout or "").splitlines() if l.strip()
        ]
    except Exception:
        pass

    result["durations_sec"]["total"] = round(time.time() - start, 3)

    if not keep_workspace and repo_dir and repo_dir.exists():
        import shutil
        shutil.rmtree(repo_dir, ignore_errors=True)

    return result
