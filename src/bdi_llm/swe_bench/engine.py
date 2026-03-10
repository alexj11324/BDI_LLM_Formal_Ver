"""SWE-bench generation engine with baseline / BDI / repair modes.

Mirrors ``travelplanner/engine.py`` — provides a single ``SWEBenchGenerator``
class with methods for each execution mode.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

import dspy

from ..planner.dspy_config import configure_dspy
from ..schemas import BDIPlan
from ..verifier import PlanVerifier
from .signatures import (
    GeneratePlanCoding,
    GeneratePlanCodingBaseline,
    RepairCodeChange,
    RepairPlanCoding,
)

logger = logging.getLogger(__name__)


@dataclass
class SWEBenchGenerationResult:
    """Result from plan generation (any mode)."""

    plan: BDIPlan
    raw: Any = None
    structural_valid: bool = False
    structural_errors: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class SWEBenchRepairResult:
    """Result from one plan-level repair attempt."""

    plan: BDIPlan
    raw: Any = None
    attempt: int = 0


@dataclass
class PatchRepairResult:
    """Result from one patch-level repair attempt."""

    file_path: str
    new_content: str
    raw: Any = None
    changed: bool = False


class SWEBenchGenerator:
    """Unified generator for SWE-bench with baseline, BDI, and repair modes.

    Follows the same pattern as ``TravelPlannerGenerator``:
    - ``generate_baseline()`` — direct Predict, no CoT
    - ``generate_bdi()``      — ChainOfThought with structural verification
    - ``repair()``            — repair from test failures
    """

    MAX_REPAIR_ATTEMPTS = 3

    def __init__(self) -> None:
        configure_dspy()
        self._baseline = dspy.Predict(GeneratePlanCodingBaseline)
        self._bdi = dspy.ChainOfThought(GeneratePlanCoding)
        self._repair = dspy.ChainOfThought(RepairPlanCoding)
        self._repair_patch = dspy.ChainOfThought(RepairCodeChange)

    # -----------------------------------------------------------------
    # Generation
    # -----------------------------------------------------------------

    def generate_baseline(
        self,
        beliefs: str,
        desire: str,
        domain_context: str = "",
    ) -> SWEBenchGenerationResult:
        """Generate plan without CoT reasoning (baseline mode)."""
        pred = self._baseline(beliefs=beliefs, desire=desire)
        plan = pred.plan
        if plan is None:
            raise ValueError("LLM returned no parseable plan (baseline)")
        root_cause = getattr(pred, "root_cause_analysis", "")
        reasoning = getattr(pred, "reasoning", "")
        combined = ""
        if root_cause:
            combined += f"Root cause: {root_cause}"
        if reasoning:
            combined += f"\nStrategy: {reasoning}" if combined else f"Strategy: {reasoning}"
        return SWEBenchGenerationResult(plan=plan, raw=pred, reasoning=combined)

    def generate_bdi(
        self,
        beliefs: str,
        desire: str,
        domain_context: str = "",
    ) -> SWEBenchGenerationResult:
        """Generate plan with BDI CoT reasoning + structural verification."""
        pred = self._bdi(beliefs=beliefs, desire=desire)
        plan = pred.plan
        if plan is None:
            raise ValueError("LLM returned no parseable plan (BDI)")

        # Structural verification (Layer 1)
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        return SWEBenchGenerationResult(
            plan=plan,
            raw=pred,
            structural_valid=is_valid,
            structural_errors=list(errors) if errors else [],
            reasoning=self._build_planning_context(pred),
        )

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _build_planning_context(pred: Any) -> str:
        """Merge root_cause_analysis and reasoning into a combined context."""
        root_cause = getattr(pred, "root_cause_analysis", "")
        reasoning = getattr(pred, "reasoning", "")
        parts: list[str] = []
        if root_cause:
            parts.append(f"Root cause: {root_cause}")
        if reasoning:
            parts.append(f"Strategy: {reasoning}")
        return "\n".join(parts)

    # -----------------------------------------------------------------
    # Repair
    # -----------------------------------------------------------------

    @staticmethod
    def _format_repair_history(
        cumulative_history: list[dict[str, Any]],
    ) -> str:
        """Format cumulative repair history for the repair prompt.

        Mirrors ``BDIPlanner._format_repair_history``.
        """
        if not cumulative_history:
            return ""

        parts: list[str] = []
        for entry in cumulative_history:
            attempt = entry.get("attempt", "?")
            test_errors = entry.get("test_errors", "")
            plan_summary = entry.get("plan_summary", "")
            parts.append(
                f"=== Attempt {attempt} ===\n"
                f"Plan summary: {plan_summary}\n"
                f"Test errors:\n{test_errors}\n"
            )
        return "\n".join(parts)

    @staticmethod
    def _summarise_plan(plan: BDIPlan) -> str:
        """Build a compact summary of a plan for repair context."""
        if plan is None:
            return "(no plan)"
        lines: list[str] = []
        for node in plan.nodes:
            params_str = ", ".join(f"{k}={v}" for k, v in (node.params or {}).items())
            lines.append(f"  {node.id}: {node.action_type}({params_str})")
        return "\n".join(lines) if lines else "(empty plan)"

    @staticmethod
    def _compute_error_signature(test_output: str) -> str:
        """Compute a compact hash of test failures for early-exit detection.

        Mirrors ``BDIPlanner._compute_error_signature``.
        """
        normalised = test_output.strip().lower()
        return hashlib.md5(normalised.encode()).hexdigest()[:12]

    def repair(
        self,
        beliefs: str,
        desire: str,
        domain_context: str,
        test_feedback: str,
        previous_plan: BDIPlan,
        cumulative_history: list[dict[str, Any]],
        verification_feedback: str = "",
    ) -> SWEBenchRepairResult:
        """Generate a repaired plan based on test failure feedback.

        Args:
            beliefs: Original beliefs (repo state, issue).
            desire: Original desire (fix issue, pass tests).
            domain_context: Action type constraints.
            test_feedback: Structured test failure output.
            previous_plan: The plan that was executed and failed.
            cumulative_history: History of all previous repair attempts.
            verification_feedback: Structured verifier diagnostics.

        Returns:
            ``SWEBenchRepairResult`` with the repaired plan.
        """
        attempt = len(cumulative_history) + 1
        history_text = self._format_repair_history(cumulative_history)
        plan_summary = self._summarise_plan(previous_plan)

        logger.info(
            f"SWE-bench repair attempt {attempt}/{self.MAX_REPAIR_ATTEMPTS}"
        )

        pred = self._repair(
            beliefs=beliefs,
            desire=desire,
            previous_plan_summary=plan_summary,
            test_feedback=test_feedback,
            repair_history=history_text,
            verification_feedback=verification_feedback,
            domain_context=domain_context,
        )

        plan = pred.plan
        if plan is None:
            raise ValueError(
                f"LLM returned no parseable plan (repair attempt {attempt})"
            )

        return SWEBenchRepairResult(plan=plan, raw=pred, attempt=attempt)

    # -----------------------------------------------------------------
    # Patch-level repair
    # -----------------------------------------------------------------

    def repair_patch(
        self,
        file_path: str,
        original_content: str,
        current_content: str,
        issue_description: str,
        test_feedback: str,
        repair_history: str = "",
        diff_text: str = "",
    ) -> PatchRepairResult:
        """Repair a single file's patch using test failure feedback.

        Instead of regenerating the *plan*, this fixes the *code change*
        directly — analogous to TravelPlanner's ``repair_patch()``.

        Args:
            file_path: Relative path of the file to repair.
            original_content: File content at base commit (before edits).
            current_content: File content after the failed edit.
            issue_description: The original bug report / issue text.
            test_feedback: Structured test failure output.
            repair_history: Summary of prior repair attempts.
            diff_text: Pre-computed unified diff of original→current.

        Returns:
            ``PatchRepairResult`` with the improved file content.
        """
        logger.info(f"Patch-level repair for {file_path}")

        # Compute unified diff if not provided by caller
        if not diff_text:
            diff_lines = difflib.unified_diff(
                original_content.splitlines(keepends=True),
                current_content.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                n=3,
            )
            diff_text = "".join(diff_lines)

        pred = self._repair_patch(
            file_path=file_path,
            original_snippet=original_content[:4000],
            previous_diff=diff_text[:4000],
            issue_description=issue_description[:4000],
            test_feedback=test_feedback[:3000],
            repair_history=repair_history[:2000],
        )

        search_block = getattr(pred, "search_block", "")
        replace_block = getattr(pred, "replace_block", "")

        if search_block and isinstance(search_block, str):
            if search_block in current_content:
                new_content = current_content.replace(search_block, replace_block, 1)
            else:
                # Fuzzy match: strip trailing whitespace per line
                search_stripped = "\n".join(
                    l.rstrip() for l in search_block.splitlines()
                )
                current_stripped = "\n".join(
                    l.rstrip() for l in current_content.splitlines()
                )
                if search_stripped in current_stripped:
                    new_content = current_stripped.replace(
                        search_stripped, replace_block, 1
                    )
                else:
                    logger.warning(
                        f"Repair search_block not found in {file_path}, "
                        f"first 80 chars: {search_block[:80]!r}"
                    )
                    new_content = current_content  # no change
        else:
            logger.warning(f"Repair returned empty search_block for {file_path}")
            new_content = current_content

        # AST syntax guardrail: reject repairs that introduce SyntaxError
        if file_path.endswith(".py") and new_content != current_content:
            try:
                ast.parse(new_content)
            except SyntaxError as e:
                logger.warning(
                    f"Repair produced SyntaxError in {file_path}: {e}"
                )
                new_content = current_content  # reject repair

        return PatchRepairResult(
            file_path=file_path,
            new_content=new_content,
            raw=pred,
            changed=(new_content != current_content),
        )
