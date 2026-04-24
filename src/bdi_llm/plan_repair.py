#!/usr/bin/env python3
"""
Plan Auto-Repair System
=======================

Automatically repairs invalid plans by:
1. Connecting disconnected subgraphs with virtual nodes
2. Fixing common structural errors
3. Normalizing graph structure

This addresses the main PlanBench failure: LLM generates disconnected
subgraphs for complex multi-step plans.

Author: BDI-LLM Research
Date: 2026-02-10
"""

from dataclasses import dataclass

import networkx as nx

from .schemas import ActionNode, BDIPlan, DependencyEdge


@dataclass
class RepairResult:
    """Result of plan repair attempt"""

    success: bool
    repaired_plan: BDIPlan | None
    original_valid: bool
    repairs_applied: list[str]
    errors: list[str]


class PlanRepairer:
    """
    Automatic plan repair system

    Handles:
    - Disconnected subgraphs (connects with virtual nodes)
    - Missing root nodes (adds virtual START)
    - Missing terminal nodes (adds virtual END)
    - Graph canonicalization
    """

    VIRTUAL_START = "__START__"
    VIRTUAL_END = "__END__"

    @classmethod
    def _append_virtual_node_once(
        cls,
        nodes: list[ActionNode],
        node_id: str,
        description: str,
    ) -> None:
        """Append a virtual node only when the ID does not already exist."""
        if any(node.id == node_id for node in nodes):
            return
        nodes.append(
            ActionNode(
                id=node_id,
                action_type="Virtual",
                params={},
                description=description,
            )
        )

    @classmethod
    def repair(cls, plan: BDIPlan) -> RepairResult:
        """
        Attempt to repair an invalid plan

        Args:
            plan: BDIPlan that may be invalid

        Returns:
            RepairResult with repaired plan and diagnostics
        """
        repairs = []

        # Convert to NetworkX
        G = plan.to_networkx()

        # Check if already valid
        from .verifier import PlanVerifier

        result = PlanVerifier.verify(G)
        is_valid = result.is_valid
        verify_errors = result.hard_errors
        has_disconnected_components = G.number_of_nodes() > 0 and not nx.is_weakly_connected(G)

        # Even when structurally valid, we still repair disconnected components to
        # preserve the historical auto-connect behavior of this module.
        if is_valid and not has_disconnected_components:
            return RepairResult(success=True, repaired_plan=plan, original_valid=True, repairs_applied=[], errors=[])

        # Attempt repairs
        try:
            # 1. Fix cycles (must be done FIRST - cycles prevent topological ordering)
            if not nx.is_directed_acyclic_graph(G):
                plan = cls._break_cycles(plan)
                repairs.append("Broke cycles to convert graph to DAG")
                G = plan.to_networkx()

            # 2. Fix disconnected subgraphs
            if not nx.is_weakly_connected(G):
                plan = cls._connect_subgraphs(plan, G)
                repairs.append("Connected disconnected subgraphs with virtual nodes")
                G = plan.to_networkx()

            # 3. Ensure single root (no incoming edges)
            roots = cls._find_roots(G)
            if len(roots) > 1:
                plan = cls._unify_roots(plan, roots)
                repairs.append(f"Unified {len(roots)} root nodes with virtual START")
                G = plan.to_networkx()

            # 4. Ensure single terminal (no outgoing edges)
            terminals = cls._find_terminals(G)
            if len(terminals) > 1:
                plan = cls._unify_terminals(plan, terminals)
                repairs.append(f"Unified {len(terminals)} terminal nodes with virtual END")
                G = plan.to_networkx()

            # 4. Re-verify
            verifier_result = PlanVerifier.verify(G)
            is_valid = verifier_result.is_valid
            verify_errors = verifier_result.hard_errors

            return RepairResult(
                success=is_valid,
                repaired_plan=plan if is_valid else None,
                original_valid=False,
                repairs_applied=repairs,
                errors=verify_errors if not is_valid else [],
            )

        except Exception as e:
            return RepairResult(
                success=False,
                repaired_plan=None,
                original_valid=False,
                repairs_applied=repairs,
                errors=[f"Repair failed: {str(e)}"],
            )

    @classmethod
    def _connect_subgraphs(cls, plan: BDIPlan, G: nx.DiGraph) -> BDIPlan:
        """
        Connect disconnected subgraphs using virtual START/END nodes

        Strategy:
        1. Find all weakly connected components
        2. Create virtual START node
        3. Connect START to root of each component
        4. Create virtual END node
        5. Connect terminal of each component to END
        """
        # Get connected components
        components = list(nx.weakly_connected_components(G))

        if len(components) <= 1:
            return plan  # Already connected

        # Create new nodes and edges lists
        new_nodes = list(plan.nodes)
        new_edges = list(plan.edges)

        # Add virtual START only once
        cls._append_virtual_node_once(
            new_nodes,
            cls.VIRTUAL_START,
            "Virtual start node (plan initialization)",
        )

        # Add virtual END only once
        cls._append_virtual_node_once(
            new_nodes,
            cls.VIRTUAL_END,
            "Virtual end node (plan completion)",
        )

        # For each component, connect START to roots and terminals to END
        for component in components:
            # Find root nodes in this component (no incoming edges from within component)
            roots_in_component = []
            for node_id in component:
                if component.isdisjoint(G.predecessors(node_id)):
                    roots_in_component.append(node_id)

            # Connect START to each root
            for root_id in roots_in_component:
                if root_id == cls.VIRTUAL_START:
                    continue
                new_edges.append(DependencyEdge(source=cls.VIRTUAL_START, target=root_id))

            # Find terminal nodes in this component (no outgoing edges)
            terminals_in_component = []
            for node_id in component:
                if component.isdisjoint(G.successors(node_id)):
                    terminals_in_component.append(node_id)

            # Connect each terminal to END
            for terminal_id in terminals_in_component:
                if terminal_id == cls.VIRTUAL_END:
                    continue
                new_edges.append(DependencyEdge(source=terminal_id, target=cls.VIRTUAL_END))

        return BDIPlan(goal_description=plan.goal_description, nodes=new_nodes, edges=new_edges)

    @classmethod
    def _break_cycles(cls, plan: BDIPlan) -> BDIPlan:
        """
        Break all cycles in the plan graph by removing back edges

        Strategy:
        1. Find all cycles using DFS-based back edge detection
        2. For each cycle, identify the back edge (edge to an ancestor in DFS tree)
        3. Remove back edges to convert graph to DAG
        4. Preserve plan semantics by keeping causal chain edges intact

        The algorithm uses DFS to classify edges:
        - Tree edges: edges in the DFS tree
        - Back edges: edges from descendant to ancestor (create cycles)
        - Forward/Cross edges: edges that don't create cycles

        By removing only back edges, we minimally break cycles while
        preserving the causal structure of the plan.

        Args:
            plan: BDIPlan that may contain cycles

        Returns:
            BDIPlan with all cycles broken (DAG)
        """
        G = plan.to_networkx()

        if nx.is_directed_acyclic_graph(G):
            return plan  # Already a DAG

        # Track edges to remove
        edges_to_remove: set[tuple[str, str]] = set()

        # DFS-based back edge detection
        # We need to find edges that go from a node to one of its ancestors
        visited: set[str] = set()
        rec_stack: set[str] = set()  # Nodes in current DFS recursion stack
        ancestor_map: dict[str, set[str]] = {}  # node -> set of its ancestors

        def dfs_find_back_edges(node: str, ancestors: set[str]) -> None:
            """
            DFS traversal to find back edges

            Args:
                node: Current node being visited
                ancestors: Set of ancestors of current node in DFS tree
            """
            visited.add(node)
            rec_stack.add(node)
            ancestor_map[node] = ancestors.copy()
            try:
                for successor in G.successors(node):
                    if successor not in visited:
                        # Tree edge - continue DFS
                        new_ancestors = ancestors | {node}
                        dfs_find_back_edges(successor, new_ancestors)
                    elif successor in rec_stack:
                        # Back edge - this creates a cycle
                        # The edge (node -> successor) where successor is an ancestor
                        edges_to_remove.add((node, successor))
                    # else: forward or cross edge - doesn't create cycle
            finally:
                rec_stack.discard(node)

        # Run DFS from all unvisited nodes (handles disconnected graphs)
        for node in G.nodes():
            if node not in visited:
                dfs_find_back_edges(node, set())

        # If no back edges found but graph has cycles, fall back to simple cycle breaking
        if not edges_to_remove and not nx.is_directed_acyclic_graph(G):
            # Fallback: for each simple cycle, remove one edge
            cycles = list(nx.simple_cycles(G))
            for cycle in cycles:
                if len(cycle) >= 2:
                    # Remove edge from last node to first node in cycle
                    # This breaks the cycle
                    edges_to_remove.add((cycle[-1], cycle[0]))

        # Remove the back edges from the plan
        if edges_to_remove:
            new_edges = [edge for edge in plan.edges if (edge.source, edge.target) not in edges_to_remove]

            return BDIPlan(goal_description=plan.goal_description, nodes=list(plan.nodes), edges=new_edges)

        return plan

    @classmethod
    def _find_roots(cls, G: nx.DiGraph) -> list[str]:
        """Find nodes with no incoming edges"""
        return [n for n in G.nodes() if G.in_degree(n) == 0]

    @classmethod
    def _find_terminals(cls, G: nx.DiGraph) -> list[str]:
        """Find nodes with no outgoing edges"""
        return [n for n in G.nodes() if G.out_degree(n) == 0]

    @classmethod
    def _unify_roots(cls, plan: BDIPlan, roots: list[str]) -> BDIPlan:
        """Add virtual START and connect to all roots"""
        new_nodes = list(plan.nodes)
        new_edges = list(plan.edges)

        # Add virtual START only if missing
        cls._append_virtual_node_once(
            new_nodes,
            cls.VIRTUAL_START,
            "Virtual start node",
        )

        # Connect START to each root
        for root_id in roots:
            if root_id != cls.VIRTUAL_START:
                new_edges.append(DependencyEdge(source=cls.VIRTUAL_START, target=root_id))

        return BDIPlan(goal_description=plan.goal_description, nodes=new_nodes, edges=new_edges)

    @classmethod
    def _unify_terminals(cls, plan: BDIPlan, terminals: list[str]) -> BDIPlan:
        """Add virtual END and connect all terminals to it"""
        new_nodes = list(plan.nodes)
        new_edges = list(plan.edges)

        # Add virtual END only if missing
        cls._append_virtual_node_once(
            new_nodes,
            cls.VIRTUAL_END,
            "Virtual end node",
        )

        # Connect each terminal to END
        for terminal_id in terminals:
            if terminal_id != cls.VIRTUAL_END:
                new_edges.append(DependencyEdge(source=terminal_id, target=cls.VIRTUAL_END))

        return BDIPlan(goal_description=plan.goal_description, nodes=new_nodes, edges=new_edges)


class PlanCanonicalizer:
    """
    Canonicalize plan structure for consistent output

    Ensures:
    - Consistent node ID naming
    - Topologically sorted edge order
    - No redundant edges
    """

    @classmethod
    def canonicalize(cls, plan: BDIPlan) -> BDIPlan:
        """
        Return canonical form of plan

        Args:
            plan: Input BDIPlan

        Returns:
            Canonicalized BDIPlan
        """
        G = plan.to_networkx()

        # Remove self-loops
        G.remove_edges_from(nx.selfloop_edges(G))

        # Get topological order for node renaming
        try:
            topo_order = list(nx.topological_sort(G))
        except nx.NetworkXUnfeasible:
            # Has cycles - just use original order
            topo_order = [n.id for n in plan.nodes]

        # Create ID mapping
        id_mapping = {old_id: f"action_{i + 1}" for i, old_id in enumerate(topo_order)}

        # Create new nodes with canonical IDs
        node_map = {n.id: n for n in plan.nodes}
        new_nodes = []

        for old_id in topo_order:
            if old_id in node_map:
                old_node = node_map[old_id]
                new_nodes.append(
                    ActionNode(
                        id=id_mapping[old_id],
                        action_type=old_node.action_type,
                        params=old_node.params,
                        description=old_node.description,
                    )
                )

        # Create new edges with canonical IDs
        new_edges = []
        seen_edges = set()

        for edge in plan.edges:
            if edge.source in id_mapping and edge.target in id_mapping:
                new_source = id_mapping[edge.source]
                new_target = id_mapping[edge.target]

                edge_key = (new_source, new_target)
                if edge_key not in seen_edges and new_source != new_target:
                    new_edges.append(DependencyEdge(source=new_source, target=new_target))
                    seen_edges.add(edge_key)

        return BDIPlan(goal_description=plan.goal_description, nodes=new_nodes, edges=new_edges)


def repair_and_verify(plan: BDIPlan) -> tuple[BDIPlan, bool, list[str]]:
    """
    Convenience function: repair plan and verify result

    Args:
        plan: Input BDIPlan

    Returns:
        (repaired_plan, is_valid, messages)
    """
    result = PlanRepairer.repair(plan)

    if result.success:
        # Canonicalize the repaired plan
        canonical = PlanCanonicalizer.canonicalize(result.repaired_plan)
        return canonical, True, result.repairs_applied
    else:
        return plan, False, result.errors
