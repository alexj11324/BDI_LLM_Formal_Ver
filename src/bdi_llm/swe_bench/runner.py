"""SWE-bench evaluation runner with baseline / BDI / BDI-repair modes.

Mirrors ``travelplanner/runner.py``:
- ``evaluate_sample()`` — runs one instance through the full BDI loop
- ``run_batch()`` — parallel batch execution with checkpoint/resume
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from .adapter import SWEBenchTaskAdapter
from .engine import SWEBenchGenerator
from .feedback import (
    build_test_feedback,
    build_verification_context,
    format_verification_feedback,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _reset_to_base_commit(instance_dir: Path, base_commit: str) -> None:
    """Hard-reset the repo back to base commit for re-execution during repair.

    Args:
        instance_dir: Path to the repository directory.
        base_commit: Base commit SHA to reset to.

    Raises:
        subprocess.SubprocessError: If git operations fail.
        subprocess.TimeoutExpired: If git operations timeout.
    """
    try:
        subprocess.run(
            ["git", "checkout", "--", "."],
            cwd=instance_dir,
            capture_output=True,
            check=True,
            timeout=60,
        )
    except subprocess.SubprocessError as exc:
        logger.warning(f"Git checkout failed in {instance_dir}: {exc}")
        raise

    try:
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=instance_dir,
            capture_output=True,
            check=True,
            timeout=60,
        )
    except subprocess.SubprocessError as exc:
        logger.warning(f"Git clean failed in {instance_dir}: {exc}")
        raise


def _repo_snapshot(instance_dir: Path, max_files: int = 250) -> str:
    """Create compact repository file listing for planner beliefs.

    Args:
        instance_dir: Path to the repository directory.
        max_files: Maximum number of files to include in snapshot.

    Returns:
        A formatted string with repository file paths, truncated if needed.
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
        if files:
            shown = files[:max_files]
            suffix = (
                f"\n... ({len(files) - max_files} files omitted)"
                if len(files) > max_files
                else ""
            )
            return "\n".join(shown) + suffix
    except (subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        logger.debug(f"Failed to generate repo snapshot: {exc}")
    return ""


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------


def evaluate_sample(
    instance: dict[str, Any],
    *,
    mode: str,
    harness: Any,
    max_repair_attempts: int = 3,
    test_timeout: int = 600,
    max_plan_steps: int = 40,
    setup_timeout: int = 900,
    keep_workspace: bool = True,
) -> dict[str, Any]:
    """Run one SWE-bench instance through the full BDI evaluation loop.

    Args:
        instance: SWE-bench dataset item (dict with instance_id, repo, etc.).
        mode: One of ``"baseline"``, ``"bdi"``, ``"bdi-repair"``.
        harness: ``LocalSWEBenchHarness`` instance with methods:
            - setup_repo(instance, cleanup_existing, clone_timeout)
            - _prepare_python_environment(instance, instance_dir, timeout)
            - build_test_command(instance, python_executable)
            - execute_plan(plan, instance, instance_dir, ...)
            - run_tests_with_dependency_fix(instance_dir, command, ...)
        max_repair_attempts: Max repair iterations (default 3).
        test_timeout: Timeout per test run in seconds.
        max_plan_steps: Maximum plan nodes to execute.
        setup_timeout: Timeout for repo clone/setup.
        keep_workspace: Whether to keep workspace after execution.

    Returns:
        Result dict with keys:
            - instance_id: str
            - repo: str
            - mode: str
            - status: str (passed, failed_tests, setup_error, planning_error, etc.)
            - tests_passed: bool
            - one_shot: bool (passed on first attempt without repair)
            - repair_attempts: int
            - repair_success: bool
            - changed_files: list[str]
            - plan_steps_total: int
            - plan_steps_executed: int
            - structural_valid: bool
            - structural_errors: list[str]
            - durations_sec: dict[str, float]
            - error: str | None
            - error_category: str | None
    """
    instance_id = instance.get("instance_id", "unknown")
    start = time.time()

    result: dict[str, Any] = {
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
        "error_category": None,
    }

    # ------------------------------------------------------------------
    # Step 0: Setup repo + env
    # ------------------------------------------------------------------
    repo_dir: Path | None = None
    try:
        setup_start = time.time()
        repo_dir = harness.setup_repo(instance, cleanup_existing=True, clone_timeout=setup_timeout)
        result["durations_sec"]["setup"] = round(time.time() - setup_start, 3)
    except Exception as exc:
        result["status"] = "setup_error"
        result["error"] = str(exc)
        result["error_category"] = "setup_error"
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
        result["error"] = f"python_environment_setup_failed: {env_info.get('error', 'unknown')}"
        result["error_category"] = "env_setup_error"
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
        result["error_category"] = "planning_error"
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
    auto_installed: list[str] = []

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
    # Step 4: Repair Loop (BDI-repair mode only)
    # ------------------------------------------------------------------
    if mode == "bdi-repair" and not test_ok:
        cumulative_history: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        current_plan = plan

        for attempt in range(1, max_repair_attempts + 1):
            # Build feedback
            test_fb = build_test_feedback(test_output, returncode)

            # Early exit: repeated error signature
            err_sig = engine._compute_error_signature(test_fb)
            if err_sig in seen_signatures:
                logger.info(
                    f"[{instance_id}] Repair attempt {attempt}: "
                    f"repeated error signature {err_sig}, stopping"
                )
                break
            seen_signatures.add(err_sig)

            cumulative_history.append({
                "attempt": attempt,
                "plan_summary": engine._summarise_plan(current_plan),
                "test_errors": test_fb,
            })

            verification_ctx = build_verification_context(
                structural_result={
                    "valid": gen_result.structural_valid,
                    "errors": gen_result.structural_errors,
                },
                test_result={
                    "valid": test_ok,
                    "errors": test_fb,
                    "returncode": returncode,
                },
            )
            verification_fb = format_verification_feedback(verification_ctx)

            # Generate repair
            repair_start = time.time()
            try:
                repair_result = engine.repair(
                    beliefs=task.beliefs,
                    desire=task.desire,
                    domain_context=task.domain_context or "",
                    test_feedback=test_fb,
                    previous_plan=current_plan,
                    cumulative_history=cumulative_history,
                    verification_feedback=verification_fb,
                )
            except Exception as exc:
                logger.warning(
                    f"[{instance_id}] Repair attempt {attempt} failed: {exc}"
                )
                result["repair_attempts"] = attempt
                break

            result["durations_sec"][f"repair_{attempt}"] = round(
                time.time() - repair_start, 3
            )

            repaired_plan = repair_result.plan
            current_plan = repaired_plan
            result["repair_attempts"] = attempt

            # Reset, re-execute, re-test
            try:
                base_commit = instance.get("base_commit", "")
                _reset_to_base_commit(repo_dir, base_commit)
            except Exception as exc:
                logger.warning(f"[{instance_id}] git reset failed: {exc}")
                break

            auto_installed_repair: list[str] = []
            harness.execute_plan(
                plan=repaired_plan,
                instance=instance,
                instance_dir=repo_dir,
                issue_desc=issue_desc,
                default_test_command=test_command,
                python_executable=python_executable,
                test_timeout=test_timeout,
                max_steps=max_plan_steps,
                auto_installed_packages=auto_installed_repair,
            )

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
                    f"[{instance_id}] Repair succeeded on attempt {attempt}"
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
