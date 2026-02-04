import networkx as nx
from typing import Tuple, List

class PlanVerifier:
    """
    The 'Compiler' for BDI Plans.
    Checks logical consistency and structural validity of the generated graph.
    """

    @staticmethod
    def verify(graph: nx.DiGraph) -> Tuple[bool, List[str]]:
        """
        Runs a suite of checks on the plan graph.
        Returns: (is_valid, list_of_errors)
        """
        errors = []

        # Check 1: Empty Graph
        if graph.number_of_nodes() == 0:
            errors.append("Plan is empty (no actions generated).")
            return False, errors

        # Check 2: Connectivity (Weakly Connected)
        # A valid plan generally shouldn't have disconnected islands of actions.
        if not nx.is_weakly_connected(graph):
            errors.append("Plan graph is disconnected. All actions should be related to the goal.")

        # Check 3: Cycles (Deadlocks)
        # A plan must be a Directed Acyclic Graph (DAG).
        try:
            cycles = list(nx.simple_cycles(graph))
            if cycles:
                for cycle in cycles:
                    errors.append(f"Cycle detected: {' -> '.join(cycle)}")
        except Exception as e:
            errors.append(f"Error checking cycles: {str(e)}")

        # Check 4: Dangling Edges
        # (NetworkX usually handles this by adding nodes, but we check logic)
        # In this implementation, we assume the graph construction from BDIPlan handles node existence.

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def topological_sort(graph: nx.DiGraph) -> List[str]:
        """Returns a valid execution order of action IDs."""
        try:
            return list(nx.topological_sort(graph))
        except nx.NetworkXUnfeasible:
            return []
