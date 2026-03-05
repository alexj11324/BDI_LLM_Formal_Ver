"""BDIPlanner – the core BDI planning module built on DSPy."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import dspy
import yaml

from ..api_budget import get_budget_manager, get_repair_cache
from ..config import Config
from ..schemas import ActionNode, BDIPlan, DependencyEdge
from ..verifier import PlanVerifier
from .dspy_config import configure_dspy
from .signatures import (
    GeneratePlan,
    GeneratePlanDepots,
    GeneratePlanLogistics,
    RepairPlan,
)

logger = logging.getLogger(__name__)


# 3. Define the Module with Assertions
class BDIPlanner(dspy.Module):
    def __init__(self, auto_repair: bool = True, domain: str = "blocksworld"):
        """
        Initialize BDI Planner

        Args:
            auto_repair: If True, automatically repair disconnected plans
            domain: Planning domain - selects domain-specific Signature
                    ("blocksworld", "logistics", or "depots")
        """
        super().__init__()

        # Configure DSPy (idempotent - only runs once per process)
        configure_dspy()

        self.domain = domain

        # Select domain-specific Signature
        if domain == "logistics":
            sig_class = GeneratePlanLogistics
        elif domain == "depots":
            sig_class = GeneratePlanDepots
        else:
            sig_class = GeneratePlan

        self.generate_plan = dspy.ChainOfThought(sig_class)
        self.repair_plan = dspy.ChainOfThought(RepairPlan)
        self.auto_repair = auto_repair
        self._last_generation_trace: dict[str, Any] = {}
        self._last_repair_trace: dict[str, Any] = {}

        # Add few-shot demonstrations for Logistics domain
        if domain == "logistics":
            self.generate_plan.demos = self._build_logistics_demos()

        # Domain-specific action constraints for dspy.Assert validation
        self._valid_action_types = {
            "blocksworld": {"pick-up", "put-down", "stack", "unstack"},
            "logistics": {"load-truck", "unload-truck", "load-airplane",
                          "unload-airplane", "drive-truck", "fly-airplane"},
            "depots": {"drive", "lift", "drop", "load", "unload"},
            "testing": set(),  # Empty set = no validation for testing
        }
        self._required_params = {
            "blocksworld": {
                "pick-up": {"block"}, "put-down": {"block"},
                "stack": {"block", "target"}, "unstack": {"block", "target"},
            },
            "logistics": {
                "load-truck": {"obj", "truck", "loc"},
                "unload-truck": {"obj", "truck", "loc"},
                "load-airplane": {"obj", "airplane", "loc"},
                "unload-airplane": {"obj", "airplane", "loc"},
                "drive-truck": {"truck", "from", "to", "city"},
                "fly-airplane": {"airplane", "from", "to"},
            },
            "depots": {
                "drive": {"truck", "from", "to"},
                "lift": {"hoist", "crate", "surface", "place"},
                "drop": {"hoist", "crate", "surface", "place"},
                "load": {"hoist", "crate", "truck", "place"},
                "unload": {"hoist", "crate", "truck", "place"},
            },
            "testing": {},  # No required params for testing
        }

    @staticmethod
    def _build_logistics_demos():
        """Build few-shot demonstrations for the Logistics domain.

        Loads demonstrations from 'src/bdi_llm/data/logistics_demos.yaml'.
        """
        # Resolve the path to the data file relative to this module
        data_path = Path(__file__).parent.parent / "data" / "logistics_demos.yaml"

        if not data_path.exists():
            print(f"Warning: logistics_demos.yaml not found at {data_path}")
            return []

        with open(data_path) as f:
            data = yaml.safe_load(f)

        demos = []
        for demo_data in data.get("demos", []):
            # Reconstruct nodes and edges from dicts
            nodes_data = demo_data["plan"]["nodes"]
            edges_data = demo_data["plan"]["edges"]

            nodes = [ActionNode(**n) for n in nodes_data]
            edges = [DependencyEdge(**e) for e in edges_data]

            plan = BDIPlan(
                goal_description=demo_data["plan"]["goal_description"],
                nodes=nodes,
                edges=edges
            )

            demos.append(
                dspy.Example(
                    beliefs=demo_data["beliefs"],
                    desire=demo_data["desire"],
                    plan=plan,
                ).with_inputs("beliefs", "desire")
            )

        return demos

    def _validate_action_constraints(self, plan_obj) -> tuple:
        """Validate action_type and params against domain constraints.

        Returns:
            (all_valid, error_message) — error_message is empty when valid.
        """
        valid_types = self._valid_action_types.get(self.domain, set())
        required_params = self._required_params.get(self.domain, {})

        if not valid_types:
            return True, ""

        invalid_actions = []
        missing_params = []

        for node in plan_obj.nodes:
            # Skip virtual nodes injected by auto-repair
            if node.action_type == "Virtual":
                continue

            at = node.action_type.lower()

            if at not in valid_types:
                invalid_actions.append(
                    f"Node '{node.id}' has invalid action_type '{node.action_type}'. "
                    f"Must be one of: {sorted(valid_types)}"
                )

            elif at in required_params:
                present = set(node.params.keys()) if node.params else set()
                missing = required_params[at] - present
                if missing:
                    missing_params.append(
                        f"Node '{node.id}' ({node.action_type}) missing params: "
                        f"{sorted(missing)}. Required: {sorted(required_params[at])}"
                    )

        errors = invalid_actions + missing_params
        if errors:
            return False, "; ".join(errors)
        return True, ""

    @staticmethod
    def _truncate_trace_text(text: str | None, max_chars: int) -> str | None:
        if text is None:
            return None
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        extra = len(text) - max_chars
        return f"{text[:max_chars]}\n...[truncated {extra} chars]"

    def _capture_prediction_trace(self, pred: dspy.Prediction, phase: str) -> dict[str, Any]:
        """Capture CoT/trace artifacts from DSPy prediction + LM adapter state."""
        max_chars = max(0, int(getattr(Config, "REASONING_TRACE_MAX_CHARS", 8000)))
        trace: dict[str, Any] = {
            "phase": phase,
            "model": Config.MODEL_NAME,
            "prediction_fields": [],
        }

        try:
            pred_dict = pred.toDict() if hasattr(pred, "toDict") else {}
            if isinstance(pred_dict, dict):
                trace["prediction_fields"] = sorted(pred_dict.keys())
                text_fields = {}
                for key, value in pred_dict.items():
                    if key == "plan":
                        continue
                    if isinstance(value, str) and value.strip():
                        text_fields[key] = self._truncate_trace_text(value, max_chars)

                if text_fields:
                    trace["prediction_text_fields"] = text_fields
                    preferred_fields = (
                        "reasoning",
                        "rationale",
                        "analysis",
                        "chain_of_thought",
                        "thought_process",
                        "explanation",
                    )
                    for key in preferred_fields:
                        if key in text_fields:
                            trace["chain_of_thought_text"] = text_fields[key]
                            trace["chain_of_thought_source"] = f"prediction.{key}"
                            break

                    if "chain_of_thought_text" not in trace:
                        longest_key = max(text_fields.keys(), key=lambda k: len(text_fields[k]))
                        trace["chain_of_thought_text"] = text_fields[longest_key]
                        trace["chain_of_thought_source"] = f"prediction.{longest_key}"
        except Exception as e:
            trace["prediction_trace_error"] = str(e)

        lm = getattr(dspy.settings, "lm", None)
        if lm is not None:
            lm_reasoning = getattr(lm, "_last_reasoning_content", None)
            lm_output = getattr(lm, "_last_output_text", None)
            if isinstance(lm_reasoning, str) and lm_reasoning.strip():
                trace["lm_reasoning_content"] = self._truncate_trace_text(lm_reasoning, max_chars)
            if isinstance(lm_output, str) and lm_output.strip():
                trace["lm_output_text"] = self._truncate_trace_text(lm_output, max_chars)

        return trace

    def get_last_generation_trace(self) -> dict[str, Any]:
        if not self._last_generation_trace:
            return {}
        return json.loads(json.dumps(self._last_generation_trace))

    def get_last_repair_trace(self) -> dict[str, Any]:
        if not self._last_repair_trace:
            return {}
        return json.loads(json.dumps(self._last_repair_trace))

    def record_generation_trace(self, pred: dspy.Prediction) -> None:
        """Record generation trace when caller invokes `generate_plan` directly."""
        self._last_generation_trace = self._capture_prediction_trace(pred, phase="generation")

    def forward(self, beliefs: str, desire: str) -> dspy.Prediction:
        # Generate the plan
        pred = self.generate_plan(beliefs=beliefs, desire=desire)
        self.record_generation_trace(pred)

        try:
            plan_obj = pred.plan

            # --- Validate action_type validity & param completeness ---
            constraints_ok, constraint_msg = self._validate_action_constraints(plan_obj)
            if not constraints_ok:
                raise ValueError(
                    f"Action constraint violation: {constraint_msg}. "
                    "Re-generate the plan using ONLY valid action types "
                    f"for the {self.domain} domain "
                    f"and include ALL required parameters for each action."
                )

            # Convert to NetworkX for verification
            G = plan_obj.to_networkx()

            # Verify the plan
            is_valid, errors = PlanVerifier.verify(G)

            # Try auto-repair if enabled and plan is invalid
            if not is_valid and self.auto_repair:
                from ..plan_repair import repair_and_verify
                repaired_plan, repaired_valid, messages = repair_and_verify(plan_obj)

                if repaired_valid:
                    # Update prediction with repaired plan
                    pred.plan = repaired_plan
                    is_valid = True
                    errors = []
                else:
                    # Auto-repair didn't fully fix, but include repair messages
                    errors.extend([f"Auto-repair attempted: {msg}" for msg in messages])
                    # CRITICAL: Still return the (possibly repaired) plan instead of raising.
                    # Let the caller's verification/repair layer handle it.
                    pred.plan = repaired_plan if repaired_plan else plan_obj

            # If still invalid, DO NOT raise - return the plan for external repair
            # The benchmark script has its own auto-repair that should handle this.
            # Only raise for truly unrecoverable errors (parsing failures, etc.)
            if not is_valid:
                # Return the invalid plan - let external repair handle it
                pred.plan = plan_obj
        except Exception as e:
            # Handle potential pydantic validation errors or parsing issues
            raise ValueError(
                f"Failed to generate a valid plan object. Error: {str(e)}"
            ) from e

        return pred

    def _format_repair_history(
        self,
        repair_history: list[dict] | None = None,
    ) -> str:
        """Format cumulative repair history for the dedicated repair_history field.

        Returns an empty string for the first attempt, or a structured history
        showing all previous failed attempts with their plans and errors.
        """
        if not repair_history:
            return ""

        parts = []
        parts.append("=== CUMULATIVE REPAIR HISTORY ===")
        parts.append(f"Total previous attempts: {len(repair_history)}")
        parts.append("")

        for entry in repair_history:
            attempt_num = entry["attempt"]
            actions = entry.get("plan_actions", [])
            errors = entry.get("val_errors", [])
            parts.append(f"--- Attempt {attempt_num} (FAILED) ---")
            parts.append(f"Plan ({len(actions)} actions):")
            for a in actions[:15]:
                parts.append(f"  {a}")
            if len(actions) > 15:
                parts.append(f"  ... ({len(actions) - 15} more actions)")
            parts.append("VAL Errors:")
            for e in errors[:5]:
                parts.append(f"  - {e}")
            parts.append("")

        parts.append("=== END HISTORY ===")
        parts.append(
            f"You have failed {len(repair_history)} time(s). "
            "DO NOT repeat any of the plans above. "
            "Analyze the error patterns and try a fundamentally different approach."
        )
        return "\n".join(parts)

    def _format_verification_feedback(
        self,
        verification_feedback: dict | None = None,
    ) -> str:
        """Format structured verifier diagnostics for the repair prompt."""
        if not verification_feedback:
            return ""

        parts = ["=== VERIFIER FEEDBACK (MULTI-LAYER) ==="]
        summary = verification_feedback.get("error_summary")
        if summary:
            parts.append(f"Summary: {summary}")

        failed_layers = verification_feedback.get("failed_layers", [])
        if failed_layers:
            parts.append(f"Failed Layers: {', '.join(failed_layers)}")

        layer_status = verification_feedback.get("layer_status", {})
        if layer_status:
            parts.append("Layer Status:")
            for layer in ("structural", "symbolic", "physics"):
                status = layer_status.get(layer)
                if status is not None:
                    parts.append(f"  - {layer}: {status}")

        key_errors = verification_feedback.get("key_errors", {})
        if key_errors:
            parts.append("Key Errors by Layer:")
            for layer in ("structural", "symbolic", "physics"):
                errors = key_errors.get(layer, [])
                if errors:
                    parts.append(f"  - {layer}:")
                    for err in errors[:3]:
                        parts.append(f"      * {err}")

        val_advice = verification_feedback.get("val_repair_advice", [])
        if val_advice:
            parts.append("VAL Repair Advice:")
            for advice in val_advice[:3]:
                parts.append(f"  - {advice}")

        repair_focus = verification_feedback.get("repair_focus", [])
        if repair_focus:
            parts.append("Repair Focus Priority:")
            for focus in repair_focus:
                parts.append(f"  - {focus}")

        parts.append("=== END VERIFIER FEEDBACK ===")
        return "\n".join(parts)

    def _compute_error_signature(self, val_errors: list[str]) -> str:
        """
        Compute a compact signature of VAL errors for pattern detection.

        Groups similar errors and creates a hash for early exit detection.
        """
        # Extract error types (first line of each error, normalized)
        error_types = []
        for err in val_errors[:5]:  # Limit to first 5 errors
            # Normalize: remove specific object names, keep error type
            normalized = err.lower().split(':')[0][:50]  # First 50 chars of error type
            error_types.append(normalized)

        # Create signature
        signature = "|".join(sorted(error_types))
        return hashlib.sha256(signature.encode()).hexdigest()[:8]

    def repair_from_val_errors(
        self,
        beliefs: str,
        desire: str,
        previous_plan_actions: list[str],
        val_errors: list[str],
        repair_history: list[dict] | None = None,
        verification_feedback: dict | None = None,
        instance_id: str | None = None,
        domain: str | None = None,
    ) -> dspy.Prediction:
        """
        Generate a repaired plan based on VAL validation errors.

        Args:
            beliefs: Original beliefs (natural language)
            desire: Original desire (natural language)
            previous_plan_actions: PDDL action strings that failed validation
            val_errors: Error messages from VAL validator
            repair_history: Cumulative list of all previous repair attempts,
                each dict has keys: attempt, plan_actions, val_errors
            verification_feedback: Structured multi-layer verifier diagnostics
                generated by IntegratedVerifier.build_planner_feedback(...)
            instance_id: Unique identifier for this instance (for budget tracking)
            domain: Planning domain (for cache keying)

        Returns:
            dspy.Prediction with repaired plan

        Raises:
            ValueError: If the repaired plan is structurally invalid
            RuntimeError: If budget exhausted or early exit triggered
        """
        # Get budget manager and repair cache
        budget = get_budget_manager()
        cache = get_repair_cache()

        # Compute signatures for caching and early exit
        error_signature = self._compute_error_signature(val_errors)
        plan_hash = hashlib.sha256(
            json.dumps(previous_plan_actions, sort_keys=True).encode()
        ).hexdigest()[:16]

        # EARLY EXIT CHECK: Detect repeated failure patterns
        if instance_id and budget.config.early_exit_enabled:
            if budget.track_error_pattern(instance_id, error_signature):
                raise RuntimeError(
                    "Early exit: Same error pattern detected "
                    f"{budget.config.early_exit_after_failures} times. "
                    f"Error type: {error_signature}. Repair unlikely to succeed."
                )

        # BUDGET CHECK: Verify we're within budget
        if instance_id:
            allowed, reason = budget.check_budget(instance_id)
            if not allowed:
                raise RuntimeError(f"Budget exhausted: {reason}")

        # CACHE CHECK: Try to get cached repair result
        cache_key_domain = domain or "unknown"
        cached_result = cache.get(cache_key_domain, error_signature, plan_hash)
        if cached_result is not None:
            logger.info(f"Cache hit for repair (domain={cache_key_domain}, err={error_signature})")
            return cached_result

        # RATE LIMIT CHECK: Wait if rate limited
        allowed, wait_time = budget.check_rate_limit()
        if not allowed:
            logger.info(f"Rate limited, waiting {wait_time:.1f}s before repair")
            import time as time_module
            time_module.sleep(wait_time + 0.1)

        # CHECK BACKOFF: Wait if endpoint in backoff
        in_backoff, backoff_time = budget.check_backoff(endpoint="repair")
        if in_backoff:
            logger.info(f"Backoff active, waiting {backoff_time:.1f}s")
            import time as time_module
            time_module.sleep(backoff_time + 0.1)

        # RECORD REQUEST for rate limiting
        budget.record_request("repair")

        try:
            # Build repair history string for the dedicated field
            history_str = self._format_repair_history(repair_history)
            verifier_feedback_str = self._format_verification_feedback(verification_feedback)

            pred = self.repair_plan(
                beliefs=beliefs,
                desire=desire,
                previous_plan="\n".join(previous_plan_actions),
                val_errors="\n".join(val_errors),
                repair_history=history_str,
                verification_feedback=verifier_feedback_str,
            )
            self._last_repair_trace = self._capture_prediction_trace(pred, phase="val_repair")

            # RECORD CALL against budget
            if instance_id:
                budget.record_call(instance_id)
            plan_obj = pred.plan

            # Validate action constraints on repaired plan
            constraints_ok, constraint_msg = self._validate_action_constraints(plan_obj)
            if not constraints_ok:
                raise ValueError(
                    f"Repaired plan has action constraint violations: {constraint_msg}"
                )

            G = plan_obj.to_networkx()
            is_valid, errors = PlanVerifier.verify(G)

            # Try structural auto-repair if needed
            if not is_valid and self.auto_repair:
                from ..plan_repair import repair_and_verify

                repaired_plan, repaired_valid, messages = repair_and_verify(plan_obj)
                if repaired_valid:
                    pred.plan = repaired_plan
                    is_valid = True
                    errors = []

            if not is_valid:
                raise ValueError(
                    f"Repaired plan is structurally invalid. Errors: {'; '.join(errors)}"
                )

            # CACHE SUCCESSFUL RESULT
            cache.put(cache_key_domain, error_signature, plan_hash, pred)

        except Exception as e:
            # Don't cache failures
            raise ValueError(
                f"Failed to generate repaired plan. Error: {str(e)}"
            ) from e

        return pred


# 4. Demonstration Function
def main():
    print("Initializing BDI Planner with DSPy...")

    # Define a scenario
    beliefs = """
    Location: Living Room.
    Inventory: None.
    Environment:
    - Door to Kitchen is closed.
    - Keys are on the Table in the Living Room.
    - Robot is at coordinate (0,0).
    Available Skills: [PickUp, MoveTo, OpenDoor, UnlockDoor]
    """
    desire = "Go to the Kitchen."

    planner = BDIPlanner()

    print(f"\nGoal: {desire}")
    print("Generating Plan...")

    try:
        # Run the planner
        # dspy.Suggest/Assert will automatically retry if validation fails
        response = planner(beliefs=beliefs, desire=desire)
        final_plan = response.plan

        print("\n✅ Plan Generated Successfully!")
        print(f"Goal Description: {final_plan.goal_description}")

        print("\n--- Actions (Nodes) ---")
        for node in final_plan.nodes:
            print(f"[{node.id}] {node.action_type}: {node.description}")

        print("\n--- Dependencies (Edges) ---")
        for edge in final_plan.edges:
            print(f"{edge.source} -> {edge.target}")

        # Verify final result
        G = final_plan.to_networkx()
        print(f"\nFinal Graph Valid? {PlanVerifier.verify(G)[0]}")

        if PlanVerifier.verify(G)[0]:
            print("\nExecution Order:")
            print(" -> ".join(PlanVerifier.topological_sort(G)))

    except ValueError as e:
        print(f"\n❌ Planning Failed: {e}")

if __name__ == "__main__":
    main()
