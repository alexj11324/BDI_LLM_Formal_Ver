#!/usr/bin/env python3
"""
Compatibility auto-repair helper for disconnected plan graphs.

Some legacy scripts import this module directly. It connects weakly-connected
components with minimal dependency edges so downstream verification can proceed.
"""

from typing import Tuple

import networkx as nx

from src.bdi_llm.schemas import BDIPlan
from src.bdi_llm.plan_repair import PlanRepairer


def auto_repair_disconnected_graph(plan: BDIPlan) -> Tuple[BDIPlan, bool]:
    """
    Add bridging edges between disconnected components.

    Returns:
        (repaired_plan, was_repaired)
    """
    graph = plan.to_networkx()
    # Preserve original behavior: only repair if disconnected
    if graph.number_of_nodes() == 0 or nx.is_weakly_connected(graph):
        return plan, False

    result = PlanRepairer.repair(plan)

    # If PlanRepairer says success, and it wasn't valid originally (which we know it wasn't, or at least we think so),
    # then it was repaired.
    # Note: PlanRepairer.repair() re-verifies. If verification passes, it returns success=True.

    if result.success:
        return result.repaired_plan, True

    return plan, False
