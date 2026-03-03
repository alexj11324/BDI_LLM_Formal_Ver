"""Shared DAG utility functions for IntentionDAG verifiers.

This module centralizes the topological sort algorithm used by all domain
verifiers.  Keeping the logic in one place avoids behavioral drift across
verifiers when error handling or performance improvements are made.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Sequence

from src.core.schemas import IntentionNode


def topological_sort(nodes: Sequence[IntentionNode]) -> List[IntentionNode]:
    """Return nodes in topological (dependency-respecting) order.

    Uses Kahn's algorithm.  Raises ``ValueError`` if a cycle is detected
    or if a node references a dependency that does not exist in the DAG.

    Parameters
    ----------
    nodes : Sequence[IntentionNode]
        The DAG nodes with inter-node dependencies.

    Returns
    -------
    List[IntentionNode]
        Nodes ordered so that every node appears after all of its
        dependencies.

    Raises
    ------
    ValueError
        If the dependency graph contains a cycle or a missing dependency.
    """
    node_map: Dict[str, IntentionNode] = {n.node_id: n for n in nodes}
    in_degree: Dict[str, int] = {n.node_id: 0 for n in nodes}

    for node in nodes:
        for dep_id in node.dependencies:
            if dep_id not in node_map:
                raise ValueError(
                    f"Node '{node.node_id}' depends on '{dep_id}' "
                    f"which does not exist in the DAG."
                )
            in_degree[node.node_id] += 1

    queue: deque[str] = deque(
        nid for nid, deg in in_degree.items() if deg == 0
    )
    sorted_ids: List[str] = []

    while queue:
        current_id = queue.popleft()
        sorted_ids.append(current_id)
        for node in nodes:
            if current_id in node.dependencies:
                in_degree[node.node_id] -= 1
                if in_degree[node.node_id] == 0:
                    queue.append(node.node_id)

    if len(sorted_ids) != len(nodes):
        raise ValueError(
            "Cycle detected in IntentionDAG.  Sorted "
            f"{len(sorted_ids)} of {len(nodes)} nodes."
        )

    return [node_map[nid] for nid in sorted_ids]
