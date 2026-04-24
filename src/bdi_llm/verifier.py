from dataclasses import dataclass, field

import networkx as nx


@dataclass
class VerificationResult:
    """
    Structured result from structural verification.

    Separates hard errors (must fix) from warnings (potential issues).
    Hard errors block further verification; warnings pass through to Layer 2 (VAL).
    """

    is_valid: bool
    hard_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def should_block_execution(self) -> bool:
        """True if hard errors exist that must be fixed before proceeding."""
        return len(self.hard_errors) > 0

    @property
    def all_messages(self) -> list[str]:
        """All errors and warnings combined."""
        return self.hard_errors + self.warnings

    @property
    def errors(self) -> list[str]:
        """
        Backward-compatible alias for legacy callers expecting a single errors list.

        Includes both hard errors and warnings.
        """
        return self.all_messages

    def as_legacy_tuple(self) -> tuple[bool, list[str]]:
        """Return legacy `(is_valid, errors)` tuple representation."""
        return self.is_valid, self.errors

    def __iter__(self):
        """Allow tuple-unpacking compatibility: `is_valid, errors = verify(...)`."""
        return iter(self.as_legacy_tuple())

    def __getitem__(self, index: int):
        """Allow tuple-style indexing compatibility: `verify(...)[0]`."""
        return self.as_legacy_tuple()[index]

    def __len__(self) -> int:
        """Behave like a 2-item tuple for compatibility checks."""
        return 2


class PlanVerifier:
    """
    The 'Compiler' for BDI Plans.
    Checks logical consistency and structural validity of the generated graph.

    Verification layers:
    - HARD errors: Empty graph, cycles (no valid execution order)
    - SOFT warnings: Disconnected components (may be parallel subplans)
    """

    @staticmethod
    def verify(graph: nx.DiGraph) -> VerificationResult:
        """
        Runs a suite of checks on the plan graph.

        Returns:
            VerificationResult with:
            - is_valid: True if no hard errors
            - hard_errors: Blocking issues that must be fixed
            - warnings: Non-blocking issues for diagnostics

        Hard errors (block Layer 2):
        - Empty graph: No plan to verify
        - Cycles: No valid topological ordering exists

        Soft warnings (proceed to Layer 2):
        - Disconnected components: May be valid parallel subplans
        """
        hard_errors = []
        warnings = []

        # Check 1: Empty Graph (HARD)
        if graph.number_of_nodes() == 0:
            hard_errors.append("Plan is empty (no actions generated).")
            return VerificationResult(is_valid=False, hard_errors=hard_errors, warnings=warnings)

        # Check 2: Connectivity (SOFT → warning only)
        # Disconnected components may be valid parallel/independent subplans.
        # Layer 2 (VAL) will validate actual executability.
        if not nx.is_weakly_connected(graph):
            warnings.append("Plan graph has disconnected components - may indicate parallel independent subplans")

        # Check 3: Cycles (HARD)
        # A plan must be a Directed Acyclic Graph (DAG) to have valid execution order.
        try:
            if not nx.is_directed_acyclic_graph(graph):
                cycle_edges = nx.find_cycle(graph)
                cycle_nodes = [u for u, v in cycle_edges]
                cycle_str = " -> ".join(map(str, cycle_nodes))
                hard_errors.append(f"Cycle detected: {cycle_str}")
        except Exception as e:
            hard_errors.append(f"Error checking cycles: {str(e)}")

        # Check 4: Dangling Edges
        # (NetworkX usually handles this by adding nodes, but we check logic)
        # In this implementation, we assume BDIPlan graph construction already
        # guarantees node existence.

        is_valid = len(hard_errors) == 0
        return VerificationResult(is_valid=is_valid, hard_errors=hard_errors, warnings=warnings)

    @staticmethod
    def topological_sort(graph: nx.DiGraph) -> list[str]:
        """
        Returns a valid execution order of action IDs.

        Returns empty list if graph has cycles (no valid ordering exists).
        """
        try:
            return list(nx.topological_sort(graph))
        except nx.NetworkXUnfeasible:
            return []
