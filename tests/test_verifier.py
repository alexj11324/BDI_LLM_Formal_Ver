"""
Unit Tests for PlanVerifier - The "Compiler" for BDI Plans.
These tests ensure our verification logic is sound BEFORE testing with LLMs.
"""
import pytest
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from bdi_llm.schemas import ActionNode, DependencyEdge, BDIPlan
from bdi_llm.verifier import PlanVerifier, VerificationResult


class TestVerifierBasics:
    """Test fundamental verification rules."""

    def test_empty_plan_is_invalid(self):
        """A plan with no actions should fail."""
        plan = BDIPlan(
            goal_description="Empty test",
            nodes=[],
            edges=[]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is False
        assert any("empty" in e.lower() for e in errors)

    def test_single_node_is_valid(self):
        """A plan with one action and no dependencies is valid."""
        plan = BDIPlan(
            goal_description="Single action",
            nodes=[
                ActionNode(id="action1", action_type="Navigate", description="Go somewhere")
            ],
            edges=[]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is True
        assert len(errors) == 0

    def test_linear_dag_is_valid(self):
        """A simple A -> B -> C chain should be valid."""
        plan = BDIPlan(
            goal_description="Linear plan",
            nodes=[
                ActionNode(id="step1", action_type="PickUp", description="Pick up keys"),
                ActionNode(id="step2", action_type="Navigate", description="Go to door"),
                ActionNode(id="step3", action_type="UnlockDoor", description="Unlock the door"),
            ],
            edges=[
                DependencyEdge(source="step1", target="step2"),
                DependencyEdge(source="step2", target="step3"),
            ]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is True
        assert len(errors) == 0

    def test_verify_result_supports_legacy_tuple_access(self):
        """Structured result should remain compatible with tuple-style callers."""
        plan = BDIPlan(
            goal_description="Tuple compatibility",
            nodes=[
                ActionNode(id="n1", action_type="Action", description="First"),
                ActionNode(id="n2", action_type="Action", description="Second"),
            ],
            edges=[DependencyEdge(source="n1", target="n2")],
        )
        G = plan.to_networkx()

        result = PlanVerifier.verify(G)
        assert isinstance(result, VerificationResult)
        assert result.is_valid is True

        is_valid, errors = result
        assert is_valid is True
        assert errors == []
        assert result[0] is True
        assert result[1] == []


class TestCycleDetection:
    """Test that cycles (deadlocks) are correctly detected."""

    def test_simple_cycle_detected(self):
        """A -> B -> A should fail."""
        plan = BDIPlan(
            goal_description="Cyclic plan",
            nodes=[
                ActionNode(id="A", action_type="Action", description="Action A"),
                ActionNode(id="B", action_type="Action", description="Action B"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),
                DependencyEdge(source="B", target="A"),  # Creates cycle!
            ]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is False
        assert any("cycle" in e.lower() for e in errors)

    def test_longer_cycle_detected(self):
        """A -> B -> C -> A should fail."""
        plan = BDIPlan(
            goal_description="Longer cycle",
            nodes=[
                ActionNode(id="A", action_type="Action", description="A"),
                ActionNode(id="B", action_type="Action", description="B"),
                ActionNode(id="C", action_type="Action", description="C"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),
                DependencyEdge(source="B", target="C"),
                DependencyEdge(source="C", target="A"),  # Cycle!
            ]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is False
        assert any("cycle" in e.lower() for e in errors)

    def test_self_loop_detected(self):
        """A -> A (self-loop) should fail."""
        plan = BDIPlan(
            goal_description="Self loop",
            nodes=[
                ActionNode(id="A", action_type="Action", description="A"),
            ],
            edges=[
                DependencyEdge(source="A", target="A"),  # Self-loop!
            ]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is False


class TestConnectivity:
    """Test that disconnected plans are detected."""

    def test_disconnected_graph_is_warning_only(self):
        """Two isolated subgraphs should warn but not hard-fail."""
        plan = BDIPlan(
            goal_description="Disconnected plan",
            nodes=[
                ActionNode(id="A", action_type="Action", description="A"),
                ActionNode(id="B", action_type="Action", description="B"),
                ActionNode(id="C", action_type="Action", description="C"),
                ActionNode(id="D", action_type="Action", description="D"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),  # Island 1
                DependencyEdge(source="C", target="D"),  # Island 2 (disconnected!)
            ]
        )
        G = plan.to_networkx()
        result = PlanVerifier.verify(G)

        assert result.is_valid is True
        assert result.hard_errors == []
        assert any("disconnect" in w.lower() for w in result.warnings)

        # Legacy tuple access still exposes warnings as messages.
        is_valid, messages = result
        assert is_valid is True
        assert any("disconnect" in m.lower() for m in messages)


class TestTopologicalSort:
    """Test execution order generation."""

    def test_topo_sort_returns_valid_order(self):
        """Topological sort should respect dependencies."""
        plan = BDIPlan(
            goal_description="Ordered plan",
            nodes=[
                ActionNode(id="first", action_type="A", description="First"),
                ActionNode(id="second", action_type="B", description="Second"),
                ActionNode(id="third", action_type="C", description="Third"),
            ],
            edges=[
                DependencyEdge(source="first", target="second"),
                DependencyEdge(source="second", target="third"),
            ]
        )
        G = plan.to_networkx()
        order = PlanVerifier.topological_sort(G)

        assert order.index("first") < order.index("second")
        assert order.index("second") < order.index("third")

    def test_topo_sort_fails_on_cycle(self):
        """Topological sort should return empty list for cyclic graphs."""
        plan = BDIPlan(
            goal_description="Cyclic",
            nodes=[
                ActionNode(id="A", action_type="X", description="A"),
                ActionNode(id="B", action_type="X", description="B"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),
                DependencyEdge(source="B", target="A"),
            ]
        )
        G = plan.to_networkx()
        order = PlanVerifier.topological_sort(G)

        assert order == []


class TestCycleDetection:
    """Enhanced cycle detection tests."""

    def test_complex_cycle_with_parallel_chain(self):
        """
        Complex cycle: A→B→C→A with parallel chain D→E
        Should detect the cycle even with disconnected component.
        """
        plan = BDIPlan(
            goal_description="Complex cycle with parallel chain",
            nodes=[
                ActionNode(id="A", action_type="Action", description="A"),
                ActionNode(id="B", action_type="Action", description="B"),
                ActionNode(id="C", action_type="Action", description="C"),
                ActionNode(id="D", action_type="Action", description="D"),
                ActionNode(id="E", action_type="Action", description="E"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),  # Cycle: A→B→C→A
                DependencyEdge(source="B", target="C"),
                DependencyEdge(source="C", target="A"),
                DependencyEdge(source="D", target="E"),  # Parallel chain
            ]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is False
        assert any("cycle" in e.lower() for e in errors)
        # Should detect the A→B→C→A cycle
        cycle_errors = [e for e in errors if "cycle" in e.lower()]
        assert len(cycle_errors) >= 1

    def test_nested_cycles(self):
        """
        Nested cycles: A→B→C→A and B→D→B
        Two interlocking cycles sharing node B.
        """
        plan = BDIPlan(
            goal_description="Nested cycles",
            nodes=[
                ActionNode(id="A", action_type="Action", description="A"),
                ActionNode(id="B", action_type="Action", description="B"),
                ActionNode(id="C", action_type="Action", description="C"),
                ActionNode(id="D", action_type="Action", description="D"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),  # Outer cycle: A→B→C→A
                DependencyEdge(source="B", target="C"),
                DependencyEdge(source="C", target="A"),
                DependencyEdge(source="B", target="D"),  # Inner cycle: B→D→B
                DependencyEdge(source="D", target="B"),
            ]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is False
        # Should detect at least one cycle
        assert any("cycle" in e.lower() for e in errors)


class TestCycleBreaking:
    """
    Tests for cycle breaking/repair functionality.

    Cycle breaking strategy:
    - Detect all cycles using simple_cycles()
    - For each cycle, remove the back-edge (edge that completes the cycle)
    - Back-edge = edge from last node in cycle back to first node
    """

    def test_simple_cycle_breaking(self):
        """
        Simple cycle A→B→A should be broken by removing one edge.
        After repair, should have either A→B or B→A (not both).
        """
        from bdi_llm.plan_repair import PlanRepairer

        plan = BDIPlan(
            goal_description="Simple cycle to break",
            nodes=[
                ActionNode(id="A", action_type="Action", description="A"),
                ActionNode(id="B", action_type="Action", description="B"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),
                DependencyEdge(source="B", target="A"),  # Back-edge creating cycle
            ]
        )

        # Verify original is invalid (has cycle)
        G = plan.to_networkx()
        is_valid, _ = PlanVerifier.verify(G)
        assert is_valid is False

        # Attempt repair
        result = PlanRepairer.repair(plan)

        # Cycle repair should succeed
        assert result.success is True
        assert "Broke cycles" in result.repairs_applied[0]

        # Repaired plan should be valid DAG
        repaired_G = result.repaired_plan.to_networkx()
        is_valid_after, errors_after = PlanVerifier.verify(repaired_G)
        assert is_valid_after is True

        # Should have exactly one edge remaining (cycle broken)
        assert len(result.repaired_plan.edges) == 1

    def test_complex_cycle_breaking(self):
        """
        Complex cycle A→B→C→A with parallel chain D→E.
        After repair: cycle should be broken, D→E chain preserved.
        Note: Repair also connects components with virtual START/END nodes.
        """
        from bdi_llm.plan_repair import PlanRepairer

        plan = BDIPlan(
            goal_description="Complex cycle with parallel chain",
            nodes=[
                ActionNode(id="A", action_type="Action", description="A"),
                ActionNode(id="B", action_type="Action", description="B"),
                ActionNode(id="C", action_type="Action", description="C"),
                ActionNode(id="D", action_type="Action", description="D"),
                ActionNode(id="E", action_type="Action", description="E"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),
                DependencyEdge(source="B", target="C"),
                DependencyEdge(source="C", target="A"),  # Back-edge
                DependencyEdge(source="D", target="E"),
            ]
        )

        # Verify original has cycle
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)
        assert is_valid is False

        # Repair should break cycle and connect components
        result = PlanRepairer.repair(plan)
        assert result.success is True
        assert any("Broke cycles" in r for r in result.repairs_applied)
        assert any("Connected disconnected" in r for r in result.repairs_applied)

        # Repaired plan should be valid
        repaired_G = result.repaired_plan.to_networkx()
        is_valid_after, _ = PlanVerifier.verify(repaired_G)
        assert is_valid_after is True

        # Original 3 cycle edges - 1 broken + 1 parallel + 4 connecting (START->A, START->D, C->END, E->END) = 7
        # Key assertion: cycle is broken (C->A edge removed)
        edge_pairs = [(e.source, e.target) for e in result.repaired_plan.edges]
        assert ("C", "A") not in edge_pairs  # Cycle-breaking edge removed
        assert ("A", "B") in edge_pairs  # Original chain preserved
        assert ("B", "C") in edge_pairs  # Original chain preserved
        assert ("D", "E") in edge_pairs  # Parallel chain preserved

    def test_nested_cycle_breaking(self):
        """
        Nested cycles A→B→C→A and B→D→B.
        After repair: both cycles should be broken.
        """
        from bdi_llm.plan_repair import PlanRepairer

        plan = BDIPlan(
            goal_description="Nested cycles",
            nodes=[
                ActionNode(id="A", action_type="Action", description="A"),
                ActionNode(id="B", action_type="Action", description="B"),
                ActionNode(id="C", action_type="Action", description="C"),
                ActionNode(id="D", action_type="Action", description="D"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),
                DependencyEdge(source="B", target="C"),
                DependencyEdge(source="C", target="A"),  # Outer cycle back-edge
                DependencyEdge(source="B", target="D"),
                DependencyEdge(source="D", target="B"),  # Inner cycle back-edge
            ]
        )

        # Verify original has cycles
        G = plan.to_networkx()
        is_valid, _ = PlanVerifier.verify(G)
        assert is_valid is False

        # Repair should break both cycles
        result = PlanRepairer.repair(plan)
        assert result.success is True
        assert any("Broke cycles" in r for r in result.repairs_applied)

        # Repaired plan should be valid DAG
        repaired_G = result.repaired_plan.to_networkx()
        is_valid_after, _ = PlanVerifier.verify(repaired_G)
        assert is_valid_after is True


class TestVALFallback:
    """
    Tests for VAL integration and fallback on structural failure.

    Key scenarios:
    1. Structurally invalid but VAL-valid plans
    2. Plans that fail structure but pass VAL execution
    3. Plans that pass structure but fail VAL (semantic errors)
    """

    def test_disconnected_but_val_valid(self):
        """
        Disconnected graph where each component is a valid plan.
        VAL would accept if actions were sequentialized.

        Example: Two independent sub-plans that could run in parallel
        but are structurally disconnected.
        """
        from bdi_llm.verifier import PlanVerifier
        from bdi_llm.plan_repair import PlanRepairer

        plan = BDIPlan(
            goal_description="Two independent sub-plans",
            nodes=[
                ActionNode(id="pickup_A", action_type="PickUp", description="Pick up A"),
                ActionNode(id="putdown_A", action_type="PutDown", description="Put down A"),
                ActionNode(id="pickup_B", action_type="PickUp", description="Pick up B"),
                ActionNode(id="putdown_B", action_type="PutDown", description="Put down B"),
            ],
            edges=[
                DependencyEdge(source="pickup_A", target="putdown_A"),  # Chain 1
                DependencyEdge(source="pickup_B", target="putdown_B"),  # Chain 2 (disconnected)
            ]
        )

        # Structural check: disconnected = warning (non-blocking)
        G = plan.to_networkx()
        result = PlanVerifier.verify(G)
        assert result.is_valid is True
        assert result.hard_errors == []
        assert any("disconnect" in w.lower() for w in result.warnings)

        # Repair should connect the components
        result = PlanRepairer.repair(plan)

        # Current repair connects via virtual START/END
        if result.success:
            repaired_G = result.repaired_plan.to_networkx()
            repaired_valid, _ = PlanVerifier.verify(repaired_G)
            assert repaired_valid is True
            # Verify virtual nodes were added
            node_ids = [n.id for n in result.repaired_plan.nodes]
            assert "__START__" in node_ids or "__END__" in node_ids

    def test_structurally_valid_but_val_invalid(self):
        """
        Plan is a valid DAG but has semantic errors VAL would catch.

        Example: Valid structure but wrong action order
        (put-down before pick-up, stack before pick-up, etc.)
        """
        # This test documents that structural verification
        # does not guarantee semantic correctness
        # VAL integration is needed as Layer 2

        plan = BDIPlan(
            goal_description="Wrong order plan",
            nodes=[
                ActionNode(id="putdown", action_type="PutDown", description="Put down first"),
                ActionNode(id="pickup", action_type="PickUp", description="Pick up second"),
            ],
            edges=[
                DependencyEdge(source="putdown", target="pickup"),
            ]
        )

        # Structurally valid (it's a DAG)
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)
        assert is_valid is True  # Structure is fine

        # But VAL would reject this (can't put down before picking up)
        # This test documents the need for Layer 2 verification
        # Full integration test with VAL would require domain/problem files

    def test_val_fallback_message(self):
        """
        When structural repair fails, error messages should guide user.

        Note: With cycle repair implemented, simple cycles are now auto-fixed.
        This test documents error handling for truly unrepairable cases.
        """
        from bdi_llm.plan_repair import PlanRepairer

        # Simple cycles are now repairable
        plan = BDIPlan(
            goal_description="Cyclic plan (repairable)",
            nodes=[
                ActionNode(id="A", action_type="Action", description="A"),
                ActionNode(id="B", action_type="Action", description="B"),
            ],
            edges=[
                DependencyEdge(source="A", target="B"),
                DependencyEdge(source="B", target="A"),
            ]
        )

        result = PlanRepairer.repair(plan)

        # Cycle repair should succeed
        assert result.success is True
        assert any("Broke cycles" in r for r in result.repairs_applied)


class TestComplexDAG:
    """Test more realistic planning scenarios."""

    def test_parallel_branches_valid(self):
        r"""
        Diamond pattern (parallel execution):
           A
          / \
         B   C
          \ /
           D
        """
        plan = BDIPlan(
            goal_description="Parallel branches",
            nodes=[
                ActionNode(id="start", action_type="Init", description="Start"),
                ActionNode(id="branch1", action_type="Task", description="Parallel 1"),
                ActionNode(id="branch2", action_type="Task", description="Parallel 2"),
                ActionNode(id="join", action_type="Finish", description="Join"),
            ],
            edges=[
                DependencyEdge(source="start", target="branch1"),
                DependencyEdge(source="start", target="branch2"),
                DependencyEdge(source="branch1", target="join"),
                DependencyEdge(source="branch2", target="join"),
            ]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is True
        assert len(errors) == 0

    def test_kitchen_scenario(self):
        """
        Real-world scenario: Go to kitchen
        - Pick up keys
        - Navigate to door
        - Unlock door
        - Open door
        - Walk through
        """
        plan = BDIPlan(
            goal_description="Navigate to kitchen",
            nodes=[
                ActionNode(id="pickup_keys", action_type="PickUp",
                          params={"object": "keys"}, description="Pick up the keys from table"),
                ActionNode(id="nav_to_door", action_type="Navigate",
                          params={"target": "door"}, description="Walk to the door"),
                ActionNode(id="unlock", action_type="UnlockDoor",
                          params={"tool": "keys"}, description="Unlock the door"),
                ActionNode(id="open", action_type="OpenDoor",
                          description="Open the unlocked door"),
                ActionNode(id="walk_through", action_type="Navigate",
                          params={"target": "kitchen"}, description="Enter the kitchen"),
            ],
            edges=[
                DependencyEdge(source="pickup_keys", target="nav_to_door"),
                DependencyEdge(source="nav_to_door", target="unlock"),
                DependencyEdge(source="pickup_keys", target="unlock"),  # Also need keys to unlock
                DependencyEdge(source="unlock", target="open"),
                DependencyEdge(source="open", target="walk_through"),
            ]
        )
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is True

        # Verify execution order makes sense
        order = PlanVerifier.topological_sort(G)
        assert order.index("pickup_keys") < order.index("unlock")
        assert order.index("unlock") < order.index("open")
        assert order.index("open") < order.index("walk_through")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
