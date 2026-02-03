"""
Unit Tests for PlanVerifier - The "Compiler" for BDI Plans.
These tests ensure our verification logic is sound BEFORE testing with LLMs.
"""
import pytest
import sys
sys.path.append('..')

from schemas import ActionNode, DependencyEdge, BDIPlan
from verifier import PlanVerifier


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

    def test_disconnected_graph_invalid(self):
        """Two isolated subgraphs should fail."""
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
        is_valid, errors = PlanVerifier.verify(G)

        assert is_valid is False
        assert any("disconnect" in e.lower() for e in errors)


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


class TestComplexDAG:
    """Test more realistic planning scenarios."""

    def test_parallel_branches_valid(self):
        """
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
