"""SWE-bench evaluation runner with baseline / BDI / BDI-repair modes.

Mirrors ``travelplanner/runner.py``:
- ``evaluate_sample()`` — runs one instance through the full BDI loop
- ``run_batch()`` — parallel batch execution with checkpoint/resume
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..verifier import PlanVerifier
from .adapter import SWEBenchTaskAdapter
from .engine import SWEBenchGenerator
from .feedback import build_test_feedback

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _reset_to_base_commit(instance_dir: Path, base_commit: str) -> None:
    """Hard-reset the repo back to base commit for re-execution during repair."""
    subprocess.run(
        ["git", "checkout", "--", "."],
        cwd=instance_dir,
        capture_output=True,
        check=True,
        timeout=60,
    )
    subprocess.run(
        ["git", "clean", "-fd"],
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


def _changed_files(instance_dir: Path) -> List[str]:
    """Get list of files modified relative to HEAD."""
    proc = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=instance_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return [l.strip() for l in (proc.stdout or "").splitlines() if l.strip()]


def _repo_snapshot(instance_dir: Path, max_files: int = 250) -> str:
    """Create compact repository file listing for planner beliefs."""
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
        if files:
            shown = files[:max_files]
            suffix = (
                f"\n... ({len(files) - max_files} files omitted)"
                if len(files) > max_files
                else ""
            )
            return "\n".join(shown) + suffix
    except Exception:
        pass
    return ""


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
    # Step 1: Build PlanningTask
    # ------------------------------------------------------------------
    snapshot = _repo_snapshot(repo_dir)
    adapter = SWEBenchTaskAdapter(repo_snapshot=snapshot)
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
    )
    result["durations_sec"]["execution"] = round(time.time() - exec_start, 3)
    result["plan_steps_executed"] = execution["executed_steps"]

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
        base_commit = instance.get("base_commit", "HEAD")

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

            # Find which files were changed by the plan execution
            modified_files = _changed_files(repo_dir)
            if not modified_files:
                logger.info(f"[{instance_id}] No files changed, nothing to repair")
                break

            repair_history = "\n".join(repair_history_parts)
            repair_start = time.time()
            any_file_changed = False

            for rel_path in modified_files:
                original = _git_show_file(repo_dir, base_commit, rel_path)
                current = (repo_dir / rel_path).read_text(
                    encoding="utf-8", errors="ignore"
                )

                try:
                    patch_result = engine.repair_patch(
                        file_path=rel_path,
                        original_content=original,
                        current_content=current,
                        issue_description=issue_desc,
                        test_feedback=test_fb,
                        repair_history=repair_history,
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
