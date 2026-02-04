"""
Integration Tests for BDI-LLM Planner.
Tests the full pipeline: LLM Generation -> Verification -> Self-Correction.

NOTE: These tests require an LLM API key to run.
Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.
"""
import pytest
import os
import sys
import json
from typing import List, Tuple

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from bdi_llm.schemas import BDIPlan
from bdi_llm.verifier import PlanVerifier

# Check if we can run LLM tests
HAS_API_KEY = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))


class TestMetrics:
    """Metrics collection for evaluation."""

    def __init__(self):
        self.total_runs = 0
        self.valid_plans = 0
        self.first_try_success = 0
        self.retry_counts: List[int] = []
        self.semantic_scores: List[float] = []

    def record(self, is_valid: bool, retries: int, semantic_score: float = None):
        self.total_runs += 1
        if is_valid:
            self.valid_plans += 1
        if retries == 0:
            self.first_try_success += 1
        self.retry_counts.append(retries)
        if semantic_score:
            self.semantic_scores.append(semantic_score)

    def report(self) -> dict:
        return {
            "structural_accuracy": self.valid_plans / self.total_runs if self.total_runs > 0 else 0,
            "first_try_rate": self.first_try_success / self.total_runs if self.total_runs > 0 else 0,
            "avg_retries": sum(self.retry_counts) / len(self.retry_counts) if self.retry_counts else 0,
            "avg_semantic_score": sum(self.semantic_scores) / len(self.semantic_scores) if self.semantic_scores else 0,
        }


# Test Scenarios - Different complexity levels
TEST_SCENARIOS = [
    {
        "name": "simple_navigation",
        "beliefs": """
        Location: Living Room.
        Environment: Door to Kitchen is open.
        Available Skills: [Navigate]
        """,
        "desire": "Go to the Kitchen.",
        "expected_min_nodes": 1,
        "expected_max_nodes": 3,
    },
    {
        "name": "locked_door",
        "beliefs": """
        Location: Living Room.
        Inventory: Keys.
        Environment:
        - Door to Kitchen is locked.
        Available Skills: [Navigate, UnlockDoor, OpenDoor]
        """,
        "desire": "Go to the Kitchen.",
        "expected_min_nodes": 3,
        "expected_max_nodes": 5,
    },
    {
        "name": "complex_preparation",
        "beliefs": """
        Location: Kitchen.
        Inventory: None.
        Environment:
        - Ingredients are in the refrigerator.
        - Pot is in the cabinet.
        - Stove is off.
        Available Skills: [Navigate, PickUp, PutDown, OpenContainer, TurnOn, TurnOff]
        """,
        "desire": "Boil water in a pot on the stove.",
        "expected_min_nodes": 4,
        "expected_max_nodes": 10,
    },
    {
        "name": "parallel_tasks",
        "beliefs": """
        Location: Office.
        Equipment: Computer (off), Printer (on), Phone.
        Available Skills: [TurnOn, TurnOff, Send, Print, Call]
        """,
        "desire": "Print a document and send an email simultaneously, then turn off the printer.",
        "expected_min_nodes": 3,
        "expected_max_nodes": 6,
    },
]


@pytest.mark.skipif(not HAS_API_KEY, reason="No API key available")
class TestLLMIntegration:
    """Tests that require actual LLM inference."""

    @pytest.fixture
    def planner(self):
        """Initialize the BDI Planner."""
        from bdi_llm.planner import BDIPlanner
        return BDIPlanner()

    @pytest.mark.parametrize("scenario", TEST_SCENARIOS, ids=[s["name"] for s in TEST_SCENARIOS])
    def test_scenario_generates_valid_plan(self, planner, scenario):
        """Test that each scenario generates a structurally valid plan."""
        try:
            response = planner(beliefs=scenario["beliefs"], desire=scenario["desire"])
            plan = response.plan

            # Structural validation
            G = plan.to_networkx()
            is_valid, errors = PlanVerifier.verify(G)

            assert is_valid, f"Plan failed validation: {errors}"
            assert len(plan.nodes) >= scenario["expected_min_nodes"], \
                f"Too few nodes: {len(plan.nodes)} < {scenario['expected_min_nodes']}"
            assert len(plan.nodes) <= scenario["expected_max_nodes"], \
                f"Too many nodes: {len(plan.nodes)} > {scenario['expected_max_nodes']}"

        except Exception as e:
            pytest.fail(f"Planning failed: {str(e)}")

    def test_assert_triggers_retry_on_invalid(self, planner, mocker):
        """
        Test that DSPy Assert mechanism triggers retry when verifier fails.
        We mock the first response to return an invalid plan.
        """
        # This test would require mocking DSPy internals
        # For now, we document the expected behavior
        pass


class TestOfflineValidation:
    """Tests that don't require LLM - validate against pre-generated plans."""

    def test_golden_plan_kitchen_scenario(self):
        """Validate a known-good plan structure."""
        golden_plan = BDIPlan(
            goal_description="Navigate from living room to kitchen",
            nodes=[
                {"id": "1", "action_type": "PickUp", "params": {"object": "keys"},
                 "description": "Pick up keys from table"},
                {"id": "2", "action_type": "Navigate", "params": {"target": "door"},
                 "description": "Walk to door"},
                {"id": "3", "action_type": "UnlockDoor", "params": {},
                 "description": "Unlock the door"},
                {"id": "4", "action_type": "OpenDoor", "params": {},
                 "description": "Open the door"},
                {"id": "5", "action_type": "Navigate", "params": {"target": "kitchen"},
                 "description": "Enter kitchen"},
            ],
            edges=[
                {"source": "1", "target": "2"},
                {"source": "1", "target": "3"},
                {"source": "2", "target": "3"},
                {"source": "3", "target": "4"},
                {"source": "4", "target": "5"},
            ]
        )

        G = golden_plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is True

        # Check execution order
        order = PlanVerifier.topological_sort(G)
        assert order[0] == "1"  # Must pick up keys first
        assert order[-1] == "5"  # Must enter kitchen last

    def test_malformed_plan_rejected(self):
        """Test that obviously wrong plans are rejected."""
        # Plan with circular dependency
        bad_plan = BDIPlan(
            goal_description="Impossible plan",
            nodes=[
                {"id": "A", "action_type": "Do", "description": "Do A"},
                {"id": "B", "action_type": "Do", "description": "Do B"},
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "A"},  # Cycle!
            ]
        )

        G = bad_plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is False
        assert len(errors) > 0


class TestSemanticValidation:
    """
    Tests for semantic correctness (not just structural).
    These would ideally use an LLM-as-judge approach.
    """

    def create_semantic_checker_prompt(self, plan: BDIPlan, goal: str) -> str:
        """Create a prompt for LLM-as-judge evaluation."""
        return f"""
        Evaluate if this plan achieves the goal. Score 1-5.

        Goal: {goal}

        Plan:
        {json.dumps([n.model_dump() for n in plan.nodes], indent=2)}

        Dependencies:
        {json.dumps([e.model_dump() for e in plan.edges], indent=2)}

        Criteria:
        1. Does the plan logically achieve the goal?
        2. Are the actions in the right order?
        3. Are there any missing steps?
        4. Is the plan efficient (no unnecessary steps)?

        Return JSON: {{"score": <1-5>, "reasoning": "<explanation>"}}
        """

    @pytest.mark.skip(reason="Requires LLM for semantic evaluation")
    def test_semantic_correctness(self):
        """Use GPT-4 as judge to evaluate plan quality."""
        # This would call an LLM to evaluate semantic correctness
        pass


def run_benchmark(output_file: str = "benchmark_results.json"):
    """
    Run full benchmark suite and save results.
    Call this function to generate evaluation metrics.
    """
    metrics = TestMetrics()
    results = []

    if not HAS_API_KEY:
        print("No API key found. Running offline tests only.")
        return

    from planner import BDIPlanner
    planner = BDIPlanner()

    for scenario in TEST_SCENARIOS:
        print(f"Testing: {scenario['name']}...")
        try:
            response = planner(beliefs=scenario["beliefs"], desire=scenario["desire"])
            plan = response.plan
            G = plan.to_networkx()
            is_valid, errors = PlanVerifier.verify(G)

            result = {
                "scenario": scenario["name"],
                "is_valid": is_valid,
                "num_nodes": len(plan.nodes),
                "num_edges": len(plan.edges),
                "errors": errors,
                "execution_order": PlanVerifier.topological_sort(G) if is_valid else [],
            }
            results.append(result)
            metrics.record(is_valid, retries=0)  # TODO: Track actual retries

        except Exception as e:
            results.append({
                "scenario": scenario["name"],
                "is_valid": False,
                "error": str(e),
            })
            metrics.record(False, retries=0)

    # Save results
    output = {
        "metrics": metrics.report(),
        "results": results,
    }

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nBenchmark Results:")
    print(f"  Structural Accuracy: {metrics.report()['structural_accuracy']:.2%}")
    print(f"  First Try Rate: {metrics.report()['first_try_rate']:.2%}")
    print(f"  Average Retries: {metrics.report()['avg_retries']:.2f}")
    print(f"\nFull results saved to {output_file}")


if __name__ == "__main__":
    # Run pytest for unit tests
    pytest.main([__file__, "-v", "-k", "not LLM"])

    # Optionally run benchmark
    # run_benchmark()
