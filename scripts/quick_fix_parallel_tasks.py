#!/usr/bin/env python3
"""
Compatibility auto-repair helper for disconnected plan graphs.

Some legacy scripts import this module directly. It connects weakly-connected
components with minimal dependency edges so downstream verification can proceed.
"""

from typing import Dict, Iterable, Tuple

import networkx as nx

from src.bdi_llm.schemas import BDIPlan, DependencyEdge


def _node_rank(component: Iterable[str], order: Dict[str, int]) -> int:
    return min(order.get(node_id, 10**9) for node_id in component)


def _pick_tail(graph: nx.DiGraph, component: Iterable[str], order: Dict[str, int]) -> str:
    nodes = list(component)
    sinks = [node_id for node_id in nodes if graph.out_degree(node_id) == 0]
    candidates = sinks if sinks else nodes
    return max(candidates, key=lambda node_id: order.get(node_id, -1))


def _pick_head(graph: nx.DiGraph, component: Iterable[str], order: Dict[str, int]) -> str:
    nodes = list(component)
    sources = [node_id for node_id in nodes if graph.in_degree(node_id) == 0]
    candidates = sources if sources else nodes
    return min(candidates, key=lambda node_id: order.get(node_id, 10**9))


def auto_repair_disconnected_graph(plan: BDIPlan) -> Tuple[BDIPlan, bool]:
    """
    Add bridging edges between disconnected components.

    Returns:
        (repaired_plan, was_repaired)
    """
    graph = plan.to_networkx()
    if graph.number_of_nodes() == 0 or nx.is_weakly_connected(graph):
        return plan, False

    repaired_plan = plan.model_copy(deep=True)
    repaired_graph = repaired_plan.to_networkx()
    order = {node.id: idx for idx, node in enumerate(repaired_plan.nodes)}

    components = sorted(
        nx.weakly_connected_components(repaired_graph),
        key=lambda comp: _node_rank(comp, order),
    )

    added_edges = 0
    for idx in range(len(components) - 1):
        left = components[idx]
        right = components[idx + 1]
        source = _pick_tail(repaired_graph, left, order)
        target = _pick_head(repaired_graph, right, order)

        if source == target or repaired_graph.has_edge(source, target):
            continue

        repaired_graph.add_edge(source, target, relationship="depends_on")
        repaired_plan.edges.append(
            DependencyEdge(source=source, target=target, relationship="depends_on")
        )
        added_edges += 1

    if added_edges == 0:
        return plan, False

    if not nx.is_weakly_connected(repaired_graph):
        return plan, False
    if not nx.is_directed_acyclic_graph(repaired_graph):
        return plan, False

    return repaired_plan, True
