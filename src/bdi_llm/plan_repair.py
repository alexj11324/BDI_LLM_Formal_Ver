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

import networkx as nx
from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass
from .schemas import BDIPlan, ActionNode, DependencyEdge


@dataclass
class RepairResult:
    """Result of plan repair attempt"""
    success: bool
    repaired_plan: Optional[BDIPlan]
    original_valid: bool
    repairs_applied: List[str]
    errors: List[str]


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
    def repair(cls, plan: BDIPlan) -> RepairResult:
        """
        Attempt to repair an invalid plan

        Args:
            plan: BDIPlan that may be invalid

        Returns:
            RepairResult with repaired plan and diagnostics
        """
        repairs = []
        errors = []

        # Convert to NetworkX
        G = plan.to_networkx()

        # Check if already valid
        from .verifier import PlanVerifier
        is_valid, verify_errors = PlanVerifier.verify(G)

        if is_valid:
            return RepairResult(
                success=True,
                repaired_plan=plan,
                original_valid=True,
                repairs_applied=[],
                errors=[]
            )

        # Attempt repairs
        try:
            # 1. Fix disconnected subgraphs
            if not nx.is_weakly_connected(G):
                plan = cls._connect_subgraphs(plan, G)
                repairs.append("Connected disconnected subgraphs with virtual nodes")
                G = plan.to_networkx()

            # 2. Ensure single root (no incoming edges)
            roots = cls._find_roots(G)
            if len(roots) > 1:
                plan = cls._unify_roots(plan, roots)
                repairs.append(f"Unified {len(roots)} root nodes with virtual START")
                G = plan.to_networkx()

            # 3. Ensure single terminal (no outgoing edges)
            terminals = cls._find_terminals(G)
            if len(terminals) > 1:
                plan = cls._unify_terminals(plan, terminals)
                repairs.append(f"Unified {len(terminals)} terminal nodes with virtual END")
                G = plan.to_networkx()

            # 4. Re-verify
            is_valid, verify_errors = PlanVerifier.verify(G)

            return RepairResult(
                success=is_valid,
                repaired_plan=plan if is_valid else None,
                original_valid=False,
                repairs_applied=repairs,
                errors=verify_errors if not is_valid else []
            )

        except Exception as e:
            return RepairResult(
                success=False,
                repaired_plan=None,
                original_valid=False,
                repairs_applied=repairs,
                errors=[f"Repair failed: {str(e)}"]
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

        # Add virtual START
        start_node = ActionNode(
            id=cls.VIRTUAL_START,
            action_type="Virtual",
            params={},
            description="Virtual start node (plan initialization)"
        )
        new_nodes.append(start_node)

        # Add virtual END
        end_node = ActionNode(
            id=cls.VIRTUAL_END,
            action_type="Virtual",
            params={},
            description="Virtual end node (plan completion)"
        )
        new_nodes.append(end_node)

        # For each component, connect START to roots and terminals to END
        for component in components:
            # Find root nodes in this component (no incoming edges from within component)
            roots_in_component = []
            for node_id in component:
                predecessors = set(G.predecessors(node_id))
                if not predecessors.intersection(component):
                    roots_in_component.append(node_id)

            # Connect START to each root
            for root_id in roots_in_component:
                new_edges.append(DependencyEdge(
                    source=cls.VIRTUAL_START,
                    target=root_id
                ))

            # Find terminal nodes in this component (no outgoing edges)
            terminals_in_component = []
            for node_id in component:
                successors = set(G.successors(node_id))
                if not successors.intersection(component):
                    terminals_in_component.append(node_id)

            # Connect each terminal to END
            for terminal_id in terminals_in_component:
                new_edges.append(DependencyEdge(
                    source=terminal_id,
                    target=cls.VIRTUAL_END
                ))

        return BDIPlan(
            goal_description=plan.goal_description,
            nodes=new_nodes,
            edges=new_edges
        )

    @classmethod
    def _find_roots(cls, G: nx.DiGraph) -> List[str]:
        """Find nodes with no incoming edges"""
        return [n for n in G.nodes() if G.in_degree(n) == 0]

    @classmethod
    def _find_terminals(cls, G: nx.DiGraph) -> List[str]:
        """Find nodes with no outgoing edges"""
        return [n for n in G.nodes() if G.out_degree(n) == 0]

    @classmethod
    def _unify_roots(cls, plan: BDIPlan, roots: List[str]) -> BDIPlan:
        """Add virtual START and connect to all roots"""
        new_nodes = list(plan.nodes)
        new_edges = list(plan.edges)

        # Add virtual START
        start_node = ActionNode(
            id=cls.VIRTUAL_START,
            action_type="Virtual",
            params={},
            description="Virtual start node"
        )
        new_nodes.append(start_node)

        # Connect START to each root
        for root_id in roots:
            if root_id != cls.VIRTUAL_START:
                new_edges.append(DependencyEdge(
                    source=cls.VIRTUAL_START,
                    target=root_id
                ))

        return BDIPlan(
            goal_description=plan.goal_description,
            nodes=new_nodes,
            edges=new_edges
        )

    @classmethod
    def _unify_terminals(cls, plan: BDIPlan, terminals: List[str]) -> BDIPlan:
        """Add virtual END and connect all terminals to it"""
        new_nodes = list(plan.nodes)
        new_edges = list(plan.edges)

        # Add virtual END
        end_node = ActionNode(
            id=cls.VIRTUAL_END,
            action_type="Virtual",
            params={},
            description="Virtual end node"
        )
        new_nodes.append(end_node)

        # Connect each terminal to END
        for terminal_id in terminals:
            if terminal_id != cls.VIRTUAL_END:
                new_edges.append(DependencyEdge(
                    source=terminal_id,
                    target=cls.VIRTUAL_END
                ))

        return BDIPlan(
            goal_description=plan.goal_description,
            nodes=new_nodes,
            edges=new_edges
        )


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
        id_mapping = {old_id: f"action_{i+1}" for i, old_id in enumerate(topo_order)}

        # Create new nodes with canonical IDs
        node_map = {n.id: n for n in plan.nodes}
        new_nodes = []

        for old_id in topo_order:
            if old_id in node_map:
                old_node = node_map[old_id]
                new_nodes.append(ActionNode(
                    id=id_mapping[old_id],
                    action_type=old_node.action_type,
                    params=old_node.params,
                    description=old_node.description
                ))

        # Create new edges with canonical IDs
        new_edges = []
        seen_edges = set()

        for edge in plan.edges:
            if edge.source in id_mapping and edge.target in id_mapping:
                new_source = id_mapping[edge.source]
                new_target = id_mapping[edge.target]

                edge_key = (new_source, new_target)
                if edge_key not in seen_edges and new_source != new_target:
                    new_edges.append(DependencyEdge(
                        source=new_source,
                        target=new_target
                    ))
                    seen_edges.add(edge_key)

        return BDIPlan(
            goal_description=plan.goal_description,
            nodes=new_nodes,
            edges=new_edges
        )


def repair_and_verify(plan: BDIPlan) -> Tuple[BDIPlan, bool, List[str]]:
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
