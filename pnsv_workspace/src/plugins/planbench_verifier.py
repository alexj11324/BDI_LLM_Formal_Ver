"""PlanBench domain verifier for PDDL Blocksworld.

This plugin implements a forward-search state simulator that validates
IntentionDAGs against Blocksworld PDDL semantics.  It iterates topologically
through the DAG nodes and checks action preconditions against the current
simulated state.

Supported Blocksworld actions
-----------------------------
* ``pick-up(block)`` – pick a clear block from the table.
* ``put-down(block)`` – place the held block on the table.
* ``stack(block, target)`` – place the held block onto a clear target block.
* ``unstack(block, from_block)`` – remove a clear block from on top of another.

The PDDL state is stored in ``BeliefState.environment_context['pddl_state']``
as a ``Set[str]`` of ground predicates (e.g. ``"clear(A)"``, ``"on(A, B)"``).

Design notes
------------
* This module deliberately imports **no** core-engine internals beyond the
  schemas and the ``BaseDomainVerifier`` interface.
* All PDDL logic is self-contained – the BDI engine never touches it.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, FrozenSet, List, Set, Tuple

from src.core.schemas import BeliefState, IntentionDAG, IntentionNode
from src.core.verification_bus import BaseDomainVerifier


# ---------------------------------------------------------------------------
# Blocksworld Action Definitions
# ---------------------------------------------------------------------------

# Each action definition maps an action_type to:
#   preconditions(params, state) -> List[str]   (predicates that must hold)
#   add_effects(params)           -> List[str]   (predicates to add)
#   del_effects(params)           -> List[str]   (predicates to remove)

def _pick_up_preconditions(params: Dict[str, Any], state: Set[str]) -> List[str]:
    """Preconditions for pick-up(block): clear(block), ontable(block), arm-empty."""
    block: str = params["block"]
    return [f"clear({block})", f"ontable({block})", "arm-empty"]


def _pick_up_add(params: Dict[str, Any]) -> List[str]:
    block: str = params["block"]
    return [f"holding({block})"]


def _pick_up_del(params: Dict[str, Any]) -> List[str]:
    block: str = params["block"]
    return [f"clear({block})", f"ontable({block})", "arm-empty"]


def _put_down_preconditions(params: Dict[str, Any], state: Set[str]) -> List[str]:
    block: str = params["block"]
    return [f"holding({block})"]


def _put_down_add(params: Dict[str, Any]) -> List[str]:
    block: str = params["block"]
    return [f"clear({block})", f"ontable({block})", "arm-empty"]


def _put_down_del(params: Dict[str, Any]) -> List[str]:
    block: str = params["block"]
    return [f"holding({block})"]


def _stack_preconditions(params: Dict[str, Any], state: Set[str]) -> List[str]:
    block: str = params["block"]
    target: str = params["target"]
    return [f"holding({block})", f"clear({target})"]


def _stack_add(params: Dict[str, Any]) -> List[str]:
    block: str = params["block"]
    target: str = params["target"]
    return [f"on({block}, {target})", f"clear({block})", "arm-empty"]


def _stack_del(params: Dict[str, Any]) -> List[str]:
    block: str = params["block"]
    target: str = params["target"]
    return [f"holding({block})", f"clear({target})"]


def _unstack_preconditions(params: Dict[str, Any], state: Set[str]) -> List[str]:
    block: str = params["block"]
    from_block: str = params["from_block"]
    return [f"clear({block})", f"on({block}, {from_block})", "arm-empty"]


def _unstack_add(params: Dict[str, Any]) -> List[str]:
    block: str = params["block"]
    from_block: str = params["from_block"]
    return [f"holding({block})", f"clear({from_block})"]


def _unstack_del(params: Dict[str, Any]) -> List[str]:
    block: str = params["block"]
    from_block: str = params["from_block"]
    return [f"clear({block})", f"on({block}, {from_block})", "arm-empty"]


# Registry of all supported Blocksworld actions.
BLOCKSWORLD_ACTIONS: Dict[str, Dict[str, Any]] = {
    "pick-up": {
        "preconditions": _pick_up_preconditions,
        "add_effects": _pick_up_add,
        "del_effects": _pick_up_del,
        "required_params": ["block"],
    },
    "put-down": {
        "preconditions": _put_down_preconditions,
        "add_effects": _put_down_add,
        "del_effects": _put_down_del,
        "required_params": ["block"],
    },
    "stack": {
        "preconditions": _stack_preconditions,
        "add_effects": _stack_add,
        "del_effects": _stack_del,
        "required_params": ["block", "target"],
    },
    "unstack": {
        "preconditions": _unstack_preconditions,
        "add_effects": _unstack_add,
        "del_effects": _unstack_del,
        "required_params": ["block", "from_block"],
    },
}


# ---------------------------------------------------------------------------
# Topological Sort Helper
# ---------------------------------------------------------------------------

def _topological_sort(nodes: List[IntentionNode]) -> List[IntentionNode]:
    """Return nodes in topological (dependency-respecting) order.

    Uses Kahn's algorithm.  Raises ``ValueError`` if a cycle is detected.

    Parameters
    ----------
    nodes : List[IntentionNode]
        The DAG nodes with inter-node dependencies.

    Returns
    -------
    List[IntentionNode]
        Nodes ordered so that every node appears after all of its
        dependencies.

    Raises
    ------
    ValueError
        If the dependency graph contains a cycle.
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
        # Decrease in-degree for nodes that depend on |current_id|.
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


# ---------------------------------------------------------------------------
# PlanBench Verifier
# ---------------------------------------------------------------------------

class PlanBenchVerifier(BaseDomainVerifier):
    """Forward-search state simulator for PDDL Blocksworld verification.

    This verifier iterates topologically through the IntentionDAG nodes and
    checks each action's preconditions against the simulated PDDL state.  On
    the first precondition violation, it returns a structured error trace and
    a correction hint for the DSPy pipeline.

    The PDDL state is expected to be stored in
    ``current_belief.environment_context['pddl_state']`` as a list (or set)
    of ground predicate strings.

    Example PDDL state::

        {
            "pddl_state": ["clear(A)", "on(A, B)", "ontable(B)", "arm-empty"]
        }
    """

    def verify_transition(
        self,
        current_belief: BeliefState,
        intention_dag: IntentionDAG,
    ) -> Tuple[bool, str, str]:
        """Validate an intention DAG against Blocksworld PDDL semantics.

        Parameters
        ----------
        current_belief : BeliefState
            A deep copy of the agent's belief state.  The verifier freely
            mutates ``environment_context['pddl_state']`` during simulation.
        intention_dag : IntentionDAG
            The candidate plan (DAG of intention nodes).

        Returns
        -------
        Tuple[bool, str, str]
            ``(is_valid, formal_error_trace, dspy_correction_hint)``.
        """
        # ── Extract and normalise the PDDL state ──
        raw_state = current_belief.environment_context.get("pddl_state", [])
        if isinstance(raw_state, set):
            state: Set[str] = raw_state
        elif isinstance(raw_state, (list, tuple)):
            state = set(raw_state)
        else:
            return (
                False,
                "StateFormatError: 'pddl_state' must be a list or set of predicate strings.",
                "Ensure environment_context['pddl_state'] is a list of predicate strings "
                "like ['clear(A)', 'on(A, B)', 'arm-empty'].",
            )

        # ── Topologically sort the DAG nodes ──
        try:
            sorted_nodes = _topological_sort(intention_dag.nodes)
        except ValueError as exc:
            message = str(exc)
            hint = (
                "Your plan references a dependency that does not exist. "
                "Ensure every dependency points to a valid node_id in the DAG."
            )
            if "cycle" in message.lower():
                hint = (
                    "Your plan contains a dependency cycle.  Ensure that node "
                    "dependencies form a valid DAG with no circular references."
                )
            return (
                False,
                f"TopologicalSortError: {exc}",
                hint,
            )

        # ── Forward simulation ──
        for node in sorted_nodes:
            action_type = node.action_type.lower().strip()

            # Check that the action type is recognised.
            if action_type not in BLOCKSWORLD_ACTIONS:
                return (
                    False,
                    f"UnknownActionError: '{node.action_type}' is not a valid "
                    f"Blocksworld action at node '{node.node_id}'. "
                    f"Valid actions: {list(BLOCKSWORLD_ACTIONS.keys())}.",
                    f"You used action '{node.action_type}' which is not a valid "
                    f"Blocksworld action.  Use one of: "
                    f"{', '.join(BLOCKSWORLD_ACTIONS.keys())}.",
                )

            action_def = BLOCKSWORLD_ACTIONS[action_type]

            # Check that all required parameters are present.
            missing_params = [
                p for p in action_def["required_params"]
                if p not in node.parameters
            ]
            if missing_params:
                return (
                    False,
                    f"MissingParameterError: Action '{action_type}' at node "
                    f"'{node.node_id}' is missing required parameters: "
                    f"{missing_params}.",
                    f"Action '{action_type}' requires parameters: "
                    f"{action_def['required_params']}.  You are missing: "
                    f"{missing_params}.  Please provide all required parameters.",
                )

            # Check preconditions.
            required_predicates: List[str] = action_def["preconditions"](
                node.parameters, state
            )
            for predicate in required_predicates:
                if predicate not in state:
                    return (
                        False,
                        f"PreconditionViolation: {predicate} is False at "
                        f"node '{node.node_id}' (action: {action_type}, "
                        f"params: {node.parameters}). "
                        f"Current state: {sorted(state)}.",
                        f"You attempted to {action_type}({', '.join(str(v) for v in node.parameters.values())}) "
                        f"but {predicate} does not hold in the current state.  "
                        f"Current state predicates: {sorted(state)}.",
                    )

            # Apply effects: add new predicates, remove old ones.
            add_preds: List[str] = action_def["add_effects"](node.parameters)
            del_preds: List[str] = action_def["del_effects"](node.parameters)

            for pred in del_preds:
                state.discard(pred)
            for pred in add_preds:
                state.add(pred)

        # All nodes executed successfully.
        return (True, "", "")
